from random import uniform, randint, random, choice
from aptc import Account, new_client
from loguru import logger
from web3 import Web3
import time

from .utilities.liquidswap_sdk.client import LiquidSwapClient
from .utilities import reader
from . import useful_data
from . import modules


class AptosBridge:
    def __init__(self, evm_private_key: str, aptos_mnemonic: str):
        self.evm_private = evm_private_key
        self.aptos_mnemonic = aptos_mnemonic

        self.aptos = modules.Aptos(self.aptos_mnemonic)
        self.aptos_private_key = self.aptos.mnemonic_to_private_key()
        self.aptos_address = self.aptos.get_wallet_address()

        self.data = useful_data.Data()

        self.evm = modules.Evm(self.evm_private)
        self.evm_address = self.evm.wallet_address

        # Network to use in aptos bridge transactions
        self.network_to_swap = ""
        # Last balance on aptos
        self.current_aptos_balance = int

    def usdc_to_aptos(self) -> bool:
        try:
            try:
                self.current_aptos_balance = self.aptos.get_account_balance()
            except:
                self.current_aptos_balance = 0

            self.network_to_swap, amount_usdc_to_send = self.evm.get_maximum_balance_network(self.evm_address)

            logger.info(f"Sending {amount_usdc_to_send / 1000000} USDC from {self.network_to_swap} to Aptos...")

            w3 = self.evm.get_web3_instance(self.data.constants["networks"][self.network_to_swap]["urls"])

            usdc_contract = w3.eth.contract(address=self.data.constants["usdc_contracts"][self.network_to_swap],
                                            abi=reader.read_abi("usdc_abi.json"))
            aptos_bridge_contract = w3.eth.contract(
                address=self.data.constants["aptos_bridge_contracts"][self.network_to_swap],
                abi=reader.read_abi("aptos_abi.json"))

            adapter_params = self.evm.create_adapter_params(self.network_to_swap, self.aptos_address)

            fee, native_balance = self.evm.get_fee(aptos_bridge_contract, w3,
                                                   (self.evm_address, "0x0000000000000000000000000000000000000000"),
                                                   adapter_params)

            underpriced_retry = False
            retries = 3
            delay = randint(20, 40)

            for attempt in range(retries):
                try:

                    nonce = w3.eth.get_transaction_count(self.evm_address)
                    max_fee_per_gas, max_priority_fee_per_gas = self.evm.get_gas_data(self.network_to_swap)

                    if underpriced_retry:
                        max_fee_per_gas *= 1.15 + 0.05 * random()
                        max_priority_fee_per_gas *= 1.15 + 0.05 * random()

                    # Check allowance
                    allowance = self.evm.get_allowance(usdc_contract,
                                                       self.evm_address,
                                                       self.data.constants["aptos_bridge_contracts"][
                                                           self.network_to_swap])
                    if allowance < amount_usdc_to_send:
                        self.evm.approve_and_retry(self.evm.account, amount_usdc_to_send, nonce, max_fee_per_gas,
                                                   max_priority_fee_per_gas, w3,
                                                   self.network_to_swap,
                                                   usdc_contract,
                                                   self.data.constants["aptos_bridge_contracts"][self.network_to_swap],
                                                   self.data.constants["networks"][self.network_to_swap]["tx"])

                        nonce = w3.eth.get_transaction_count(self.evm_address)

                    # Send tokens
                    swap_txn_obj = aptos_bridge_contract.functions.sendToAptos(
                        self.data.constants["usdc_contracts"][self.network_to_swap],
                        Web3.to_bytes(hexstr=self.aptos_address.hex()),
                        int(amount_usdc_to_send),
                        (self.evm_address, "0x0000000000000000000000000000000000000000"),
                        adapter_params
                    )
                    swap_gas_estimate = swap_txn_obj.estimate_gas({'from': self.evm_address, 'value': fee})
                    # Multiply swap_gas_estimate by a random number between 1.01 to 1.04
                    swap_gas_estimate = int(swap_gas_estimate * uniform(1.0301, 1.0402))

                    if self.network_to_swap == "Polygon":
                        swap_gas_estimate = int(swap_gas_estimate * uniform(0.69090, 0.703))

                    swap_txn = swap_txn_obj.build_transaction({
                        'from': self.evm_address,
                        'value': fee,
                        'gas': swap_gas_estimate,
                        'maxFeePerGas': int(w3.to_wei(max_fee_per_gas, 'gwei')),
                        'maxPriorityFeePerGas': int(w3.to_wei(max_priority_fee_per_gas, 'gwei')),
                        'nonce': nonce,
                    })

                    signed_swap_txn = w3.eth.account.sign_transaction(swap_txn, self.evm_private)
                    swap_txn_hash = w3.eth.send_raw_transaction(signed_swap_txn.rawTransaction)

                    logger.info(
                        f"Transaction hash -> {self.data.constants['networks'][self.network_to_swap]['tx']}{swap_txn_hash.hex()}")

                    while True:
                        try:
                            tx_info = w3.eth.get_transaction(swap_txn_hash)
                            if tx_info is None or " not found" in str(tx_info):
                                logger.error('Transaction not found')
                                time.sleep(5)
                            else:
                                receipt = w3.eth.get_transaction_receipt(swap_txn_hash)

                                if receipt is None:
                                    logger.info('Transaction not confirmed yet')
                                    time.sleep(5)

                                elif receipt['status'] == 1:
                                    logger.success(
                                        f"{self.network_to_swap} | SWAP SUCCEEDED -> {self.data.constants['networks'][self.network_to_swap]['tx']}{swap_txn_hash.hex()}")
                                    return True

                                else:
                                    logger.error(
                                        f"Transaction failed -> {self.data.constants['networks'][self.network_to_swap]['tx']}{swap_txn_hash.hex()}")
                                    break
                        except Exception as e:
                            if " not found." in str(e):
                                logger.error('Transaction not found')
                                time.sleep(5)
                            else:
                                logger.error(f'Error: {e}')

                except Exception as e:
                    if "execution reverted: LayerZero: not enough native for fees" in str(e):
                        if attempt < retries - 1:
                            logger.warning(
                                f"Retrying 'usdc to aptos' function (attempt {attempt + 1}/{retries}) due to error -> {e}")
                            time.sleep(delay)
                        else:
                            logger.error(f"Failed to complete 'usdc to aptos' function after {retries} attempts -> {e}")
                            break
                    else:
                        logger.error(f"Error while confirming USDC transaction to Aptos -> {e}")
                        break

            return False

        except Exception as er:
            logger.error(f"Error while swapping USDC to Aptos -> {er}")

    def claim_on_aptos(self):
        try:
            client = new_client()

            trans = client.account_transactions(self.aptos_address)

            for transaction in trans:
                if "claim_coin" in str(transaction) and transaction["success"] is True:
                    logger.success(f"Token already claimed!")
                    return

            while True:
                try:
                    balance = self.aptos.get_account_balance()
                    if balance != self.current_aptos_balance:
                        break
                except:
                    pass

                time.sleep(randint(25, 35))

            rand_sleep = randint(30, 120)
            logger.info(f"Not claimed yet, waiting for {rand_sleep} seconds and start to claim.")
            time.sleep(rand_sleep)

            # Get gas price
            import requests
            r = requests.get("https://rpc.ankr.com/http/aptos/v1/estimate_gas_price",
                             headers={"Accept": "application/json, application/x-bcs"}).json()

            # submit transaction
            # load your private key, environment variable
            account = Account.load_key(self.aptos_private_key)
            account_address = account.address()

            # build a transaction payload
            payload = {
                'function': '0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::coin_bridge::claim_coin',
                'type_arguments': ["0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::USDC"],
                'arguments': [],
                'type': 'entry_function_payload'
            }

            txn_dict = {
                "sender": f"{account_address}",
                "sequence_number": str(client.get_account_sequence_number(account_address)),
                "max_gas_amount": str(1000),
                "gas_unit_price": str(r["gas_estimate"]),
                "expiration_timestamp_secs": str(int(time.time()) + 100),
                "payload": payload,
                "signature": {
                    "type": "ed25519_signature",
                    "public_key": f"{account.public_key()}",
                    "signature": f"{'0' * 128}",
                }}

            gas = int(self.aptos.get_gas_amount(txn_dict))
            txn_dict["max_gas_amount"] = str(int(gas + (gas * 0.1)))

            # encode this transaction
            encoded = client.encode(txn_dict)
            # sign this transaction
            signature = account.sign(encoded)

            txn_dict["signature"] = {
                "type": "ed25519_signature",
                "public_key": f"{account.public_key()}",
                "signature": f"{signature}",
            }

            # submit transaction
            tx = client.submit_transaction(txn_dict)

            logger.success(f"Claimed on Aptos -> {tx['hash']}")

        except Exception as err:
            logger.exception(f"Failed to claim tokens on Aptos -> {err}")

    def liquid_swap_usdc_to_aptos(self):
        try:
            liquid_client = LiquidSwapClient(node_url="https://fullnode.mainnet.aptoslabs.com/v1",
                                             tokens_mapping={
                                                 "APTOS": "0x1::aptos_coin::AptosCoin",
                                                 "USDC": "0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::USDC",
                                             },
                                             account=self.aptos.get_aptos_account())

            minimum_aptos_to_get = round(liquid_client.calculate_rates("USDC", "APTOS", 0.5), 5)

            client = new_client()

            # Get gas price
            import requests
            r = requests.get("https://rpc.ankr.com/http/aptos/v1/estimate_gas_price",
                             headers={"Accept": "application/json, application/x-bcs"}).json()

            # submit transaction
            # load your private key, environment variable
            account = Account.load_key(self.aptos_private_key)
            account_address = account.address()

            amount_to_send = randint(400000, 500000)
            # build a transaction payload
            payload = {
                'function': '0x190d44266241744264b964a37b8f09863167a12d3e70cda39376cfb4e3561e12::scripts_v2::swap',
                'type_arguments': ["0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::USDC",
                                   "0x1::aptos_coin::AptosCoin",
                                   "0x190d44266241744264b964a37b8f09863167a12d3e70cda39376cfb4e3561e12::curves::Uncorrelated"],
                'arguments': [
                    str(amount_to_send),  # amount of usdc to swap
                    str(int(minimum_aptos_to_get * 1000000))  # amount of usdc + 0.2% fee
                ],
                'type': 'entry_function_payload'
            }

            txn_dict = {"sender": str(account_address),
                        "sequence_number": str(client.get_account_sequence_number(account_address)),
                        "max_gas_amount": str(1000), "gas_unit_price": str(r["gas_estimate"]),
                        "expiration_timestamp_secs": str(int(time.time()) + 100), "payload": payload, "signature": {
                    "type": "ed25519_signature",
                    "public_key": f"{account.public_key()}",
                    "signature": f"{'0' * 128}",
                }}

            gas = int(self.aptos.get_gas_amount(txn_dict))

            txn_dict["max_gas_amount"] = str(int(gas + (gas * 0.1)))

            # encode this transaction
            encoded = client.encode(txn_dict)
            # sign this transaction
            signature = account.sign(encoded)
            # generate fake signature for transaction test

            txn_dict["signature"] = {
                "type": "ed25519_signature",
                "public_key": f"{account.public_key()}",
                "signature": f"{signature}",
            }

            # submit transaction
            tx = client.submit_transaction(txn_dict)
            if "hash" in str(tx):
                logger.success(
                    f"Swapped {amount_to_send / 1000_000} USDC to {minimum_aptos_to_get} APT on LiquidSwap -> {tx['hash']}")
            else:
                logger.error(f"Failed to swap USDC to APT on LiquidSwap -> {tx['message']}")

        except Exception as err:
            logger.error(f"Failed to swap USDC to APT on LiquidSwap -> {err}")

    def usdc_from_aptos(self):
        try:
            destination_network = choice(["Polygon", "Avalanche"])

            client = new_client()
            usdc_balance_str = client.get_account_resource(self.aptos_address,
                                                           "0x1::coin::CoinStore<0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::USDC>")[
                "data"]["coin"]["value"]

            if int(usdc_balance_str) < 1_000_000:
                logger.info(f"USDC balance is {int(usdc_balance_str) / 1000_000}, lower than expected.")
                return

            # Get gas price
            import requests
            r = requests.get("https://rpc.ankr.com/http/aptos/v1/estimate_gas_price",
                             headers={"Accept": "application/json, application/x-bcs"}).json()

            # submit transaction
            account = Account.load_key(self.aptos_private_key)
            account_address = account.address()

            # build a transaction payload
            payload = {
                'function': '0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::coin_bridge::send_coin_from',
                'type_arguments': ["0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::USDC"],
                'arguments': [
                    str(self.data.constants["networks"][destination_network]["chain_id"]),
                    "0x000000000000000000000000" + str(self.evm_address).replace("0x", ""),
                    usdc_balance_str,
                    str(randint(3357489, 5357489)),  # bridge fee
                    "0",
                    False,
                    "0x000100000000000249f0",  # ???
                    "0x",
                ],
                'type': 'entry_function_payload'
            }

            txn_dict = {"sender": str(account_address),
                        "sequence_number": str(client.get_account_sequence_number(account_address)),
                        "max_gas_amount": str(1000),
                        "gas_unit_price": str(r["gas_estimate"]),
                        "expiration_timestamp_secs": str(int(time.time()) + 100),
                        "payload": payload, "signature": {
                    "type": "ed25519_signature",
                    "public_key": f"{account.public_key()}",
                    "signature": f"{'0' * 128}",
                }}

            gas = int(self.aptos.get_gas_amount(txn_dict))

            txn_dict["max_gas_amount"] = str(int(gas + (gas * 0.1)))

            # encode this transaction
            encoded = client.encode(txn_dict)
            # sign this transaction
            signature = account.sign(encoded)
            # generate fake signature for transaction test

            txn_dict["signature"] = {
                "type": "ed25519_signature",
                "public_key": f"{account.public_key()}",
                "signature": f"{signature}",
            }

            # submit transaction
            tx = client.submit_transaction(txn_dict)

            if "hash" in str(tx):
                logger.success(
                    f"Bridged {int(usdc_balance_str) / 1000_000} USDC from Aptos to {destination_network} -> {tx['hash']}")
            else:
                logger.error(f"Failed to bridge USDC from Aptos to {destination_network} -> {tx['message']}")

        except Exception as err:
            logger.error(f"Failed to bridge USDC from Aptos -> {err}")
