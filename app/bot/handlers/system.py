from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.services.license_service import LicenseService
from app.services.broadcast_service import BroadcastService
from app.services.ledger_service import LedgerService
from app.models.group import GroupConfig, TrialRequest
from app.core.utils import get_now, to_timezone
from app.core.config import settings
from app.bot.handlers.permissions import check_operator_permission
from loguru import logger

async def check_license_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Global Middleware to check license
    """
    if not update.effective_chat or update.effective_chat.type == "private":
        return True # Allow private or no-chat updates
        
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    
    # Allow /activate command always
    if update.message and update.message.text:
        text = update.message.text
        if text.startswith("/activate") or text.startswith("/激活") or text == "激活":
            return True
        # Allow '试用' to pass through so they can claim trial
        if text == "试用":
            return True
        
    session = AsyncSessionLocal()
    service = LicenseService(session)
    try:
        # Check license for Group OR User (Creator)
        user_id = update.effective_user.id if update.effective_user else None
        
        is_valid = await service.check_license(chat_id, bot_id, user_id)
        
        if not is_valid:
            # Check if it looks like a user attempting to use the bot
            # Only reply for likely commands to avoid spamming normal chat
            if update.message and update.message.text:
                msg_text = update.message.text.strip()
                if (msg_text.startswith("+") or 
                    msg_text.startswith("入款") or 
                    msg_text.startswith("下发") or 
                    msg_text == "显示账单" or
                    msg_text == "清理今天数据" or
                    msg_text.startswith("/start") or
                    msg_text == "/开始" or
                    msg_text == "开始"):
                    
                    try:
                        await update.message.reply_text(
                            "⚠️ 机器人未激活或授权已过期。\n"
                            "请发送 '试用' 获取试用时长，或联系管理员获取激活码。"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send license warning: {e}")
            
            # Rate limit warning: In future, use redis to rate limit this warning
            return False
        return True
    finally:
        await session.close()

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin Broadcast: /broadcast <password> <message>
    """
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ 格式错误: /broadcast <密码> <消息内容>")
        return
        
    password = args[0]
    message = " ".join(args[1:])
    
    # Security Check
    if password != settings.ADMIN_PASSWORD:
        await update.message.reply_text("❌ 密码错误")
        return
        
    bot_id = context.bot_data.get("db_id")
    
    await update.message.reply_text("⏳ 开始广播...")
    
    session = AsyncSessionLocal()
    service = BroadcastService(session)
    try:
        stats = await service.broadcast_to_bot_groups(bot_id, message)
        await update.message.reply_text(
            f"✅ 广播完成\n"
            f"总群数: {stats['total']}\n"
            f"成功: {stats['success']}\n"
            f"失败: {stats['failed']}"
        )
    except Exception as e:
        logger.error(f"Broadcast failed: {e}")
        await update.message.reply_text(f"❌ 广播出错: {e}")
    finally:
        await session.close()

async def activate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: /activate CODE
    """
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id

    session = AsyncSessionLocal()
    try:
        permission_service = LedgerService(session)
        if not await check_operator_permission(update, context, permission_service):
            return

        # Get Code
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ 请输入激活码 (例如: /activate HY-XXXX-XXXX-XXXX)")
            return
        code = args[0]

        service = LicenseService(session)
        success, msg = await service.redeem_code(code, chat_id, bot_id)
        if success:
            await update.message.reply_text(f"🎉 {msg}")
        else:
            await update.message.reply_text(f"❌ 激活失败: {msg}")
    finally:
        await session.close()

async def trial_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 试用
    """
    bot_id = context.bot_data.get("db_id")
    user_id = update.effective_user.id
    username = update.effective_user.username
    chat_id = update.effective_chat.id

    if update.effective_chat.type != "private":
        await update.message.reply_text("⚠️ 请私聊机器人申请试用")
        return

    session = AsyncSessionLocal()
    try:
        # 1. Check if already licensed
        stmt_config = select(GroupConfig).where(
            GroupConfig.group_id == chat_id, GroupConfig.bot_id == bot_id
        )
        result = await session.execute(stmt_config)
        config = result.scalars().first()
        
        if config and config.expire_at and config.expire_at > get_now():
            expire_str = to_timezone(config.expire_at).strftime('%Y-%m-%d')
            await update.message.reply_text(f"✅ 您已有有效授权，有效期至: {expire_str}")
            return

        # 2. Check for pending request
        stmt_req = select(TrialRequest).where(
            TrialRequest.user_id == user_id, 
            TrialRequest.bot_id == bot_id,
            TrialRequest.status == "pending"
        )
        result_req = await session.execute(stmt_req)
        existing_req = result_req.scalars().first()
        
        if existing_req:
             await update.message.reply_text("⏳ 您的试用申请正在审核中，请耐心等待管理员批准。")
             return

        # 3. Create Request
        new_req = TrialRequest(
            bot_id=bot_id,
            user_id=user_id,
            username=username,
            status="pending",
            duration_days=1 # Default 1 day
        )
        session.add(new_req)
        await session.commit()
        
        await update.message.reply_text("📝 试用申请已提交！\n请等待管理员审核，审核通过后您将获得试用权限。")
        
    except Exception as e:
        logger.error(f"Trial request error: {e}")
        await update.message.reply_text("❌ 申请失败，请稍后重试")
    finally:
        await session.close()

async def license_info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 到期时间
    """
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    
    session = AsyncSessionLocal()
    try:
        stmt = select(GroupConfig).where(
            GroupConfig.group_id == chat_id, GroupConfig.bot_id == bot_id
        )
        result = await session.execute(stmt)
        config = result.scalars().first()
        
        if not config or not config.expire_at:
             await update.message.reply_text("⏳ 暂无授权信息，请使用 /activate 激活")
             return

        expire_str = to_timezone(config.expire_at).strftime("%Y-%m-%d %H:%M")
        await update.message.reply_text(f"📅 你已有权限啦，结束时间：{expire_str}")
    finally:
        await session.close()
