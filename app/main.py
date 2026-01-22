from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.core.bot_manager import bot_manager
from app.models.bot import Bot
from app.models.group import GroupConfig, Operator, LedgerRecord, LicenseCode
from sqlalchemy import select
from loguru import logger
from app.api import admin, webhook, dashboard
from app.api.bill import router as bill_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")
    
    # Create DB Tables (for demo purposes)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Load Active Bots
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Bot).where(Bot.status == "active"))
        bots = result.scalars().all()
        for bot in bots:
            logger.info(f"Loading Bot: {bot.name} ({bot.id})")
            # We use create_task to not block startup if one bot fails or takes time
            # But strictly speaking we should await to ensure they are ready. 
            # Given "No system restart" requirement, parallel start is better.
            await bot_manager.start_bot(bot.token, bot.id)
            
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    # Stop all bots
    for bot_id in list(bot_manager.apps.keys()):
        await bot_manager.stop_bot(bot_id)

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(webhook.router, prefix="/telegram", tags=["Webhook"])
app.include_router(bill_router, tags=["bill"])
app.include_router(dashboard.router, tags=["dashboard"])

@app.get("/")
async def root():
    return {"message": "HuiYing Ledger Platform V3 Running"}
