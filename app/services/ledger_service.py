from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.group import GroupConfig, Operator, LedgerRecord
from app.models.bot import Bot
from datetime import datetime, time, timedelta
from app.core.cache import cache_service
from app.core.utils import get_now


class LedgerService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_group_config(self, group_id: int, bot_id: int, group_name: str = None) -> GroupConfig:
        # 1. Try Cache
        cached_data = await cache_service.get_group_config(group_id, bot_id)
        if cached_data:
            # We need to return an object that behaves like GroupConfig
            # Ideally we return a detached instance or a Pydantic model
            # For quick integration, we'll return a pseudo-object or fetch from DB if complex logic needed
            # But "get_group_config" usually returns an attached instance for updates.
            # If we just need read access, cache is fine.
            # If we need to UPDATE, we must fetch from DB.
            # This method is used for both. This is a design challenge.
            
            # Strategy: If we are in a read-heavy context, use cache.
            # But the current signature returns a SQLAlchemy Model which is often used for updates.
            # To be safe and simple: Use cache only for 'is_active' checks or read-only displays.
            # But the request is to "reduce DB pressure".
            
            # Let's keep it simple: If cache exists, we return a detached object.
            # BUT: detached objects can't be used for `session.commit()` updates directly without merging.
            # So, for now, let's ONLY use cache for `is_group_active` check which is the most frequent call.
            pass

        stmt = select(GroupConfig).where(
            and_(GroupConfig.group_id == group_id, GroupConfig.bot_id == bot_id)
        )
        result = await self.session.execute(stmt)
        config = result.scalars().first()
        if not config:
            config = GroupConfig(group_id=group_id, bot_id=bot_id, group_name=group_name)
            self.session.add(config)
            await self.session.commit()
            await self.session.refresh(config)
        elif group_name and config.group_name != group_name:
            # Update group name if changed
            config.group_name = group_name
            await self.session.commit()
            await cache_service.invalidate_group_config(group_id, bot_id)
        
        # Update Cache (Async, fire and forget logic ideally, but here await is fine)
        # We need to convert config to dict
        config_dict = {c.name: getattr(config, c.name) for c in config.__table__.columns}
        await cache_service.set_group_config(group_id, bot_id, config_dict)
        
        return config

    async def is_group_active(self, group_id: int, bot_id: int) -> bool:
        # Optimized: Check Cache First
        cached = await cache_service.get_group_config(group_id, bot_id)
        if cached:
            return cached.get('is_active', False)
            
        config = await self.get_group_config(group_id, bot_id)
        return config.is_active

    async def start_recording(self, group_id: int, bot_id: int):
        stmt = update(GroupConfig).where(
            and_(GroupConfig.group_id == group_id, GroupConfig.bot_id == bot_id)
        ).values(is_active=True, active_start_time=get_now())
        await self.session.execute(stmt)
        await self.session.commit()
        # Invalidate Cache
        await cache_service.invalidate_group_config(group_id, bot_id)

    async def stop_recording(self, group_id: int, bot_id: int):
        stmt = update(GroupConfig).where(
            and_(GroupConfig.group_id == group_id, GroupConfig.bot_id == bot_id)
        ).values(is_active=False)
        await self.session.execute(stmt)
        await self.session.commit()
        # Invalidate Cache
        await cache_service.invalidate_group_config(group_id, bot_id)

    async def add_operator(self, group_id: int, user_id: int, username: str):
        # Check if exists
        stmt = select(Operator).where(
            and_(Operator.group_id == group_id, Operator.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        if result.scalars().first():
            return # Already exists
        
        op = Operator(group_id=group_id, user_id=user_id, username=username)
        self.session.add(op)
        await self.session.commit()

    async def remove_operator(self, group_id: int, user_id: int):
        stmt = delete(Operator).where(
            and_(Operator.group_id == group_id, Operator.user_id == user_id)
        )
        await self.session.execute(stmt)
        await self.session.commit()
    
    async def get_operators(self, group_id: int):
        stmt = select(Operator).where(Operator.group_id == group_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def record_transaction(self, bot_id: int, group_id: int, type: str, amount: float, 
                               operator_id: int, operator_name: str, original_text: str):
        # Get current config for snapshots
        config = await self.get_group_config(group_id, bot_id)
        
        record = LedgerRecord(
            bot_id=bot_id,
            group_id=group_id,
            type=type,
            amount=amount,
            operator_id=operator_id,
            operator_name=operator_name,
            original_text=original_text,
            fee_applied=config.fee_percent,
            usd_rate_snapshot=config.usd_rate,
            created_at=get_now()
        )
        self.session.add(record)
        await self.session.commit()
        return record

    async def get_recent_records(self, group_id: int, bot_id: int, limit: int = 5, record_type: str = None):
        stmt = select(LedgerRecord).where(
            and_(LedgerRecord.group_id == group_id, LedgerRecord.bot_id == bot_id)
        )
        
        if record_type:
            stmt = stmt.where(LedgerRecord.type == record_type)
            
        stmt = stmt.order_by(LedgerRecord.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_today_records(self, group_id: int, bot_id: int):
        # Logic: 4AM to 4AM next day (Beijing Time)
        now = get_now()
        if now.hour < 4:
            start_date = now.date() - timedelta(days=1)
        else:
            start_date = now.date()
            
        # Create timezone-aware boundaries
        tz = now.tzinfo
        start_time = datetime.combine(start_date, time(4, 0))
        if tz:
            start_time = tz.localize(start_time)
            
        end_time = start_time + timedelta(hours=24)
        
        stmt = delete(LedgerRecord).where(
            and_(
                LedgerRecord.group_id == group_id,
                LedgerRecord.bot_id == bot_id,
                LedgerRecord.created_at >= start_time,
                LedgerRecord.created_at < end_time
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_daily_summary(self, group_id: int, bot_id: int):
        # Logic: 4AM to 4AM next day (Beijing Time)
        now = get_now()
        if now.hour < 4:
            start_date = now.date() - timedelta(days=1)
        else:
            start_date = now.date()
            
        # Create timezone-aware boundaries
        tz = now.tzinfo
        start_time = datetime.combine(start_date, time(4, 0))
        if tz:
            start_time = tz.localize(start_time)

        end_time = start_time + timedelta(hours=24)
        
        stmt = select(LedgerRecord).where(
            and_(
                LedgerRecord.group_id == group_id,
                LedgerRecord.bot_id == bot_id,
                LedgerRecord.created_at >= start_time,
                LedgerRecord.created_at < end_time
            )
        ).order_by(LedgerRecord.created_at.desc())
        
        result = await self.session.execute(stmt)
        records = result.scalars().all()
        
        deposits = [r for r in records if r.type == 'deposit']
        payouts = [r for r in records if r.type == 'payout']
        
        total_deposit = sum(r.amount for r in deposits)
        total_payout = sum(r.amount for r in payouts)
        
        return {
            "deposits": deposits,
            "payouts": payouts,
            "total_deposit": total_deposit,
            "total_payout": total_payout,
            "count_deposit": len(deposits),
            "count_payout": len(payouts),
            "date_str": start_date.strftime("%Y-%m-%d"),
            "start_time": start_time,
            "end_time": end_time
        }
