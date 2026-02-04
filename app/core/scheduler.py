from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from loguru import logger
from app.core.database import AsyncSessionLocal
from app.services.ledger_service import LedgerService
from app.models.group import GroupConfig
from app.core.bot_manager import bot_manager
from app.core.config import settings

# Initialize Scheduler
scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)

async def daily_settlement_job():
    """
    Daily job at 04:00 AM to stop all active groups.
    Users must manually type /start to resume.
    """
    logger.info("Running daily settlement job...")
    async with AsyncSessionLocal() as session:
        service = LedgerService(session)
        
        # Get all active groups
        # Filter logic:
        # 1. is_active == True (Already in code)
        # 2. Must be a valid group (group_id < 0 for Telegram groups/supergroups)
        # 3. Private chats (user_id > 0) are technically possible in GroupConfig if we track them, 
        #    but usually we only care about Groups.
        #    If private chat is also "active", we stop it too? 
        #    User request: "Only send to activated active groups, not inactive, not private chats"
        
        stmt = select(GroupConfig).where(GroupConfig.is_active == True)
        result = await session.execute(stmt)
        groups = result.scalars().all()
        
        count = 0
        for group in groups:
            # Check if it's a group (negative ID)
            # Private chats have positive ID.
            if group.group_id > 0:
                # Private chat - Skip notification, but maybe still stop recording?
                # User said: "not private chat".
                # Let's just stop recording silently for private chats if they are active.
                await service.stop_recording(group.group_id, group.bot_id)
                continue

            # Check if it has any records today? 
            # User said "activated active groups". 
            # Our definition of "is_active=True" means they typed /start today (or didn't stop).
            # So they are "activated".
            
            # Stop recording
            await service.stop_recording(group.group_id, group.bot_id)
            
            # Send notification
            app = bot_manager.apps.get(group.bot_id)
            if app:
                try:
                    await app.bot.send_message(
                        chat_id=group.group_id,
                        text="🌅 <b>每日自动结算完成</b>\n\n已停止当日记账功能。\n如需开始新的一天，请发送 /start 或 点击下方按钮",
                        parse_mode='HTML'
                    )
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to send settlement msg to {group.group_id}: {e}")
            else:
                logger.warning(f"Bot {group.bot_id} not active for group {group.group_id}")
                
        logger.info(f"Daily settlement completed. Sent notifications to {count} groups.")

def start_scheduler():
    # Run at 04:00 every day
    # Use 'cron' trigger
    scheduler.add_job(daily_settlement_job, 'cron', hour=4, minute=0, id="daily_settlement")
    scheduler.start()
