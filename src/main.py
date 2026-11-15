"""Entry point for the long-running dedup bot.

Run from the repository root with ``python -m src.main``.
"""
import logging
import sys
from pathlib import Path

# Make ``src.*`` importable when run as ``python src/main.py``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from src.bot import load_baseline, on_new_message
from src.update import update_bot
from src.config import (
    DEDUP_CUSTOMAPI,
    DEDUP_MAIN_BOT_IDS,
    DEDUP_REVIEWER_GROUPS,
    DEDUP_TOKEN,
)

logger = logging.getLogger("src.main")


async def on_init(application):
    load_baseline()
    for chat_id in DEDUP_REVIEWER_GROUPS:
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text="🥷DOMO，审核SAN，重复slayer DESU🥷",
            )
        except Exception:  # bot removed from / cannot post in this group:
            # log and keep going -- the other groups must still be served.
            logger.exception("online notice to chat %s failed", chat_id)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # Empty id sets would silently exclude every review-group submission.
    if not DEDUP_REVIEWER_GROUPS:
        raise SystemExit("config.json: reviewer_groups is empty")
    if not DEDUP_MAIN_BOT_IDS:
        raise SystemExit("config.json: main_bot_ids is empty")
    application = (
        ApplicationBuilder()
        .token(DEDUP_TOKEN)
        .base_url(DEDUP_CUSTOMAPI)
        .job_queue(None)
        .get_updates_connect_timeout(60)
        .connect_timeout(60)
        .read_timeout(60)
        .write_timeout(60)
        .get_updates_read_timeout(60)
        .get_updates_write_timeout(60)
        .post_init(on_init)
        .build()
    )
    application.add_handler(
        CommandHandler(
            "update",
            update_bot,
            filters=~filters.UpdateType.EDITED_MESSAGE & filters.ChatType.PRIVATE,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGES
            & filters.Chat(chat_id=DEDUP_REVIEWER_GROUPS),
            on_new_message,
        )
    )
    application.run_polling()
