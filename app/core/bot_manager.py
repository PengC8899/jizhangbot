import asyncio
from typing import Dict
from telegram import Update
from telegram.ext import Application
from telegram.error import InvalidToken
from loguru import logger
from app.core.config import settings
from app.bot.handlers import setup_handlers

class BotManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BotManager, cls).__new__(cls)
            cls._instance.apps: Dict[int, Application] = {}
        return cls._instance

    async def start_bot(self, token: str, bot_db_id: int) -> bool:
        """
        Dynamically start a bot.
        1. Validate token (implicitly by building app)
        2. Initialize Application
        3. Setup Webhook
        """
        try:
            if bot_db_id in self.apps:
                logger.warning(f"Bot {bot_db_id} already running.")
                return True

            app = Application.builder().token(token).build()
            
            # Setup handlers
            setup_handlers(app)
            
            # Initialize
            await app.initialize()
            
            # Store DB ID in bot_data for handlers to access
            app.bot_data["db_id"] = bot_db_id
            
            await app.start()
            
            # Get Bot Info (verify token works)
            bot_info = await app.bot.get_me()
            logger.info(f"Started Bot: {bot_info.username} (ID: {bot_info.id})")

            # Setup Webhook
            if settings.TG_MODE == "webhook":
                webhook_url = f"https://{settings.DOMAIN}/telegram/webhook/{bot_db_id}"
                # Add secret token for security
                secret_token = f"secret_{bot_db_id}_{settings.SECRET_KEY}"[:32].replace("-", "") 
                
                await app.bot.set_webhook(
                    url=webhook_url,
                    secret_token=secret_token,
                    allowed_updates=Update.ALL_TYPES # PTB specific
                )
                logger.info(f"Webhook set to {webhook_url}")
            else:
                # Polling mode (for dev/testing if needed, but V3 emphasizes Webhook)
                # In a multi-bot single-process setup, polling is tricky. 
                # We would need to spawn a task for updater.start_polling()
                await app.updater.start_polling()
                logger.info("Polling started")

            self.apps[bot_db_id] = app
            return True

        except Exception as e:
            logger.error(f"Failed to start bot {bot_db_id}: {e}")
            return False

    async def stop_bot(self, bot_db_id: int):
        if bot_db_id in self.apps:
            app = self.apps[bot_db_id]
            
            if settings.TG_MODE == "webhook":
                await app.bot.delete_webhook()
            else:
                await app.updater.stop()
            
            await app.stop()
            await app.shutdown()
            del self.apps[bot_db_id]
            logger.info(f"Stopped Bot {bot_db_id}")

    async def reload_bot(self, token: str, bot_db_id: int):
        await self.stop_bot(bot_db_id)
        await self.start_bot(token, bot_db_id)

    def get_app(self, bot_db_id: int) -> Application:
        return self.apps.get(bot_db_id)

bot_manager = BotManager()
