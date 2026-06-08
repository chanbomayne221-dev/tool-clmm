"""Telethon userbot listener: reads source chat in realtime.

Source chat is dynamic (from DB). When admin changes it via the
"📡 Nhóm check LS" menu, the listener resubscribes automatically.
"""
import asyncio
import logging

from telethon import events

from .config import SEND_COOLDOWN_SECONDS
from .database import db
from .parser import parse_result
from .prediction_service import (
    build_next_prediction_message,
    record_prediction_outcome_if_any,
)
from .telethon_client import get_client, get_source

log = logging.getLogger(__name__)

_last_send_ts = 0.0


async def _maybe_broadcast_prediction(bot_app):
    global _last_send_ts
    # Only broadcast when admin has enabled auto for at least one group.
    if (await db.get_setting("auto_enabled")) != "1":
        return
    groups = await db.auto_groups()
    if not groups:
        return

    res = await build_next_prediction_message()
    if not res:
        return
    _next_session, msg, _label, _conf = res

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
    """Listener loop. Re-resolves the source room each iteration so admin
    changes via 📡 Nhóm check LS take effect without restarting the bot.
    """
    while not stop_event.is_set():
        client = await get_client()
        if client is None:
            log.error("Telethon not configured / not authorized. Retrying in 30s.")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass
            continue

        source = await get_source()
        target_chat_id = None
        if source is not None:
            try:
                entity = await client.get_entity(source)
                target_chat_id = entity.id
            except Exception as e:
                log.exception("Cannot resolve source %s: %s", source, e)

        if target_chat_id is None:
            log.warning("No source room configured. Waiting 15s.")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=15)
            except asyncio.TimeoutError:
                pass
            continue

        # Snapshot the current source so we can detect admin changes.
        current_source_snapshot = str(source)

        @client.on(events.NewMessage())
        async def _on_new(event):
            try:
                if abs(event.chat_id) != abs(target_chat_id):
                    return
                await _handle_text(event.raw_text or "", bot_app)
            except Exception as e:
                log.exception("Handler error: %s", e)

        @client.on(events.MessageEdited())
        async def _on_edit(event):
            try:
                if abs(event.chat_id) != abs(target_chat_id):
                    return
                await _handle_text(event.raw_text or "", bot_app)
            except Exception as e:
                log.exception("Edit handler error: %s", e)

        try:
            me = await client.get_me()
            log.info("Telethon listener active as %s (id=%s); source=%s",
                     getattr(me, "username", None), me.id, source)

            async def _watch_source_change():
                while not stop_event.is_set():
                    await asyncio.sleep(5)
                    new_src = await get_source()
                    if str(new_src) != current_source_snapshot:
                        log.info("Source changed: %s -> %s; rebinding listener.",
                                 current_source_snapshot, new_src)
                        return

            disconnected = client.disconnected
            done, pending = await asyncio.wait(
                {
                    asyncio.create_task(stop_event.wait()),
                    asyncio.create_task(disconnected),
                    asyncio.create_task(_watch_source_change()),
                },
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
        except Exception as e:
            log.exception("Listener crashed: %s; restart in 5s", e)
        finally:
            # Remove our handlers before next loop iteration so we don't stack.
            try:
                client.remove_event_handler(_on_new)
                client.remove_event_handler(_on_edit)
            except Exception:
                pass

        if stop_event.is_set():
            log.info("Stop requested; shutting down listener.")
            break
        await asyncio.sleep(2)
