from configparser import ConfigParser
from loguru import logger
import json
import os


def read_file(file_name: str, file_type: str, accounts_range: list) -> list:
    with open(file_name, "r") as f:
        data = [line.strip() for line in f]

    if accounts_range != ["0-0"]:
        start, end = map(int, accounts_range[0].split("-"))
        start -= 1  # Make the range one-indexed
        if end > len(data):
            logger.warning(f"Range end is greater than the file length. Adjusting range end to file length.")
            end = len(data)
        data = data[start:end]

    logger.info(f"Loaded {len(data)} {file_type}")

    return data


def read_abi(filename: str) -> dict:
    script_path = os.path.dirname(os.path.abspath(__file__))

    relative_path = filename

    file_path = os.path.join(script_path, relative_path)
    with open(file_path, "r") as f:
        return json.load(f)


def read_config():
    settings = {}
    config = ConfigParser()
    config.read('config.ini')
    settings["proposal"] = str(config["section_a"]["proposal"])
    settings["proxy_type"] = str(config['section_a']["proxy_type"])
    settings["pause_from"] = str(config['section_a']['random_pause']).split("-")[0]
    settings["pause_to"] = str(config['section_a']['random_pause']).split("-")[1]
    accounts_range = str(config['section_a']['accounts_range']).replace(' ', '')
    settings["accounts_range"] = accounts_range.split(",")
    settings["choice_ratio"] = choice_ratio(config["section_a"]["choice_ratio"])
    accounts_list = str(config['section_a']['Accounts_list']).replace(' ', '')
    settings["Accounts_list"] = [int(account) for account in accounts_list.split(",")]

    return settings


def read_config_values():
    config = read_config()
    proxy_type = config["proxy_type"]
    accounts_range = config["accounts_range"]
    choice_ratio = config["choice_ratio"]
    pause_from = config['pause_from']
    pause_to = config['pause_to']
    accounts_list = config['Accounts_list']
    return proxy_type, accounts_range, choice_ratio, pause_from, pause_to, accounts_list


def choice_ratio(choice_ratio_str):
    ratio_list = [int(x) for x in choice_ratio_str.split('-')]
    ratio_sum = sum(ratio_list)
    probabilities = [x / ratio_sum for x in ratio_list]

    return probabilities
