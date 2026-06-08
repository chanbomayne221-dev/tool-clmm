"""Telethon userbot listener: reads source chat in realtime.
Uses the shared client from telethon_client so on-demand fetches and
the realtime listener share a single Telegram session.
"""
import asyncio
import logging

from telethon import events

from .config import SOURCE_CHAT_ID, SOURCE_CHAT_USERNAME, SEND_COOLDOWN_SECONDS
from .database import db
from .parser import parse_result
from .prediction_service import (
    build_next_prediction_message,
    record_prediction_outcome_if_any,
)
from .telethon_client import get_client

log = logging.getLogger(__name__)

_last_send_ts = 0.0


async def _maybe_broadcast_prediction(bot_app):
    global _last_send_ts
    res = await build_next_prediction_message()
    if not res:
        return
    next_session, msg, label, conf = res

    groups = await db.auto_groups()
    if not groups:
        return

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
        return
    log.info(
        "New session #%s dice=%s total=%s %s %s",
        parsed["session_number"], parsed["dice_values"], parsed["total"],
        parsed["tai_xiu"], parsed["chan_le"],
    )
    await record_prediction_outcome_if_any(parsed)
    await _maybe_broadcast_prediction(bot_app)


async def run_listener(bot_app, stop_event: asyncio.Event):
    """Run the Telethon listener (auto-reconnect loop) on the shared client."""
    while not stop_event.is_set():
        client = await get_client()
        if client is None:
            log.error("Telethon not configured / not authorized. Retrying in 30s.")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass
            continue

        try:
            target_chat_id = SOURCE_CHAT_ID
            target_entity = None
            if target_chat_id is None and SOURCE_CHAT_USERNAME:
                try:
                    target_entity = await client.get_entity(SOURCE_CHAT_USERNAME)
                    target_chat_id = target_entity.id
                except Exception as e:
                    log.exception("Cannot resolve @%s: %s", SOURCE_CHAT_USERNAME, e)

            @client.on(events.NewMessage())
            async def _on_new(event):
                try:
                    if target_chat_id is not None and event.chat_id != target_chat_id:
                        # Telegram chat ids for channels often start with -100; be lenient
                        if abs(event.chat_id) != abs(target_chat_id):
                            return
                    await _handle_text(event.raw_text or "", bot_app)
                except Exception as e:
                    log.exception("Handler error: %s", e)

            @client.on(events.MessageEdited())
            async def _on_edit(event):
                try:
                    if target_chat_id is not None and event.chat_id != target_chat_id:
                        if abs(event.chat_id) != abs(target_chat_id):
                            return
                    await _handle_text(event.raw_text or "", bot_app)
                except Exception as e:
                    log.exception("Edit handler error: %s", e)

            me = await client.get_me()
            log.info("Telethon listener active as %s (id=%s); source=%s",
                     getattr(me, "username", None), me.id,
                     target_chat_id or SOURCE_CHAT_USERNAME)

            disconnected = client.disconnected
            done, pending = await asyncio.wait(
                {asyncio.create_task(stop_event.wait()),
                 asyncio.create_task(disconnected)},
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
        await asyncio.sleep(5)
