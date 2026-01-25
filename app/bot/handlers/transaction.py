from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from app.core.database import AsyncSessionLocal
from app.services.ledger_service import LedgerService
from app.core.config import settings
from app.models.bot import Bot
from app.core.utils import to_timezone
import re
import json
from decimal import Decimal

async def get_service():
    session = AsyncSessionLocal()
    return LedgerService(session), session

async def get_main_menu_keyboard():
    keyboard = [
        ["试用", "开始"],
        ["到期时间", "详细说明书"],
        ["自助续费", "如何设置权限人"],
        ["如何设置群内操作人", "开启/关闭计算功能"],
        ["群发管理"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def group_broadcast_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User types "群发管理"
    """
    bot_id = context.bot_data.get("db_id")
    url = f"http://{settings.DOMAIN}/customer/login?bot_id={bot_id}"
    
    kb = [
        [InlineKeyboardButton("🔗 进入群发管理后台", url=url)]
    ]
    
    await update.message.reply_text(
        "📢 <b>群发管理后台</b>\n\n"
        "点击下方按钮进入独立的群发管理系统。\n"
        f"登录账号 (Bot ID): <code>{bot_id}</code>\n"
        "登录密码: (请使用 /set_password 设置)",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode='HTML'
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User types "开始" -> Start recording
    """
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    
    service, session = await get_service()
    try:
        # Update Group Name when starting
        group_title = update.effective_chat.title
        # Ensure config exists and update name
        await service.get_group_config(chat_id, bot_id, group_name=group_title)
        
        await service.start_recording(chat_id, bot_id)
        
        # Only show keyboard in Private Chat
        reply_markup = None
        if update.effective_chat.type == "private":
            reply_markup = await get_main_menu_keyboard()
            
        await update.message.reply_text(
            "✅ 机器人已开启，开始记录今日账单 (4:00 - 4:00)",
            reply_markup=reply_markup
        )
    finally:
        await session.close()

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User types "结束记录"
    """
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    
    service, session = await get_service()
    try:
        await service.stop_recording(chat_id, bot_id)
        await update.message.reply_text("🛑 记录已结束")
    finally:
        await session.close()

async def handle_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle: +1000, 下发1000, 下发100u, 入款-100 (Correction)
    """
    text = update.message.text
    if not text: return
    
    # Debug log
    from loguru import logger
    logger.info(f"Transaction handler received: {text}")
    
    # 1. Parse Command
    # Support "+1000", "+ 1000", "入款1000", "入款 1000"
    # Also support implicit positive numbers if configured, but let's stick to explicit for now
    # We need to be careful about regex. 
    # ^\+? -> Optional plus at start? No, explicit plus is safer to avoid chatting interference.
    
    deposit_match = re.match(r"^(\+|入款)\s*(-?\d+(\.\d+)?)", text)
    payout_match = re.match(r"^(下发)\s*(-?\d+(\.\d+)?)(u|U)?", text)
    
    # Fallback for just "+10000" without space if re.match is strict
    if not deposit_match:
         # Try matching just the number with + prefix
         # This handles: "+10000", "+ 10000"
         simple_plus_match = re.match(r"^\+\s*(\d+(\.\d+)?)", text)
         if simple_plus_match:
             deposit_match = simple_plus_match
             # Adjust group index mapping if needed. 
             # For simple_plus_match: group(1) is the amount.
             # We need to normalize how we extract amount below.
    
    if not (deposit_match or payout_match or (text.strip().startswith('+') and text.strip()[1:].replace('.', '', 1).isdigit())):
        logger.info(f"Ignored message: {text}")
        return

    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    service, session = await get_service()
    try:
        # Check if active
        if not await service.is_group_active(chat_id, bot_id):
            logger.info(f"Group {chat_id} not active")
            await update.message.reply_text("⚠️ 请先输入“开始”以开启今日记录")
            return

        type_ = "deposit"
        amount = Decimal(0)
        is_usdt_amount = False
        
        if payout_match:
            type_ = "payout"
            amount = Decimal(payout_match.group(2))
            if payout_match.group(4): # 'u' suffix
                is_usdt_amount = True
        elif deposit_match:
            type_ = "deposit"
            # If matched by main regex: group(2) is amount
            # If matched by simple_plus_match: group(1) is amount
            # Let's unify extraction.
            if len(deposit_match.groups()) >= 2 and deposit_match.group(2):
                 amount = Decimal(deposit_match.group(2))
            else:
                 # Fallback extraction
                 amount_str = re.search(r"(-?\d+(\.\d+)?)", text).group(0)
                 amount = Decimal(amount_str)
        else:
             # Fallback simple + case
             amount_str = text.strip().replace('+', '').strip()
             amount = Decimal(amount_str)
             type_ = "deposit"
            
        # Get Config (and update group name)
        group_title = update.effective_chat.title
        config = await service.get_group_config(chat_id, bot_id, group_name=group_title)
        
        if is_usdt_amount:
            if config.usd_rate <= 0:
                await update.message.reply_text("⚠️ 未设置美元汇率，无法使用 U 结算")
                return
            amount = amount * config.usd_rate
            
        # Record
        await service.record_transaction(
            bot_id, chat_id, type_, amount, user.id, user.full_name, text
        )
        
        # Reply with summary
        summary = await service.get_daily_summary(chat_id, bot_id)
        
        # Calculate Logic (All Decimal)
        total_in = summary['total_deposit']
        fee = total_in * (config.fee_percent / Decimal(100))
        net_in = total_in - fee
        should_pay = net_in
        pending_pay = should_pay - summary['total_payout']
        
        # Formatting
        def fmt(val):
            if not config.decimal_mode:
                return f"{int(val)}"
            return f"{val:.2f}"

        # Construct Message
        reply = f"<b>HYPay国际支付</b>\n"
        
        reply += f"入款 ({summary['count_deposit']}笔)：\n"
        recent_deposits = await service.get_recent_records(chat_id, bot_id, limit=5, record_type="deposit")
        for r in recent_deposits:
            time_str = to_timezone(r.created_at).strftime("%H:%M:%S")
            val_str = f"<b>{fmt(r.amount)}</b>"
            if config.usd_rate > 0:
                usdt_val = r.amount / config.usd_rate
                val_str += f" / {config.usd_rate}={usdt_val:.2f}"
            reply += f"  {time_str}  {val_str}\n"
        reply += "\n"
        
        reply += f"下发 ({summary['count_payout']}笔)：\n"
        recent_payouts = await service.get_recent_records(chat_id, bot_id, limit=5, record_type="payout")
        for r in recent_payouts:
             time_str = to_timezone(r.created_at).strftime("%H:%M:%S")
             reply += f"  {time_str}  <b>{fmt(r.amount)}</b>\n"
        reply += "\n"

        reply += f"总入款: {fmt(total_in)}\n"
        reply += f"费率: {config.fee_percent}%\n"
        
        if config.usd_rate > 0:
            reply += f"汇率: {config.usd_rate}\n"
            should_pay_usdt = should_pay / config.usd_rate
            pending_pay_usdt = pending_pay / config.usd_rate
            reply += f"\n应下发: {pending_pay_usdt:.2f} USDT\n"
            reply += f"未下发: {pending_pay_usdt:.2f} USDT\n"
        else:
             reply += f"\n应下发: {fmt(should_pay)}\n"
             reply += f"未下发: {fmt(pending_pay)}\n"

        # --- Dynamic Buttons Logic ---
        # Fetch Bot Config
        bot = await session.get(Bot, bot_id)
        btn_config = {}
        if bot and bot.button_config:
            try:
                btn_config = json.loads(bot.button_config)
            except:
                pass
        
        # Defaults
        bill_text = btn_config.get("bill_text") or "点击跳转完整账单"
        biz_text = btn_config.get("biz_text") or "业务对接"
        biz_url = btn_config.get("biz_url") or "https://t.me/"
        complaint_text = btn_config.get("complaint_text") or "投诉建议"
        complaint_url = btn_config.get("complaint_url") or "https://t.me/"
        support_text = btn_config.get("support_text") or "24小时客服"
        support_url = btn_config.get("support_url") or "https://t.me/"
        
        kb = [
            [InlineKeyboardButton(bill_text, url=f"http://{settings.DOMAIN}/bill/{chat_id}")],
            [InlineKeyboardButton(biz_text, url=biz_url), InlineKeyboardButton(complaint_text, url=complaint_url)],
            [InlineKeyboardButton(support_text, url=support_url)]
        ]
        
        await update.message.reply_text(reply, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        
    finally:
        await session.close()

async def show_bill_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    显示账单: Recent 5
    """
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    
    service, session = await get_service()
    try:
        records = await service.get_recent_records(chat_id, bot_id, limit=5)
        if not records:
            await update.message.reply_text("📭 暂无账单记录")
            return
            
        msg = "📄 <b>最近 5 笔账单：</b>\n\n"
        for r in records:
            icon = "🟢" if r.type == "deposit" else "🔴"
            t_name = "入款" if r.type == "deposit" else "下发"
            time_str = to_timezone(r.created_at).strftime("%H:%M:%S")
            msg += f"{icon} {time_str} <b>{t_name}</b> {r.amount}\n"
            msg += f"   👤 操作: {r.operator_name}\n"
        
        await update.message.reply_text(msg, parse_mode='HTML')
    finally:
        await session.close()

async def clear_data_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    清理今天数据
    """
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    
    # Permission check: usually only admin
    user = update.effective_user
    member = await context.bot.get_chat_member(chat_id, user.id)
    if member.status not in ['creator', 'administrator']:
        await update.message.reply_text("⚠️ 只有管理员可以执行此操作")
        return

    service, session = await get_service()
    try:
        await service.delete_today_records(chat_id, bot_id)
        await update.message.reply_text("🗑️ 今日数据已清理")
    finally:
        await session.close()
