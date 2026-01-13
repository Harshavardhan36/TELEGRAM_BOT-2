import asyncio
from telegram import Bot

BOT_TOKEN = "8461367172:AAGnqmsLbpfRLLGRNqQztKbU0aBek5lJwf8"

async def main():
    bot = Bot(token=BOT_TOKEN)
    updates = await bot.get_updates()

    for u in updates:
        if u.message:
            print(u.message.chat.id)

asyncio.run(main())

