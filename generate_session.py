"""Helper: generate a SESSION_STRING for Telethon. Run locally once."""
import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    api_id = int(input("API_ID: ").strip())
    api_hash = input("API_HASH: ").strip()
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        print("\n=== SESSION_STRING ===\n")
        print(client.session.save())
        print("\nLưu vào env SESSION_STRING trên Render.")


if __name__ == "__main__":
    asyncio.run(main())
