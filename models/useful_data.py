from .utilities import *


class Data:
    def __init__(self):
        self.proxy_type, self.accounts_range, self.choice_ratio, self.pause_from, self.pause_to, accounts_list = read_config_values()

        self.constants = self.get_constants()
        self.config = None

    def get_constants(self) -> dict:
        return {
            "networks": {
                'Polygon': {
                    'urls': ['https://polygon.llamarpc.com',
                             'https://1rpc.io/matic',
                             'https://polygon-mainnet.public.blastapi.io'],
                    'symbol': 'MATIC',
                    'tx': "https://polygonscan.com/tx/",
                    'chain_id': 109,
                },
                'Avalanche': {
                    'urls': ['https://avalanche.public-rpc.com',
                             'https://api.avax.network/ext/bc/C/rpc',
                             'https://1rpc.io/avax/c'],
                    'symbol': 'AVAX',
                    'tx': "https://snowtrace.io/tx/",
                    'chain_id': 106,
                },
            },
            "usdt_contracts": {
                'Polygon': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F',
                'Avalanche': '0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7',
            },

            "usdc_contracts": {
                'Polygon': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
                'Avalanche': '0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E',
            },
            "aptos_bridge_contracts": {
                "Polygon": "0x488863D609F3A673875a914fBeE7508a1DE45eC6",
                "Avalanche": "0xA5972EeE0C9B5bBb89a5B16D1d65f94c9EF25166",
            },
            "ERC20_ABI": [
                {
                    "constant": True,
                    "inputs": [{"name": "owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "payable": False,
                    "stateMutability": "view",
                    "type": "function",
                }
            ],
            "aptos": {
                "APTOS": "0x1::coin::CoinStore<0x1::aptos_coin::AptosCoin>",
                "APTOS_WETH": "0x1::coin::CoinStore<0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::WETH>",
                "APTOS_USDT": "0x1::coin::CoinStore<0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::USDT>",
                "APTOS_USDC": "0x1::coin::CoinStore<0xf22bede237a07e121b56d91a491eb7bcdfd1f5907926a9e58338f964a01b17fa::asset::USDC>",
                "APTOS_NODE_URL": "https://rpc.ankr.com/http/aptos/v1",
            },
            "GAS_API": "4b98374a09e34d62ac73060b33aa74c7",
            "stargate_addresses": {
                'Polygon': '0x45A01E4e04F14f7A4a6702c74187c5F6222033cd',
                'Avalanche': '0x45A01E4e04F14f7A4a6702c74187c5F6222033cd',
            },
        }
