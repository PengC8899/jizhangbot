import asyncio
import sys
import os
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add app to path
sys.path.append(os.getcwd())

from app.models.group import GroupConfig, LedgerRecord, Base
from app.services.ledger_service import LedgerService

async def test_transaction_flow():
    print("--- Testing Transaction Flow ---")
    
    # 1. Setup DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    bot_id = 1
    group_id = 100
    user_id = 888
    
    async with AsyncSessionLocal() as session:
        service = LedgerService(session)
        
        # 2. Start Recording (Create Config)
        await service.start_recording(group_id, bot_id)
        print("✅ Started recording")
        
        # 3. Record Deposit +1000
        await service.record_transaction(bot_id, group_id, "deposit", 1000.0, user_id, "UserA", "+1000")
        print("✅ Recorded +1000")
        
        # 4. Verify Summary
        summary = await service.get_daily_summary(group_id, bot_id)
        print(f"Summary: {summary}")
        
        if summary['total_deposit'] != 1000.0:
            print("❌ Total Deposit Mismatch!")
            return
            
        # 5. Test Payout
        await service.record_transaction(bot_id, group_id, "payout", 200.0, user_id, "UserA", "下发200")
        print("✅ Recorded Payout 200")
        
        summary = await service.get_daily_summary(group_id, bot_id)
        print(f"Summary: {summary}")
        
        if summary['total_payout'] != 200.0:
            print("❌ Total Payout Mismatch!")
            return
            
        print("✅ Transaction Flow Verified!")

if __name__ == "__main__":
    asyncio.run(test_transaction_flow())