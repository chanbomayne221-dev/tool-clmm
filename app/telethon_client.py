"""Shared Telethon client used by listener AND on-demand fetches."""
import asyncio
import logging
from typing import Optional, List, Dict, Any

from telethon import TelegramClient
from telethon.sessions import StringSession

from .config import API_ID, API_HASH, SESSION_STRING, SOURCE_CHAT_USERNAME
from .parser import parse_result
from .database import db

log = logging.getLogger(__name__)

_client: Optional[TelegramClient] = None
_lock = asyncio.Lock()
_last_fetch_ts: float = 0.0
FETCH_THROTTLE_SECONDS = 2.0  # don't hammer Telegram on every button press


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


async def fetch_latest_sessions(limit: int = 30) -> List[Dict[str, Any]]:
    """Fetch the latest result messages from SOURCE_CHAT_USERNAME and persist
    any new sessions to DB. Returns the list of newly inserted parsed sessions.
    Throttled so rapid button presses don't spam Telegram.
    """
    global _last_fetch_ts
    now = asyncio.get_event_loop().time()
    if now - _last_fetch_ts < FETCH_THROTTLE_SECONDS:
        return []
    _last_fetch_ts = now

    client = await get_client()
    if client is None:
        return []
    if not SOURCE_CHAT_USERNAME:
        return []

    inserted: List[Dict[str, Any]] = []
    try:
        entity = await client.get_entity(SOURCE_CHAT_USERNAME)
        # iter_messages yields newest first
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
        log.info("Fetched %d new sessions from @%s", len(inserted), SOURCE_CHAT_USERNAME)
    return inserted
