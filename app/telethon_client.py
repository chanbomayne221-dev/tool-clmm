"""Shared Telethon client used by listener AND on-demand fetches.

The source room is dynamic and lives in DB (settings.source_chat).
Admins change it at runtime via the "📡 Nhóm check LS" menu.
"""
import asyncio
import logging
from typing import Optional, List, Dict, Any, Tuple, Union

from telethon import TelegramClient
from telethon.sessions import StringSession

from .config import (
    API_ID,
    API_HASH,
    SESSION_STRING,
    DEFAULT_SOURCE_CHAT_USERNAME,
    DEFAULT_SOURCE_CHAT_ID,
)
from .parser import parse_result
from .database import db

log = logging.getLogger(__name__)

_client: Optional[TelegramClient] = None
_lock = asyncio.Lock()
_last_fetch_ts: float = 0.0
FETCH_THROTTLE_SECONDS = 2.0

SETTING_KEY = "source_chat"


async def get_client() -> Optional[TelegramClient]:
    """Return a connected shared Telethon client (or None if not configured)."""
    global _client
    if not API_ID or not API_HASH or not SESSION_STRING:
        return None
    async with _lock:
        if _client is None:
            _client = TelegramClient(
                StringSession(SESSION_STRING), API_ID, API_HASH,
                auto_reconnect=True, connection_retries=999, retry_delay=5,
            )
        if not _client.is_connected():
            try:
                await _client.connect()
            except Exception as e:
                log.exception("Telethon connect failed: %s", e)
                return None
        if not await _client.is_user_authorized():
            log.error("Telethon session not authorized.")
            return None
    return _client


def _normalize_input(raw: str) -> Union[str, int, None]:
    """Accept link / username / numeric id and normalize for Telethon."""
    if not raw:
        return None
    s = raw.strip()
    # https://t.me/xxx or t.me/xxx
    if "t.me/" in s:
        s = s.split("t.me/", 1)[1].split("/")[0].split("?")[0]
    s = s.lstrip("@").strip()
    if not s:
        return None
    # numeric id (possibly -100...)
    if s.lstrip("-").isdigit():
        return int(s)
    return s


async def get_source() -> Optional[Union[str, int]]:
    """Return the saved source chat (id or username), falling back to defaults."""
    val = await db.get_setting(SETTING_KEY)
    if val:
        try:
            return int(val)
        except ValueError:
            return val
    if DEFAULT_SOURCE_CHAT_ID is not None:
        return DEFAULT_SOURCE_CHAT_ID
    if DEFAULT_SOURCE_CHAT_USERNAME:
        return DEFAULT_SOURCE_CHAT_USERNAME
    return None


async def set_source(value: Union[str, int]):
    await db.set_setting(SETTING_KEY, str(value))


async def verify_source(raw: str) -> Tuple[bool, str, Optional[Union[str, int]]]:
    """Verify that we can read the room. Returns (ok, info_text, normalized).

    Tries to fetch latest 5–10 messages so we know reading works.
    """
    norm = _normalize_input(raw)
    if norm is None:
        return False, "Không nhận diện được link / username / ID.", None
    client = await get_client()
    if client is None:
        return False, "Telethon chưa cấu hình hoặc session không hợp lệ.", None
    try:
        entity = await client.get_entity(norm)
    except Exception as e:
        log.exception("verify_source get_entity failed: %s", e)
        return False, f"Không tìm thấy room: {e.__class__.__name__}", None
    try:
        count = 0
        async for _msg in client.iter_messages(entity, limit=10):
            count += 1
        if count == 0:
            return False, "Đọc được room nhưng không có message nào.", None
    except Exception as e:
        log.exception("verify_source iter_messages failed: %s", e)
        return False, f"Không có quyền đọc tin nhắn: {e.__class__.__name__}", None

    display = getattr(entity, "username", None)
    if display:
        normalized: Union[str, int] = display
    else:
        normalized = entity.id
    return True, f"OK ({count} messages)", normalized


async def fetch_latest_sessions(limit: int = 30) -> List[Dict[str, Any]]:
    """Fetch latest result messages from the configured source room."""
    global _last_fetch_ts
    now = asyncio.get_event_loop().time()
    if now - _last_fetch_ts < FETCH_THROTTLE_SECONDS:
        return []
    _last_fetch_ts = now

    client = await get_client()
    if client is None:
        return []
    source = await get_source()
    if source is None:
        return []

    inserted: List[Dict[str, Any]] = []
    try:
        entity = await client.get_entity(source)
        async for msg in client.iter_messages(entity, limit=limit):
            text = msg.message or getattr(msg, "raw_text", "") or ""
            parsed = parse_result(text)
            if not parsed:
                continue
            ok = await db.insert_session(
                session_number=parsed["session_number"],
                dice_values=parsed["dice_values"],
                total=parsed["total"],
                tai_xiu=parsed["tai_xiu"],
                chan_le=parsed["chan_le"],
                timestamp=parsed["timestamp"],
            )
            if ok:
                inserted.append(parsed)
    except Exception as e:
        log.exception("fetch_latest_sessions failed: %s", e)
    if inserted:
        log.info("Fetched %d new sessions from %s", len(inserted), source)
    return inserted
