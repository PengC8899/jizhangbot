import asyncio
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
from telegram.error import Forbidden, BadRequest

from app.models.group import GroupConfig
# from app.core.bot_manager import bot_manager  <-- Moved inside method to avoid circular import

class BroadcastService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def broadcast_to_bot_groups(self, bot_id: int, message: str, sleep_interval: float = 0.05) -> dict:
        """
        Broadcast a message to all active groups of a specific bot.
        
        Args:
            bot_id: Database ID of the bot
            message: Message content
            sleep_interval: Time to sleep between sends to avoid flood limits (default 0.05s = 20 msg/sec)
            
        Returns:
            Stats dict: {total, success, failed}
        """
        # Avoid circular import
        from app.core.bot_manager import bot_manager

        # 1. Get Bot App
        app = bot_manager.get_app(bot_id)
        if not app:
            logger.error(f"Bot {bot_id} is not running.")
            return {"status": "error", "message": "Bot not running"}

        # 2. Fetch all active groups for this bot
        stmt = select(GroupConfig.group_id).where(
            GroupConfig.bot_id == bot_id,
            GroupConfig.is_active == True
        )
        result = await self.session.execute(stmt)
        group_ids = result.scalars().all()
        
        total = len(group_ids)
        success = 0
        failed = 0
        
        logger.info(f"Starting broadcast for Bot {bot_id} to {total} groups.")
        
        # 3. Iterate and Send
        for chat_id in group_ids:
            try:
                await app.bot.send_message(chat_id=chat_id, text=message)
                success += 1
            except Forbidden:
                # Bot blocked by user/group
                logger.warning(f"Bot blocked by {chat_id}. Marking inactive might be good here.")
                failed += 1
            except BadRequest as e:
                # Chat not found or other issue
                logger.warning(f"Broadcast failed for {chat_id}: {e}")
                failed += 1
            except Exception as e:
                logger.error(f"Unexpected error broadcasting to {chat_id}: {e}")
                failed += 1
            
            # Rate limiting
            await asyncio.sleep(sleep_interval)
            
        logger.info(f"Broadcast finished. Total: {total}, Success: {success}, Failed: {failed}")
        return {
            "total": total,
            "success": success, 
            "failed": failed
        }

    async def broadcast_platform_wide(self, message: str) -> dict:
        """
        Broadcast to ALL groups across ALL bots.
        """
        # TODO: Implement if needed. For now, per-bot is safer.
        pass
