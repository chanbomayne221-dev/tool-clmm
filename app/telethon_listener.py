"""Telethon userbot listener: reads source chat in realtime."""
import asyncio
import logging
from typing import Optional

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from .config import API_ID, API_HASH, SESSION_STRING, SOURCE_CHAT_ID, SEND_COOLDOWN_SECONDS
from .database import db
from .parser import parse_result
from .prediction_service import build_next_prediction_message, record_prediction_outcome_if_any

log = logging.getLogger(__name__)

_last_send_ts = 0.0


async def _maybe_broadcast_prediction(bot_app):
    """Build prediction for next session and send to all auto groups."""
    global _last_send_ts
    res = await build_next_prediction_message()
    if not res:
        return
    next_session, msg, label, conf = res

    # dedupe: only insert if new
    inserted = await db.insert_prediction(next_session, label, conf)
    if not inserted:
        log.info("Prediction for #%s already sent, skip.", next_session)
        return

    groups = await db.auto_groups()
    if not groups:
        return

    # anti-spam delay
    now = asyncio.get_event_loop().time()
    delta = now - _last_send_ts
    if delta < SEND_COOLDOWN_SECONDS:
        await asyncio.sleep(SEND_COOLDOWN_SECONDS - delta)

    for chat_id in groups:
        try:
            await bot_app.bot.send_message(chat_id, msg)
            await asyncio.sleep(0.4)
        except Exception as e:
            log.exception("Failed sending to %s: %s", chat_id, e)
    _last_send_ts = asyncio.get_event_loop().time()


async def _handle_text(text: str, bot_app):
    parsed = parse_result(text)
    if not parsed:
        return
    inserted = await db.insert_session(
        session_number=parsed["session_number"],
        dice_values=parsed["dice_values"],
        total=parsed["total"],
        tai_xiu=parsed["tai_xiu"],
        chan_le=parsed["chan_le"],
        timestamp=parsed["timestamp"],
    )
    if not inserted:
        return  # duplicate, ignore
    log.info(
        "New session #%s dice=%s total=%s %s %s",
        parsed["session_number"], parsed["dice_values"], parsed["total"],
        parsed["tai_xiu"], parsed["chan_le"],
    )
    # Grade previous prediction if it targeted this session
    await record_prediction_outcome_if_any(parsed)
    # Build & broadcast next prediction
    await _maybe_broadcast_prediction(bot_app)


async def run_listener(bot_app, stop_event: asyncio.Event):
    """Run the Telethon client with auto-reconnect loop."""
    if not API_ID or not API_HASH or not SESSION_STRING:
        log.error("Missing API_ID/API_HASH/SESSION_STRING. Telethon listener disabled.")
        return

    while not stop_event.is_set():
        client: Optional[TelegramClient] = None
        try:
            client = TelegramClient(
                StringSession(SESSION_STRING), API_ID, API_HASH,
                auto_reconnect=True, connection_retries=999, retry_delay=5,
            )

            @client.on(events.NewMessage())
            async def _on_new(event):
                try:
                    if SOURCE_CHAT_ID is not None and event.chat_id != SOURCE_CHAT_ID:
                        return
                    text = event.raw_text or ""
                    await _handle_text(text, bot_app)
                except Exception as e:
                    log.exception("Handler error: %s", e)

            @client.on(events.MessageEdited())
            async def _on_edit(event):
                try:
                    if SOURCE_CHAT_ID is not None and event.chat_id != SOURCE_CHAT_ID:
                        return
                    text = event.raw_text or ""
                    await _handle_text(text, bot_app)
                except Exception as e:
                    log.exception("Edit handler error: %s", e)

            await client.start()
            me = await client.get_me()
            log.info("Telethon connected as %s (id=%s)", getattr(me, "username", None), me.id)
            log.info("Listening on SOURCE_CHAT_ID=%s", SOURCE_CHAT_ID)

            # Wait until stop_event OR disconnect
            disconnected = client.disconnected
            done, pending = await asyncio.wait(
                {asyncio.create_task(stop_event.wait()), asyncio.create_task(disconnected)},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()

            if stop_event.is_set():
                log.info("Stop requested; shutting down listener.")
                break
            log.warning("Telethon disconnected, reconnecting in 5s...")
        except Exception as e:
            log.exception("Listener crashed: %s; restart in 5s", e)
        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        await asyncio.sleep(5)
