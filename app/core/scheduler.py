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
        stmt = select(GroupConfig).where(GroupConfig.is_active == True)
        result = await session.execute(stmt)
        groups = result.scalars().all()
        
        count = 0
        for group in groups:
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
                
        logger.info(f"Daily settlement completed for {count} groups.")

def start_scheduler():
    # Run at 04:00 every day
    # Use 'cron' trigger
    scheduler.add_job(daily_settlement_job, 'cron', hour=4, minute=0, id="daily_settlement")
    scheduler.start()
