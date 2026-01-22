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
        """
        try:
            if bot_db_id in self.apps:
                logger.warning(f"Bot {bot_db_id} already running.")
                return True

            app = Application.builder().token(token).build()
            setup_handlers(app)
            
            await app.initialize()
            app.bot_data["db_id"] = bot_db_id
            await app.start()
            
            # Verify Token & Get Info
            bot_info = await app.bot.get_me()
            logger.info(f"Started Bot: {bot_info.username} (ID: {bot_info.id})")

            # Setup Webhook or Polling
            if settings.TG_MODE == "webhook":
                webhook_url = f"https://{settings.DOMAIN}/telegram/webhook/{bot_db_id}"
                secret_token = f"secret_{bot_db_id}_{settings.SECRET_KEY}"[:32].replace("-", "") 
                
                await app.bot.set_webhook(
                    url=webhook_url,
                    secret_token=secret_token,
                    allowed_updates=Update.ALL_TYPES
                )
                logger.info(f"Webhook set to {webhook_url}")
            else:
                # Polling mode: Run updater.start_polling() in a task to avoid blocking
                # Important: In multi-bot setup, we can't block here.
                # 'app.updater.start_polling()' is usually non-blocking if we don't await 'idle()'
                # But let's be explicit.
                await app.updater.start_polling() 
                logger.info("Polling started")

            self.apps[bot_db_id] = app
            return True

        except Exception as e:
            logger.error(f"Failed to start bot {bot_db_id}: {e}")
            return False

    async def start_all_bots(self, bots: list):
        """
        Parallel startup of all bots to reduce downtime and startup time.
        """
        tasks = [self.start_bot(bot.token, bot.id) for bot in bots]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = 0
        for i, res in enumerate(results):
            if res is True:
                success_count += 1
            else:
                logger.error(f"Bot {bots[i].id} failed to start: {res}")
        
        logger.info(f"Parallel startup finished. Success: {success_count}/{len(bots)}")

    async def stop_bot(self, bot_db_id: int):
        # ... (Same as before)
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

    # ... (reload_bot, get_app remain same) ...
    async def reload_bot(self, token: str, bot_db_id: int):
        await self.stop_bot(bot_db_id)
        await self.start_bot(token, bot_db_id)

    def get_app(self, bot_db_id: int) -> Application:
        return self.apps.get(bot_db_id)

bot_manager = BotManager()
