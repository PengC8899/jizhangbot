import asyncio
from app.core.database import AsyncSessionLocal
from app.models.group import GroupConfig
from sqlalchemy import select, update, and_

async def main():
    async with AsyncSessionLocal() as session:
        # Check current
        stmt = select(GroupConfig).where(GroupConfig.group_id == -5207621278)
        result = await session.execute(stmt)
        config = result.scalars().first()
        print(f"Current fee: {config.fee_percent}, usd_rate: {config.usd_rate}")

        # Try update
        stmt = update(GroupConfig).where(
            and_(GroupConfig.group_id == -5207621278, GroupConfig.bot_id == 1)
        ).values(fee_percent=7.0, usd_rate=120.0)
        await session.execute(stmt)
        await session.commit()

        # Check again
        stmt = select(GroupConfig).where(GroupConfig.group_id == -5207621278)
        result = await session.execute(stmt)
        config = result.scalars().first()
        print(f"New fee: {config.fee_percent}, usd_rate: {config.usd_rate}")

asyncio.run(main())
