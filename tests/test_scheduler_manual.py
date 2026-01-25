import asyncio
import sys
import os

# Add app to path
sys.path.append(os.getcwd())

from app.core.database import AsyncSessionLocal
from app.services.ledger_service import LedgerService
from app.core.scheduler import daily_settlement_job
from app.models.group import GroupConfig
from sqlalchemy import select, delete

async def test_settlement():
    print("Setting up test data...")
    async with AsyncSessionLocal() as session:
        service = LedgerService(session)
        # Create a dummy group
        test_group_id = -100123456789
        test_bot_id = 12345
        
        # Clean up
        await session.execute(delete(GroupConfig).where(GroupConfig.group_id == test_group_id))
        await session.commit()
        
        # Create and Activate
        config = await service.get_group_config(test_group_id, test_bot_id)
        await service.start_recording(test_group_id, test_bot_id)
        
        # Verify Active
        is_active = await service.is_group_active(test_group_id, test_bot_id)
        print(f"Group Active Before: {is_active}")
        assert is_active == True
        
    print("Running Settlement Job...")
    # Run job
    await daily_settlement_job()
    
    print("Verifying result...")
    async with AsyncSessionLocal() as session:
        service = LedgerService(session)
        is_active = await service.is_group_active(test_group_id, test_bot_id)
        print(f"Group Active After: {is_active}")
        assert is_active == False
        
        # Cleanup
        await session.execute(delete(GroupConfig).where(GroupConfig.group_id == test_group_id))
        await session.commit()
        
    print("Test Passed!")

if __name__ == "__main__":
    asyncio.run(test_settlement())
