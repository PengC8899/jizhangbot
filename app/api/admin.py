from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import date, datetime, timedelta
from telegram.ext import Application
from telegram.error import InvalidToken

from app.core.database import get_db
from app.models.bot import Bot
from app.models.transaction import Transaction
from app.models.group import GroupConfig, Operator, LedgerRecord, LicenseCode, TrialRequest
from app.core.bot_manager import bot_manager
from app.services.license_service import LicenseService
from loguru import logger

router = APIRouter()

class BotCreate(BaseModel):
    token: str
    name: str = None

@router.post("/bot/create")
async def create_bot(bot_in: BotCreate, db: AsyncSession = Depends(get_db)):
    """
    Online Bot Registration (No Restart)
    1. Check Token
    2. Save to DB
    3. Start Bot Process
    """
    # 1. Validate Token via PTB (Try to build/initialize)
    try:
        # Just building isn't enough to validate, need get_me, but we can try building first
        # We can use a temporary app to check token validity
        temp_app = Application.builder().token(bot_in.token).build()
        # await temp_app.bot.get_me() # This requires network, might be slow. 
        # But for "Immediate System Check" it's good.
        # Ideally we trust the input or check it. BotManager.start_bot checks it too.
        pass
    except Exception as e:
         raise HTTPException(status_code=400, detail=f"Invalid Token format: {e}")

    # 2. Check if exists
    result = await db.execute(select(Bot).where(Bot.token == bot_in.token))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Bot already exists")

    # 3. Create DB Entry
    new_bot = Bot(token=bot_in.token, name=bot_in.name, status="active")
    db.add(new_bot)
    await db.commit()
    await db.refresh(new_bot)

    # 4. Start Bot dynamically
    success = await bot_manager.start_bot(new_bot.token, new_bot.id)
    if not success:
        # Rollback if failed to start? Or keep as 'error' status?
        # For now, we keep it but log error. User can retry or delete.
        logger.error(f"Failed to start bot {new_bot.id} immediately.")
        return {"status": "created_but_failed_to_start", "bot_id": new_bot.id}

    return {"status": "success", "bot_id": new_bot.id, "name": new_bot.name}

@router.post("/license/generate")
async def generate_license(days: int, db: AsyncSession = Depends(get_db)):
    """Generate a new license code"""
    service = LicenseService(db)
    code = await service.generate_code(days)
    return {"status": "success", "code": code, "days": days}

from app.services.export_service import generate_group_ledger

@router.get("/group/{chat_id}/export")
async def export_group_ledger(
    chat_id: str, 
    date: date, 
    db: AsyncSession = Depends(get_db)
):
    """
    Export Group Ledger to Excel
    """
    output = await generate_group_ledger(db, chat_id, date)
    
    filename = f"账单_{chat_id}_{date}.xlsx"
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    
    return StreamingResponse(
        output, 
        headers=headers, 
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# Trial Management

@router.get("/trials/pending")
async def list_pending_trials(db: AsyncSession = Depends(get_db)):
    """List all pending trial requests"""
    stmt = select(TrialRequest).where(TrialRequest.status == "pending")
    result = await db.execute(stmt)
    requests = result.scalars().all()
    return requests

@router.post("/trials/{request_id}/approve")
async def approve_trial(request_id: int, days: int = None, db: AsyncSession = Depends(get_db)):
    """
    Approve a trial request.
    Optional 'days' parameter to override default duration.
    """
    # 1. Get Request
    stmt = select(TrialRequest).where(TrialRequest.id == request_id)
    result = await db.execute(stmt)
    req = result.scalars().first()
    
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")
        
    # 2. Grant License (Update GroupConfig)
    # Check if config exists
    stmt_group = select(GroupConfig).where(
        GroupConfig.group_id == req.user_id,
        GroupConfig.bot_id == req.bot_id
    )
    result_group = await db.execute(stmt_group)
    config = result_group.scalars().first()
    
    if not config:
        config = GroupConfig(
            group_id=req.user_id,
            bot_id=req.bot_id,
            is_active=True 
        )
        db.add(config)
        
    # Set Expiration
    duration = days if days is not None else req.duration_days
    
    now = datetime.now()
    if config.expire_at and config.expire_at > now:
         new_expire = config.expire_at + timedelta(days=duration)
    else:
         new_expire = now + timedelta(days=duration)
         
    config.expire_at = new_expire
    
    # 3. Update Request Status
    req.status = "approved"
    req.duration_days = duration # Update actual granted duration
    req.updated_at = now
    
    await db.commit()
    
    # 4. Notify User
    try:
        app = bot_manager.apps.get(req.bot_id)
        if app:
            await app.bot.send_message(
                chat_id=req.user_id,
                text=f"🎉 您的试用申请已通过！\n授权天数：{duration}天\n有效期至：{new_expire.strftime('%Y-%m-%d %H:%M')}"
            )
    except Exception as e:
        logger.error(f"Failed to notify user {req.user_id}: {e}")
        
    return {"status": "approved", "granted_days": duration, "expire_at": new_expire}

@router.post("/trials/{request_id}/reject")
async def reject_trial(request_id: int, db: AsyncSession = Depends(get_db)):
    """Reject a trial request"""
    stmt = select(TrialRequest).where(TrialRequest.id == request_id)
    result = await db.execute(stmt)
    req = result.scalars().first()
    
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    req.status = "rejected"
    req.updated_at = datetime.now()
    await db.commit()
    
    return {"status": "rejected"}
