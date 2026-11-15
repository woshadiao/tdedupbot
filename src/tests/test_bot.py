"""Offline mock test for the live-bot handler (:mod:`src.bot`).

Drives :func:`src.bot.on_new_message` with a fake ``Update`` and an async
``context.bot.get_file`` mock -- no network, no Telegram -- and checks the
*dispatch* the handler does:

- review message (vote keyboard)   -> skipped (no download, no mark)
- message from a non-main bot      -> skipped
- new photo (unknown file_unique_id) -> downloaded, stored, no mark
- same photo again (known fui)     -> fast path, no download, mark fires
- photo + caption                  -> caption not fingerprinted (no text row)
- caption text as a pure-text post -> no mark; its exact repeat -> mark fires
- mark formatting (``⚠️`` + 相似度 %)
- mark deep link: supergroup -> ``t.me/c/<bare id>/<msg id>``; basic group -> no link
- edited-message update (``update.message`` None) -> skipped, no crash
- multi-main-bot: a second configured main bot is accepted; a hit crosses bots
- multi-group: a submission in a second configured group is stored with that
  group's chat id; a repeat in another group hits the cross-group first-seen
  and its mark deep-links back into the other group
- main-bot reply (operational notice) -> skipped, never fingerprinted or stored
  (helpers must set ``reply_to_message`` explicitly -- MagicMock would
  otherwise auto-create a truthy value and exclude every message)
- media album: a sibling item (same chat + media_group_id) is not marked and
  is not stored, but its fui joins the cache; the same group id in another
  chat still marks

Run from the repository root with ``python src/tests/test_bot.py``.
"""
import asyncio
import io
import json
import os
import sys
import tempfile
from itertools import count
from unittest.mock import MagicMock

# Own throwaway JSON config and DB before importing ``src.bot``.
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_workdir = tempfile.mkdtemp()
_db = os.path.join(_workdir, "dedup_bot.db")
with open(os.path.join(_workdir, "config.json"), "w", encoding="utf-8") as config_file:
    json.dump({
        "token": "123:ABC",
        "reviewer_groups": [100, -1002345678901],
        "main_bot_ids": [99999, 88888],
        "superadmin": [],
        "db_url": f"sqlite:///{_db}",
    }, config_file)
os.chdir(_workdir)
sys.path.insert(0, _project_root)

from PIL import Image, ImageDraw  # noqa: E402

from src.database import SubmissionContent, db as dedup_db  # noqa: E402
import src.bot as bot  # noqa: E402

PASS, FAIL = [], []
MAIN_BOT = 99999
BOT_B = 88888  # second configured main bot (matches the env comma list)
GROUP_B = -1002345678901  # second configured group (supergroup id, bare 2345678901)


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name: <30}{detail}")


def _green_png():
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    ImageDraw.Draw(img).ellipse([30, 30, 170, 170], fill=(0, 120, 0))
    b = io.BytesIO()
    img.convert("RGB").save(b, format="PNG")
    return b.getvalue()


def _blue_png():
    # a *square*, not an ellipse: the same blob shape would land within the
    # pHash threshold of ``_green_png`` and wrongly mark the caption test photo
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([40, 40, 160, 160], fill=(0, 0, 200))
    b = io.BytesIO()
    img.convert("RGB").save(b, format="PNG")
    return b.getvalue()


def _black_png():
    # solid black: farthest possible from the white-background images above,
    # so its pHash can never land within threshold of a stored row
    img = Image.new("RGB", (200, 200), (0, 0, 0))
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


def _album_png():
    # two black bars with a white center gap: low-frequency layout far from
    # the centered ellipse/rectangle of the images above
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 90, 190], fill=(0, 0, 0))
    draw.rectangle([110, 10, 190, 190], fill=(0, 0, 0))
    b = io.BytesIO()
    img.convert("RGB").save(b, format="PNG")
    return b.getvalue()


_ids = count(1)


def _photosize(file_id, fui, size):
    p = MagicMock()
    p.file_id = file_id
    p.file_unique_id = fui
    p.file_size = size
    return p


def _photo(file_id, fui, main_bot=True, keyboard=None, caption=None,
           chat_id=100, sender_id=None, reply_to=None, media_group_id=None):
    # ``message.photo`` is a tuple of PhotoSize (sizes); the handler picks the
    # largest via ``max(..., key=file_size)``.
    photo = (_photosize(file_id, fui, 100), _photosize(file_id, fui, 5000))
    m = MagicMock()
    m.photo = photo
    m.video = None
    m.animation = None
    m.sticker = None
    m.document = None
    m.caption = caption  # None -> only the photo is fingerprintable
    m.text = None
    m.reply_markup = keyboard
    m.reply_to_message = reply_to
    m.from_user = MagicMock(
        id=sender_id if sender_id is not None else (MAIN_BOT if main_bot else 12345)
    )
    m.chat = MagicMock(id=chat_id)
    m.media_group_id = media_group_id
    m.message_id = next(_ids)
    return m


def _text(text, main_bot=True, keyboard=None, chat_id=100, sender_id=None,
          reply_to=None):
    m = MagicMock()
    m.photo = None
    m.video = None
    m.animation = None
    m.sticker = None
    m.document = None
    m.caption = None
    m.text = text
    m.reply_markup = keyboard
    m.reply_to_message = reply_to
    m.from_user = MagicMock(
        id=sender_id if sender_id is not None else (MAIN_BOT if main_bot else 12345)
    )
    m.chat = MagicMock(id=chat_id)
    m.media_group_id = None
    m.message_id = next(_ids)
    return m


class _Bot:
    """Stands in for ``context.bot``: serves ``get_file``, records downloads."""

    def __init__(self, files):
        self.files = files
        self.downloads = []

    async def get_file(self, file_id):
        self.downloads.append(file_id)
        data = self.files[file_id]
        f = MagicMock()
        async def _dl(out, **_):
            out.write(data)
        f.download_to_memory = _dl
        return f


class _Ctx:
    pass


async def main_async():
    album_png = _album_png()  # same bytes under a second file id: pHash hit
    cbot = _Bot({
        "green.png": _green_png(),
        "blue.png": _blue_png(),
        "black.png": _black_png(),
        "album.png": album_png,
        "album-copy.png": album_png,
    })
    context = _Ctx()
    context.bot = cbot
    bot.load_baseline()

    def capture(msg):
        marks = []
        async def _capture(text, **kwargs):
            marks.append(text)
        msg.reply_text = _capture
        return marks

    # 1. review message (vote keyboard) -> skipped
    m = _photo("review.png", "fui-review", keyboard=["btn"])
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("review msg: no download", "review.png" not in cbot.downloads)
    check("review msg: no mark", not marks)

    # 2. non-main-bot message -> skipped
    m = _photo("other.png", "fui-other", main_bot=False)
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("non-main-bot: no download", "other.png" not in cbot.downloads)
    check("non-main-bot: no mark", not marks)

    # 3. new photo (slow path) -> downloaded + stored, no mark
    cbot.downloads.clear()
    m = _photo("green.png", "fui-green-1")
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("slow path: downloaded once", cbot.downloads == ["green.png"])
    check("slow path: no mark", not marks)

    # 4. same photo again (fast path) -> no download, mark fires
    cbot.downloads.clear()
    m = _photo("green.png", "fui-green-1")
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("fast path: no download", cbot.downloads == [])
    check("fast path: mark fires", len(marks) == 1)
    check("mark format",
          bool(marks) and "⚠️" in marks[0] and "相似度" in marks[0])

    # 5. photo WITH caption -> caption must NOT be fingerprinted (media
    #    submissions do not participate in text dedup)
    cbot.downloads.clear()
    m = _photo("blue.png", "fui-blue-1", caption="你好世界")
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("photo+caption: downloaded, no mark",
          cbot.downloads == ["blue.png"] and not marks)
    text_rows = dedup_db.select(SubmissionContent, SubmissionContent.type == "text")
    check("photo+caption: no text row stored", len(text_rows) == 0)

    # 6. the same text as a pure-text submission -> no mark (the caption was
    #    never stored in the text baseline); it is stored as a fresh row
    cbot.downloads.clear()
    m = _text("你好世界")
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("caption text as pure post: no mark", not marks)
    text_rows = dedup_db.select(SubmissionContent, SubmissionContent.type == "text")
    check("pure text: stored as text row", len(text_rows) == 1)

    # 7. exact repeat of that pure text -> mark (pure-text dedup still works)
    cbot.downloads.clear()
    m = _text("你好世界")
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("pure text repeat: mark fires", len(marks) == 1)

    # 8. mark links the original (first occurrence) message when the chat is
    #    a supergroup (-100 prefix -> bare-id t.me/c deep link)
    row = {"source_chat_id": -1001234567890, "source_message_id": 4412,
           "first_seen_date": "2025-01-01 12:00"}
    mark = bot._make_mark([(row, 0, "exact")])
    check("mark: original-message deep link",
          "https://t.me/c/1234567890/4412" in mark and "#4412" in mark)

    # 9. basic group (no -100 prefix) has no public deep link -> plain ref
    row = {"source_chat_id": -99999, "source_message_id": 7,
           "first_seen_date": "2025-01-01 12:00"}
    mark = bot._make_mark([(row, 0, "exact")])
    check("mark: non-supergroup no link",
          "https://t.me/" not in mark and "#7" in mark)

    # 10. edited-message / non-message update: ``update.message`` is None ->
    #     skipped, no crash (regression for the AttributeError in production)
    cbot.downloads.clear()
    await bot.on_new_message(MagicMock(message=None), context)
    check("non-message update: skipped, no crash", cbot.downloads == [])

    # 11. second main bot in the author set -> accepted; a repeat submitted by
    #     the first main bot hits its row (matching crosses main bots)
    cbot.downloads.clear()
    m = _photo("black.png", "fui-black-1", sender_id=BOT_B)
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("second main bot: slow path stored, no mark",
          cbot.downloads == ["black.png"] and not marks)
    cbot.downloads.clear()
    m = _photo("black.png", "fui-black-1", sender_id=MAIN_BOT)
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("second main bot: cross-bot fast-path mark",
          cbot.downloads == [] and len(marks) == 1)

    # 12. second configured group: a submission there is processed (no mark on
    #     first sight) and its row carries that group's chat id
    cbot.downloads.clear()
    m = _text("第二群的首发文本", chat_id=GROUP_B)
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("group B: pure text stored, no mark", not marks)
    g2_rows = dedup_db.select(
        SubmissionContent,
        SubmissionContent.source_chat_id == GROUP_B,
        SubmissionContent.type == "text",
    )
    check("group B: row carries group B chat id", len(g2_rows) == 1)

    # 13. cross-group hit: the same text submitted in group 100 matches the
    #     group-B first occurrence, and the mark deep-links back into group B
    cbot.downloads.clear()
    m = _text("第二群的首发文本")  # group 100 by default
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    g2_msg = g2_rows[0]["source_message_id"]
    check("cross-group: hit references group B first-seen",
          len(marks) == 1
          and f"https://t.me/c/2345678901/{g2_msg}" in marks[0]
          and f"#{g2_msg}" in marks[0])

    # 14. main-bot REPLY (operational notice like "✅ 已添加备注") -> skipped:
    #     never downloaded / fingerprinted / stored (content posts are always
    #     top-level, notices are always replies)
    cbot.downloads.clear()
    m = _photo("blue.png", "fui-reply-1", reply_to="review-message")
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("main-bot reply: no download, no mark",
          cbot.downloads == [] and not marks)
    n_text_rows = len(dedup_db.select(
        SubmissionContent, SubmissionContent.type == "text"))
    cbot.downloads.clear()
    m = _text("✅ 已添加备注", reply_to="review-message")
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("main-bot reply notice: no mark", not marks)
    n_after = len(dedup_db.select(
        SubmissionContent, SubmissionContent.type == "text"))
    check("main-bot reply notice: no text row stored",
          n_after == n_text_rows)

    # 15. one media album (same chat + media_group_id): a copy of the album
    #     photo is NOT marked as a duplicate, but its fui still joins the
    #     cache; the same group id in another chat is a different album
    #     and still marks.
    cbot.downloads.clear()
    m = _photo("album.png", "fui-album-1", media_group_id="album-77")
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    album_rows = dedup_db.select(
        SubmissionContent,
        SubmissionContent.file_unique_id == "fui-album-1",
    )
    check("album: first item stored, no mark", not marks)
    check("album: media group id stored",
          len(album_rows) == 1
          and album_rows[0]["media_group_id"] == "album-77")

    cbot.downloads.clear()
    m = _photo("album-copy.png", "fui-album-2", media_group_id="album-77")
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("album: same-group repeat: no mark", not marks)
    check("album: same-group repeat not stored",
          not dedup_db.select(
              SubmissionContent,
              SubmissionContent.file_unique_id == "fui-album-2",
          ))
    check("album: same-group fui still cached",
          "fui-album-2" in bot.baseline.fui_rows)

    cbot.downloads.clear()
    m = _photo("album-copy.png", "fui-album-2", chat_id=GROUP_B,
               media_group_id="album-77")
    marks = capture(m)
    await bot.on_new_message(MagicMock(message=m), context)
    check("album: same id in other chat still marks", len(marks) == 1)
    return len(PASS) + len(FAIL)


def main():
    print("P5 handler mock (src.bot.on_new_message)\n")
    total = asyncio.run(main_async())
    print(f"\n{len(PASS)}/{total} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
