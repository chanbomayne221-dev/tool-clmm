"""Entrypoint."""
import asyncio
import logging
import signal
import sys

from app.config import BOT_TOKEN
from app.database import db
from app.handlers import build_application
from app.telethon_listener import run_listener


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def main():
    setup_logging()
    log = logging.getLogger("main")

    if not BOT_TOKEN:
        log.error("BOT_TOKEN missing. Set env BOT_TOKEN.")
        sys.exit(1)

    await db.init()

    app = build_application()
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=None, drop_pending_updates=True)
    log.info("Telegram bot started (polling).")

    stop_event = asyncio.Event()

    def _stop(*_):
        log.info("Signal received, stopping...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _stop)
        except NotImplementedError:
            pass

    listener_task = asyncio.create_task(run_listener(app, stop_event))

    await stop_event.wait()

    log.info("Shutting down...")
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    log.info("Bye.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
