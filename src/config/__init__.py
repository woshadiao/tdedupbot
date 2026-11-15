"""JSON configuration for the dedup bot.

Read ``config.json`` from the process working directory. Run the bot from the
repository root so this file and relative database URLs resolve together.
"""
import json
from pathlib import Path


CONFIG_FILE = Path("config.json")
with CONFIG_FILE.open(encoding="utf-8") as config_file:
    _config = json.load(config_file)


DEDUP_TOKEN = _config["token"]
DEDUP_CUSTOMAPI = _config.get("custom_api", "https://api.telegram.org/bot")
DEDUP_REVIEWER_GROUPS = {int(chat_id) for chat_id in _config["reviewer_groups"]}
DEDUP_MAIN_BOT_IDS = {int(bot_id) for bot_id in _config["main_bot_ids"]}
DEDUP_SUPERADMIN = {int(user_id) for user_id in _config.get("superadmin", [])}

DEDUP_DB_URL = _config.get("db_url", "sqlite:///data/dedup.db")
DEDUP_PHASH_THRESHOLD = int(_config.get("phash_threshold", 8))
DEDUP_SIMHASH_THRESHOLD = int(_config.get("simhash_threshold", 16))
DEDUP_ENABLE_SIMHASH = _config.get("enable_simhash", True)
DEDUP_MIN_SIMHASH_TEXT_LEN = int(_config.get("min_simhash_text_len", 12))
