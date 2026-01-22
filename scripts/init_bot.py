import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal
from app.models.bot import Bot

async def add_bot(token: str, name: str = "JishuBot"):
    async with AsyncSessionLocal() as session:
        # Check if exists
        from sqlalchemy import select
        stmt = select(Bot).where(Bot.token == token)
        result = await session.execute(stmt)
        existing = result.scalars().first()
        
        if existing:
            print(f"Bot {name} already exists with ID: {existing.id}")
            return

        new_bot = Bot(token=token, name=name, status="active")
        session.add(new_bot)
        await session.commit()
        print(f"Successfully added bot: {name}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python init_bot.py <BOT_TOKEN> [BOT_NAME]")
        sys.exit(1)
    
    token = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "JishuBot"
    
    asyncio.run(add_bot(token, name))
