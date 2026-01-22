import asyncio
import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add app to path
sys.path.append(os.getcwd())

from app.models.group import GroupConfig, Base
from app.models.bot import Bot # Import Bot to register table
from app.services.license_service import LicenseService

async def test_license_logic():
    print("--- Testing License Logic ---")
    
    # 1. Setup In-Memory DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    user_id = 1001
    group_id = -2002
    bot_id = 1
    
    async with AsyncSessionLocal() as session:
        # 2. Seed Data: User has license, Group has NONE
        print(f"Seeding: User {user_id} has active license. Group {group_id} has NO license.")
        
        user_config = GroupConfig(
            group_id=user_id, # User ID as Group ID for personal license
            bot_id=bot_id,
            expire_at=datetime.now() + timedelta(days=30),
            is_active=True
        )
        session.add(user_config)
        
        # Group config might exist but expired or not exist
        # Let's create an expired group config to be sure
        group_config = GroupConfig(
            group_id=group_id,
            bot_id=bot_id,
            expire_at=datetime.now() - timedelta(days=1), # Expired
            is_active=True
        )
        session.add(group_config)
        
        await session.commit()
        
        # 3. Test Check
        service = LicenseService(session)
        
        # Case A: Check Group Only (Should Fail)
        is_valid_group = await service.check_license(group_id, bot_id)
        print(f"Case A (Group Only): {is_valid_group} (Expected: False)")
        
        # Case B: Check Group + User (Should Pass)
        is_valid_user = await service.check_license(group_id, bot_id, user_id=user_id)
        print(f"Case B (Group + User): {is_valid_user} (Expected: True)")
        
        if not is_valid_group and is_valid_user:
            print("✅ License Logic SUCCESS: User license propagated to Group.")
        else:
            print("❌ License Logic FAILED.")

if __name__ == "__main__":
    asyncio.run(test_license_logic())