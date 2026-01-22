from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.group import GroupConfig, Operator, LedgerRecord
from app.models.bot import Bot
from datetime import datetime, time, timedelta

class LedgerService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_group_config(self, group_id: int, bot_id: int) -> GroupConfig:
        stmt = select(GroupConfig).where(
            and_(GroupConfig.group_id == group_id, GroupConfig.bot_id == bot_id)
        )
        result = await self.session.execute(stmt)
        config = result.scalars().first()
        if not config:
            config = GroupConfig(group_id=group_id, bot_id=bot_id)
            self.session.add(config)
            await self.session.commit()
            await self.session.refresh(config)
        return config

    async def is_group_active(self, group_id: int, bot_id: int) -> bool:
        config = await self.get_group_config(group_id, bot_id)
        return config.is_active

    async def start_recording(self, group_id: int, bot_id: int):
        stmt = update(GroupConfig).where(
            and_(GroupConfig.group_id == group_id, GroupConfig.bot_id == bot_id)
        ).values(is_active=True, active_start_time=datetime.now())
        await self.session.execute(stmt)
        await self.session.commit()

    async def stop_recording(self, group_id: int, bot_id: int):
        stmt = update(GroupConfig).where(
            and_(GroupConfig.group_id == group_id, GroupConfig.bot_id == bot_id)
        ).values(is_active=False)
        await self.session.execute(stmt)
        await self.session.commit()

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
            usd_rate_snapshot=config.usd_rate
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
        # Logic: 4AM to 4AM next day
        now = datetime.now()
        if now.hour < 4:
            start_date = now.date() - timedelta(days=1)
        else:
            start_date = now.date()
            
        start_time = datetime.combine(start_date, time(4, 0))
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
        # Logic: 4AM to 4AM next day
        now = datetime.now()
        if now.hour < 4:
            start_date = now.date() - timedelta(days=1)
        else:
            start_date = now.date()
            
        start_time = datetime.combine(start_date, time(4, 0))
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
