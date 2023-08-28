from loguru import logger
from time import sleep
import urllib3
import sys

from models import aptos_bridge


def main():
    urllib3.disable_warnings()
    logger.remove()
    logger.add(sys.stdout, colorize=True,
               format="   <light-cyan>{time:HH:mm:ss}</light-cyan> | <level> {level: <8}</level> | - <white>{"
                      "message}</white>")

    with open("data/evm_private_keys.txt", "r") as f:
        evm_privates = [line.strip() for line in f]
    with open("data/aptos_mnemonic.txt", "r") as f:
        aptos_privates = [line.strip() for line in f]

    action = input("Your choice: \n1) Swap to Aptos + claim\n2) LiquidSwap + swap from aptos\n\n>> ")
    instance = aptos_bridge.AptosBridge(evm_privates[0], aptos_privates[0])

    match action:
        case "1":
            # Swap and claim
            success = instance.usdc_to_aptos()
            if success:
                sleep(15)
                instance.claim_on_aptos()

        case "2":
            # Swap and claim
            instance.liquid_swap_usdc_to_aptos()
            sleep(30)
            instance.usdc_from_aptos()


if __name__ == "__main__":
    main()
