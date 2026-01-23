from sqlalchemy import select, update, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.group import GroupConfig, Operator, LedgerRecord
from app.models.bot import Bot
from datetime import datetime, time, timedelta
from app.core.cache import cache_service
from app.core.utils import get_now
from decimal import Decimal
from typing import Union

class LedgerService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_group_config(self, group_id: int, bot_id: int, group_name: str = None) -> GroupConfig:
        # 1. Try Cache
        cached_data = await cache_service.get_group_config(group_id, bot_id)
        if cached_data:
            # Reconstruct GroupConfig object from dict
            # Be careful: This is a detached object and cannot be used for updates directly without merging
            # However, for read-only access it's perfect.
            # We must convert string decimals back if JSON didn't do it (our custom loader does)
            
            # Since cached_data comes from json.loads(..., parse_float=Decimal), numeric fields are already Decimal/float
            # But SQLAlchemy expects models.
            
            # To avoid complexity with detached instances, we only use cache for specific read-heavy fields
            # or return a Pydantic model. But the signature says -> GroupConfig.
            
            # For now, let's just return the object manually constructed.
            # Warning: This object is NOT attached to the session.
            config = GroupConfig(**cached_data)
            return config
        
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
        
        # Update Cache
        # Convert config to dict
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
        await cache_service.invalidate_group_config(group_id, bot_id)

    async def stop_recording(self, group_id: int, bot_id: int):
        stmt = update(GroupConfig).where(
            and_(GroupConfig.group_id == group_id, GroupConfig.bot_id == bot_id)
        ).values(is_active=False)
        await self.session.execute(stmt)
        await self.session.commit()
        await cache_service.invalidate_group_config(group_id, bot_id)
        
    async def add_operator(self, group_id: int, user_id: int, username: str):
        stmt = select(Operator).where(
            and_(Operator.group_id == group_id, Operator.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        if result.scalars().first():
            return 
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

    async def get_daily_records(self, group_id: int, bot_id: int = None) -> list[LedgerRecord]:
        # 4AM Logic
        now = get_now()
        if now.hour < 4:
            start_date = now.date() - timedelta(days=1)
        else:
            start_date = now.date()
        start_time = datetime.combine(start_date, time(4, 0))
        # Ensure timezone
        if now.tzinfo:
            start_time = now.tzinfo.localize(start_time)
            
        stmt = select(LedgerRecord).where(
            and_(
                LedgerRecord.group_id == group_id,
                LedgerRecord.created_at >= start_time
            )
        )
        if bot_id:
            stmt = stmt.where(LedgerRecord.bot_id == bot_id)
            
        stmt = stmt.order_by(LedgerRecord.created_at.desc())
        
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def record_transaction(self, bot_id: int, group_id: int, type_: str, amount: Union[Decimal, float, str], 
                               operator_id: int, operator_name: str, original_text: str):
        # 1. Convert to Decimal for storage
        if isinstance(amount, Decimal):
            amount_decimal = amount
        else:
            amount_decimal = Decimal(str(amount))
        
        # 2. Get Config for Snapshot
        config = await self.get_group_config(group_id, bot_id)
        
        # 3. Calculate Fee Snapshot
        # fee_percent is now Numeric/Decimal
        fee_applied = Decimal(0)
        if type_ == "deposit" and config.fee_percent > 0:
            fee_applied = amount_decimal * (config.fee_percent / Decimal(100))
            
        record = LedgerRecord(
            bot_id=bot_id,
            group_id=group_id,
            type=type_,
            amount=amount_decimal,
            operator_id=operator_id,
            operator_name=operator_name,
            original_text=original_text,
            fee_applied=fee_applied,
            usd_rate_snapshot=config.usd_rate
        )
        self.session.add(record)
        await self.session.commit()
        
    async def get_daily_summary(self, group_id: int, bot_id: int) -> dict:
        # 4AM Logic
        now = get_now()
        if now.hour < 4:
            start_date = now.date() - timedelta(days=1)
        else:
            start_date = now.date()
        start_time = datetime.combine(start_date, time(4, 0))
        # Ensure timezone
        if now.tzinfo:
            start_time = now.tzinfo.localize(start_time)
            
        # Aggregation using SQL for efficiency
        # CAST to ensure correct summation if DB driver returns weird types
        stmt = select(
            LedgerRecord.type,
            func.sum(LedgerRecord.amount).label("total"),
            func.count(LedgerRecord.id).label("count")
        ).where(
            and_(
                LedgerRecord.group_id == group_id,
                LedgerRecord.bot_id == bot_id,
                LedgerRecord.created_at >= start_time
            )
        ).group_by(LedgerRecord.type)
        
        result = await self.session.execute(stmt)
        rows = result.all()
        
        summary = {
            "total_deposit": Decimal(0),
            "count_deposit": 0,
            "total_payout": Decimal(0),
            "count_payout": 0
        }
        
        for row in rows:
            # row.total might be Decimal or Float depending on DB driver
            val = Decimal(str(row.total)) if row.total is not None else Decimal(0)
            if row.type == "deposit":
                summary["total_deposit"] = val
                summary["count_deposit"] = row.count
            elif row.type == "payout":
                summary["total_payout"] = val
                summary["count_payout"] = row.count
                
        return summary

    async def get_recent_records(self, group_id: int, bot_id: int, limit: int = 5, record_type: str = None):
        stmt = select(LedgerRecord).where(
            and_(
                LedgerRecord.group_id == group_id,
                LedgerRecord.bot_id == bot_id
            )
        )
        if record_type:
            stmt = stmt.where(LedgerRecord.type == record_type)
            
        stmt = stmt.order_by(LedgerRecord.created_at.desc()).limit(limit)
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
        
    async def delete_today_records(self, group_id: int, bot_id: int):
        # 4AM Logic
        now = get_now()
        if now.hour < 4:
            start_date = now.date() - timedelta(days=1)
        else:
            start_date = now.date()
        start_time = datetime.combine(start_date, time(4, 0))
        if now.tzinfo: start_time = now.tzinfo.localize(start_time)

        stmt = delete(LedgerRecord).where(
            and_(
                LedgerRecord.group_id == group_id,
                LedgerRecord.bot_id == bot_id,
                LedgerRecord.created_at >= start_time
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()
