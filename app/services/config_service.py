import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.database import AsyncSessionLocal
from app.models.bot import Bot

async def get_bot_config(bot_id: int):
    async with AsyncSessionLocal() as session:
        stmt = select(Bot).options(
            selectinload(Bot.fee_template),
            selectinload(Bot.exchange_template)
        ).where(Bot.id == bot_id)
        
        result = await session.execute(stmt)
        bot = result.scalars().first()
        
        if not bot:
            return None
            
        return {
            "name": bot.name,
            "fee": bot.fee_template.fee_percent if bot.fee_template else 0.0,
            "rates": {
                "usd": bot.exchange_template.usd_rate if bot.exchange_template else 1.0,
                "php": bot.exchange_template.php_rate if bot.exchange_template else 1.0,
            }
        }

async def get_bot_button_config(bot_id: int, session: AsyncSession | None = None) -> dict:
    async def _load_config(active_session: AsyncSession) -> dict:
        bot = await active_session.get(Bot, bot_id)
        if not bot or not bot.button_config:
            return {}
        try:
            return json.loads(bot.button_config)
        except Exception:
            return {}

    if session is not None:
        return await _load_config(session)

    async with AsyncSessionLocal() as active_session:
        return await _load_config(active_session)
