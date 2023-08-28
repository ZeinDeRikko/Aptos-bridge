from aptos_sdk.account import Account as AptosAccount
from random import uniform, randint
from eth_account import Account
from aptc import new_client
from retrying import retry
from loguru import logger
from web3 import Web3
from time import sleep
import requests
import json


from .utilities import aptos_lib
from . import useful_data


class Evm:
    def __init__(self, private_key: str):
        self.private_key = private_key

        self.account = Account.from_key(private_key)
        self.wallet_address = self.account.address

        self.useful_data = useful_data.Data()

    def get_maximum_balance_network(self, wallet_address: str) -> str or None:
        networks_to_swap = ["Polygon", "Avalanche"]

        balances = {
            "Polygon": self.get_balance_usdc(wallet_address, self.useful_data.constants["usdc_contracts"]["Polygon"],
                                             "Polygon"),
            "Avalanche": self.get_balance_usdc(wallet_address,
                                               self.useful_data.constants["usdc_contracts"]["Avalanche"], "Avalanche"),
        }

        max_balance_network = max(balances, key=balances.get)

        networks_to_swap.remove(max_balance_network)
        max_balance_network = max(balances, key=balances.get)
        max_balance = balances[max_balance_network]

        if max_balance < 1:
            logger.warning("No USDC balance in all networks.")
            return False

        return max_balance_network, balances[max_balance_network]

    @retry(stop_max_attempt_number=5, wait_fixed=2000)
    def get_balance_usdc(self, wallet_address, contract_address, network: str):
        w3 = self.get_web3_instance(self.useful_data.constants["networks"][network]["urls"])

        contract = w3.eth.contract(address=contract_address, abi=self.useful_data.constants["ERC20_ABI"])
        return contract.functions.balanceOf(wallet_address).call()

    def get_web3_instance(self, rpc_urls: list) -> Web3(Web3.HTTPProvider()) or bool:
        for rpc in rpc_urls:
            w3 = Web3(Web3.HTTPProvider(rpc))
            if w3.is_connected():
                return w3

        logger.error("Failed to connect to EVM RPC!")
        return False

    def get_gas_data(self, network: str):
        network_lower = network.lower()
        res = requests.get(
            'https://api.owlracle.info/v4/{}/gas?apikey={}'.format(network_lower,
                                                                   self.useful_data.constants["GAS_API"]))
        data = res.json()

        if len(data['speeds']) >= 2:
            second_speed = data['speeds'][1]

            # Generate a random multiplier between 1.111 and 1.297
            multiplier = uniform(1.111, 1.297)

            # Multiply the maxFeePerGas value by the random multiplier
            adjusted_max_fee_per_gas = second_speed['maxFeePerGas'] * multiplier

            return adjusted_max_fee_per_gas, second_speed['maxPriorityFeePerGas']
        else:
            return None

    def get_fee(self, aptos_contract, w3, call_params, adapter_params):
        fees = aptos_contract.functions.quoteForSend(call_params, adapter_params).call()
        native_balance = w3.eth.get_balance(self.account.address)
        return fees[0], native_balance

    def get_allowance(self, usdc_contract, account_address, stargate_address):
        return usdc_contract.functions.allowance(account_address, stargate_address).call()

    def approve_and_retry(self, account, amount, nonce, max_fee_per_gas, max_priority_fee_per_gas, w3, network,
                          usdc_contract, stargate_address, tx_url):
        approval_success = False
        approval_attempts = 0
        while not approval_success and approval_attempts < 3:
            approve_txn_hash = self.approve_usdc(account, usdc_contract, stargate_address, amount, nonce,
                                                 max_fee_per_gas, max_priority_fee_per_gas, w3)
            sleep_duration = randint(20, 60)
            logger.info(
                f'Sent USDC approve transaction {tx_url}{approve_txn_hash.hex()}, waiting {sleep_duration} seconds')
            sleep(sleep_duration)
            nonce += 1
            try:
                tx_info = w3.eth.get_transaction(approve_txn_hash)
                if tx_info is None:
                    logger.error('Transaction not found')
                else:
                    receipt = w3.eth.get_transaction_receipt(approve_txn_hash)
                    if receipt is None:
                        logger.info('Transaction not confirmed yet')
                    elif receipt['status'] == 1:
                        logger.success(f"{network} | USDC APPROVED {tx_url}{approve_txn_hash.hex()}")
                        approval_success = True
                    else:
                        logger.error(f'Transaction failed {tx_url}{approve_txn_hash.hex()}')
                        approval_attempts += 1
            except Exception as e:
                logger.error(f'Error: {e}')
                approval_attempts += 1

        if not approval_success:
            logger.error("Failed to approve USDC after 3 attempts")
            return None

    def approve_usdc(self, account, usdc_contract, stargate_address, amount, nonce, max_fee_per_gas,
                     max_priority_fee_per_gas, w3):
        approve_txn_obj = usdc_contract.functions.approve(stargate_address, int(amount))
        approve_gas_estimate = approve_txn_obj.estimate_gas({'from': account.address})
        approve_txn = approve_txn_obj.build_transaction({
            'from': account.address,
            'gas': approve_gas_estimate,
            'maxFeePerGas': int(w3.to_wei(max_fee_per_gas, "gwei")),
            'maxPriorityFeePerGas': int(w3.to_wei(max_priority_fee_per_gas, "gwei")),
            'nonce': nonce,
        })
        signed_approve_txn = w3.eth.account.sign_transaction(approve_txn, account.key)
        approve_txn_hash = w3.eth.send_raw_transaction(signed_approve_txn.rawTransaction)

        return approve_txn_hash

    def create_adapter_params(self, network: str, aptos_wallet, version: int = 2) -> bytes:
        gas_amount = randint(5000, 7000)

        if network == "Avalanche":
            native_for_dst = randint(1000000, 1900000)
        elif network == "Polygon":
            native_for_dst = randint(1000000, 1900000)

        param1_converted = Web3.to_bytes(version).rjust(2, b'\0')
        param2_converted = Web3.to_bytes(gas_amount).rjust(32, b'\0')  # uint in Solidity is 32 bytes
        param3_converted = Web3.to_bytes(native_for_dst).rjust(32, b'\0')
        param4_converted = Web3.to_bytes(hexstr=aptos_wallet.hex())

        # Concatenate the byte arrays
        adapter_params = param1_converted + param2_converted + param3_converted + param4_converted

        return adapter_params


class Aptos:
    def __init__(self, mnemonic: str):
        self.mnemonic = mnemonic

    def get_aptos_account(self):
        return AptosAccount.load_key(self.mnemonic_to_private_key())

    def get_wallet_address(self):
        return AptosAccount.load_key(self.mnemonic_to_private_key()).address()

    def get_account_balance(self):
        return new_client().get_account_balance(self.get_wallet_address())

    def mnemonic_to_private_key(self) -> hex:
        words = self.mnemonic.split(" ")
        if len(words) > 6:
            instance = aptos_lib.PublicKeyUtils(self.mnemonic)
            private_key = instance.mnemonic_to_private_key(self.mnemonic).hex()
        else:
            private_key = self.mnemonic

        return private_key

    def get_gas_amount(self, payload: dict) -> str:
        import requests

        resp = requests.post("https://rpc.ankr.com/http/aptos/v1/transactions/simulate",
                             headers={
                                 "Accept": "application/json, application/x-bcs",
                                 "Content-Type": "application/json"
                             },
                             data=json.dumps(payload))

        return resp.json()[0]["gas_used"]
