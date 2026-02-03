from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, insert, delete
from pydantic import BaseModel
import json

from app.core.database import get_db
from app.core.config import settings
from app.models.bot import Bot
from app.models.group import GroupConfig, GroupCategory, group_category_association
from app.core.bot_manager import bot_manager

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

COOKIE_NAME = "customer_session"

# --- Models ---
class CreateCategoryRequest(BaseModel):
    name: str

class AddToCategoryRequest(BaseModel):
    group_ids: list[int]

class ExitGroupsRequest(BaseModel):
    group_ids: list[int]

class CustomerBroadcastRequest(BaseModel):
    text: str
    group_ids: list[int] # Chat IDs

# --- Dependencies ---

async def get_current_customer_bot(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Returns the Bot object if the user is logged in as a customer (Bot Owner).
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        if "login" not in request.url.path:
             raise HTTPException(status_code=307, headers={"Location": "/customer/login"})
        return None

    # Token format: "customer_{bot_id}_{password_hash}" (Simple for MVP)
    # We'll just store bot_id in signed way or check against DB
    # For MVP: "customer_{bot_id}_{plain_password}" (Secure enough for this context if HTTPS)
    try:
        parts = token.split("_")
        if len(parts) < 3 or parts[0] != "customer":
            raise HTTPException(status_code=307, headers={"Location": "/customer/login"})
        
        bot_id = int(parts[1])
        password = "_".join(parts[2:]) # In case password has underscores
        
        bot = await db.get(Bot, bot_id)
        if not bot or bot.web_password != password:
            raise HTTPException(status_code=307, headers={"Location": "/customer/login"})
            
        return bot
    except Exception:
        raise HTTPException(status_code=307, headers={"Location": "/customer/login"})

# --- Routes ---

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    bot_id = request.query_params.get("bot_id", "")
    return templates.TemplateResponse("customer/login.html", {"request": request, "bot_id": bot_id})

@router.post("/login", response_class=HTMLResponse)
async def login_action(request: Request, bot_id: int = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    bot = await db.get(Bot, bot_id)
    if bot and bot.web_password == password:
        response = RedirectResponse(url="/customer/broadcast", status_code=303)
        # Set cookie
        token = f"customer_{bot_id}_{password}"
        response.set_cookie(key=COOKIE_NAME, value=token, httponly=True, max_age=86400 * 7) # 7 days
        return response
    
    return templates.TemplateResponse("customer/login.html", {"request": request, "error": "Bot ID 或密码错误", "bot_id": bot_id})

@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/customer/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response

@router.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request, db: AsyncSession = Depends(get_db), bot: Bot = Depends(get_current_customer_bot)):
    # Fetch groups for THIS bot only
    stmt = select(GroupConfig).where(GroupConfig.bot_id == bot.id).order_by(GroupConfig.updated_at.desc())
    result = await db.execute(stmt)
    groups = result.scalars().all()
    
    # Fetch Categories (scoped to bot or global)
    stmt_cat = select(GroupCategory).where((GroupCategory.bot_id == bot.id) | (GroupCategory.bot_id == None))
    result_cat = await db.execute(stmt_cat)
    categories = result_cat.scalars().all()
    
    categories_data = []
    for cat in categories:
        # Count groups for this bot in this category
        stmt_c = (
            select(func.count(GroupConfig.id))
            .join(group_category_association, GroupConfig.id == group_category_association.c.group_config_id)
            .where(
                GroupConfig.bot_id == bot.id,
                group_category_association.c.category_id == cat.id
            )
        )
        count = await db.scalar(stmt_c)
        categories_data.append({
            "id": cat.id,
            "name": cat.name,
            "count": count or 0
        })
        
    return templates.TemplateResponse("customer/broadcast.html", {
        "request": request, 
        "groups": groups, 
        "bot": bot,
        "categories": categories_data
    })

# --- API for Customer Broadcast ---

@router.post("/api/category")
async def create_category(req: CreateCategoryRequest, db: AsyncSession = Depends(get_db), bot: Bot = Depends(get_current_customer_bot)):
    # Check if category exists for this bot
    stmt = select(GroupCategory).where(GroupCategory.bot_id == bot.id, GroupCategory.name == req.name)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
         return {"success": False, "error": "分组名称已存在"}
         
    new_cat = GroupCategory(name=req.name, bot_id=bot.id)
    db.add(new_cat)
    try:
        await db.commit()
        await db.refresh(new_cat)
        return {"success": True, "data": {"id": new_cat.id, "name": new_cat.name}}
    except Exception as e:
        await db.rollback()
        return {"success": False, "error": str(e)}

@router.post("/api/category/{cat_id}/add")
async def add_groups_to_category(cat_id: int, req: AddToCategoryRequest, db: AsyncSession = Depends(get_db), bot: Bot = Depends(get_current_customer_bot)):
    # Verify category belongs to bot (or is global, but we only allow adding to bot's own categories ideally? 
    # For now allow global too if we show them)
    cat = await db.get(GroupCategory, cat_id)
    if not cat:
        return {"success": False, "error": "分组不存在"}
    
    if cat.bot_id is not None and cat.bot_id != bot.id:
        return {"success": False, "error": "无权操作此分组"}
        
    # Verify groups belong to bot
    stmt = select(GroupConfig).where(GroupConfig.bot_id == bot.id, GroupConfig.group_id.in_(req.group_ids))
    result = await db.execute(stmt)
    groups = result.scalars().all()
    
    if not groups:
         return {"success": False, "error": "无有效群组"}
         
    count = 0
    for group in groups:
        # Check if already in category
        stmt_check = select(group_category_association).where(
            group_category_association.c.group_config_id == group.id,
            group_category_association.c.category_id == cat.id
        )
        res_check = await db.execute(stmt_check)
        if not res_check.first():
            stmt_ins = insert(group_category_association).values(group_config_id=group.id, category_id=cat.id)
            await db.execute(stmt_ins)
            count += 1
            
    await db.commit()
    return {"success": True, "data": {"added": count}}

@router.post("/api/groups/exit")
async def exit_groups(req: ExitGroupsRequest, db: AsyncSession = Depends(get_db), bot: Bot = Depends(get_current_customer_bot)):
    # Verify groups
    stmt = select(GroupConfig).where(GroupConfig.bot_id == bot.id, GroupConfig.group_id.in_(req.group_ids))
    result = await db.execute(stmt)
    groups = result.scalars().all()
    
    if not groups:
        return {"success": False, "error": "No valid groups"}
        
    app = bot_manager.apps.get(bot.id)
    
    count = 0
    for group in groups:
        # 1. Leave Chat
        if app:
            try:
                await app.bot.leave_chat(chat_id=group.group_id)
            except Exception:
                pass # Maybe already left
                
        # 2. Delete Config
        await db.delete(group)
        count += 1
        
    await db.commit()
    return {"success": True, "data": {"removed": count}}

@router.post("/api/broadcast")
async def customer_broadcast_api(
    text: str = Form(...),
    group_ids: str = Form(...),
    image: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
    bot: Bot = Depends(get_current_customer_bot)
):
    # Parse group_ids
    try:
        target_group_ids = json.loads(group_ids)
    except Exception:
        return {"success": False, "error": "Invalid group_ids format"}

    # Verify groups belong to this bot
    # (Security check)
    stmt = select(GroupConfig).where(
        GroupConfig.bot_id == bot.id,
        GroupConfig.group_id.in_(target_group_ids)
    )
    result = await db.execute(stmt)
    valid_groups = result.scalars().all()
    
    if not valid_groups:
        return {"success": False, "error": "No valid groups selected"}

    app = bot_manager.apps.get(bot.id)
    if not app:
        return {"success": False, "error": "Bot is not running"}

    success_count = 0
    error_count = 0
    
    # Read image once if present
    image_bytes = None
    if image:
        image_bytes = await image.read()

    for group in valid_groups:
        try:
            if image_bytes:
                await app.bot.send_photo(chat_id=group.group_id, photo=image_bytes, caption=text)
            else:
                await app.bot.send_message(chat_id=group.group_id, text=text)
            success_count += 1
        except Exception as e:
            error_count += 1
            
    return {"success": True, "data": {"success_count": success_count, "error_count": error_count}}

@router.get("/api/groups")
async def get_customer_groups(
    category_id: int = None, 
    db: AsyncSession = Depends(get_db), 
    bot: Bot = Depends(get_current_customer_bot)
):
    """
    Get groups filtered by category (optional) for the current bot.
    """
    stmt = select(GroupConfig).where(GroupConfig.bot_id == bot.id)
    
    if category_id:
        from app.models.group import group_category_association
        stmt = stmt.join(group_category_association).where(
            group_category_association.c.category_id == category_id
        )
        
    stmt = stmt.order_by(GroupConfig.updated_at.desc())
    
    result = await db.execute(stmt)
    groups = result.scalars().all()
    
    return [
        {
            "group_id": str(g.group_id), # Ensure string for JS
            "group_name": g.group_name or "未命名群组",
            "is_active": g.is_active
        }
        for g in groups
    ]
