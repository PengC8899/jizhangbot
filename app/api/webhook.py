from fastapi import APIRouter, Request, Header, HTTPException, status, BackgroundTasks
from app.core.bot_manager import bot_manager
from app.core.config import settings
from telegram import Update
from loguru import logger

router = APIRouter()

@router.post("/webhook/{bot_id}")
async def telegram_webhook(
    bot_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str = Header(None)
):
    """
    Handle incoming Telegram updates.
    """
    # 1. Validate Secret Token
    expected_secret = f"secret_{bot_id}_{settings.SECRET_KEY}"[:32].replace("-", "")
    if x_telegram_bot_api_secret_token != expected_secret:
        logger.warning(f"Invalid secret token for Bot {bot_id}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Token")

    # 2. Get Application
    app = bot_manager.get_app(bot_id)
    if not app:
        logger.warning(f"Received update for unknown or stopped Bot {bot_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")

    # 3. Process Update
    try:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        
        # We process update in the background to respond quickly to Telegram
        # Wait, app.process_update is async. If we await it, we hold the request.
        # PTB's process_update waits for handlers.
        # For high concurrency, we should return 200 OK immediately and process in background?
        # BUT PTB application is designed to handle this.
        # If we use `await app.process_update(update)`, we are bound by handler execution time.
        # Better: app.update_queue.put(update) if using internal queue, 
        # but manual `process_update` usually executes handlers directly.
        
        # Standard way for webhook handler in FastAPI + PTB:
        await app.process_update(update)
        
    except Exception as e:
        logger.error(f"Error processing update for Bot {bot_id}: {e}")
        # Still return 200 to prevent Telegram from retrying endlessly on bad updates
        return {"status": "error", "message": str(e)}

    return {"status": "ok"}
