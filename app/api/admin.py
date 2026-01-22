from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel
from datetime import date, datetime, timedelta
import json
from telegram.ext import Application
from telegram.error import InvalidToken

from app.core.database import get_db
from app.models.bot import Bot
from app.models.transaction import Transaction
from app.models.group import GroupConfig, Operator, LedgerRecord, LicenseCode, TrialRequest
from app.core.bot_manager import bot_manager
from app.services.license_service import LicenseService
from loguru import logger
from app.core.utils import to_timezone, get_now

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# --- UI Routes ---

@router.get("/ui/dashboard", response_class=HTMLResponse)
async def dashboard_ui(request: Request, db: AsyncSession = Depends(get_db)):
    # Stats
    bot_count = await db.scalar(select(func.count(Bot.id)))
    group_count = await db.scalar(select(func.count(GroupConfig.id)).where(GroupConfig.is_active == True))
    pending_trials = await db.scalar(select(func.count(TrialRequest.id)).where(TrialRequest.status == "pending"))
    
    # Today Volume
    now = get_now()
    if now.hour < 4:
        start_date = now.date() - timedelta(days=1)
    else:
        start_date = now.date()
    start_time = datetime.combine(start_date, datetime.min.time()).replace(hour=4)
    if now.tzinfo: start_time = now.tzinfo.localize(start_time) # Assuming naive handling in DB, but let's be safe
    # Actually LedgerRecord stores naive usually? Or we standardized.
    # Let's just do a simple query.
    
    # Simplified today sum
    stmt = select(func.sum(LedgerRecord.amount)).where(
        and_(LedgerRecord.type == 'deposit', LedgerRecord.created_at >= start_time)
    )
    today_volume = await db.scalar(stmt) or 0
    
    stats = {
        "bot_count": bot_count,
        "group_count": group_count,
        "pending_trials": pending_trials,
        "today_volume": today_volume
    }
    return templates.TemplateResponse("admin/dashboard.html", {"request": request, "stats": stats, "page": "dashboard"})

@router.get("/ui/trials", response_class=HTMLResponse)
async def trials_ui(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrialRequest).where(TrialRequest.status == "pending").order_by(TrialRequest.created_at.desc()))
    requests = result.scalars().all()
    return templates.TemplateResponse("admin/trials.html", {"request": request, "requests": requests, "page": "trials"})

@router.get("/ui/bots", response_class=HTMLResponse)
async def bots_ui(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Bot))
    bots = result.scalars().all()
    
    # Parse button config for UI
    for bot in bots:
        if bot.button_config:
            try:
                bot.button_config = json.loads(bot.button_config)
            except:
                bot.button_config = {}
        else:
            bot.button_config = {}
            
    return templates.TemplateResponse("admin/bots.html", {"request": request, "bots": bots, "page": "bots"})

@router.get("/ui/groups", response_class=HTMLResponse)
async def groups_ui(request: Request, db: AsyncSession = Depends(get_db)):
    # List all groups that have config
    result = await db.execute(select(GroupConfig).order_by(GroupConfig.updated_at.desc()))
    groups = result.scalars().all()
    return templates.TemplateResponse("admin/groups.html", {"request": request, "groups": groups, "page": "groups"})


# --- API Endpoints ---

class BotButtonConfig(BaseModel):
    bill_text: str = None
    biz_text: str = None
    biz_url: str = None
    complaint_text: str = None
    complaint_url: str = None
    support_text: str = None
    support_url: str = None

@router.post("/bot/{bot_id}/buttons")
async def update_bot_buttons(bot_id: int, config: BotButtonConfig, db: AsyncSession = Depends(get_db)):
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    bot.button_config = json.dumps(config.dict())
    await db.commit()
    
    # Update running bot context if possible (Optional, as handler reads from DB usually or we refresh)
    # Ideally we update cache or notify bot manager.
    # For now, we assume handler queries DB or we add a refresh mechanism.
    return {"status": "success"}

class GroupMessage(BaseModel):
    text: str

@router.post("/bot/{bot_id}/group/{group_id}/message")
async def send_group_message(bot_id: int, group_id: int, msg: GroupMessage, db: AsyncSession = Depends(get_db)):
    # 1. Get Bot Instance
    app = bot_manager.apps.get(bot_id)
    if not app:
        raise HTTPException(status_code=404, detail="Bot not running")
    
    try:
        await app.bot.send_message(chat_id=group_id, text=msg.text)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/broadcast")
async def broadcast_message(msg: GroupMessage, db: AsyncSession = Depends(get_db)):
    """Broadcast message to ALL active groups across ALL bots"""
    # 1. Get all active groups
    stmt = select(GroupConfig).where(GroupConfig.is_active == True)
    result = await db.execute(stmt)
    groups = result.scalars().all()
    
    count = 0
    errors = 0
    
    for group in groups:
        app = bot_manager.apps.get(group.bot_id)
        if not app:
            continue
            
        try:
            await app.bot.send_message(chat_id=group.group_id, text=msg.text)
            count += 1
        except Exception as e:
            logger.error(f"Broadcast failed for group {group.group_id}: {e}")
            errors += 1
            
    return {"status": "success", "count": count, "errors": errors}

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
