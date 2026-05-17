from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from app.core.database import AsyncSessionLocal
from app.services.ledger_service import LedgerService
from app.services.config_service import get_bot_button_config
from app.core.config import settings
from app.models.bot import Bot
from app.core.utils import to_timezone, format_number
from app.bot.handlers.permissions import check_operator_permission
import re
import json
from decimal import Decimal

MANUAL_USD_RATE_PATTERN = re.compile(
    r"^(?:\+|入款)\s*-?\d+(?:\.\d+)?\s*/\s*(\d+(?:\.\d+)?)\s*$"
)


def extract_manual_usd_rate(text: str | None) -> Decimal | None:
    if not text:
        return None
    match = MANUAL_USD_RATE_PATTERN.match(text.strip())
    if not match:
        return None
    return Decimal(match.group(1))


def get_record_usd_rate(record, fallback_rate: Decimal) -> Decimal:
    snapshot = getattr(record, "usd_rate_snapshot", None)
    if snapshot is None:
        return fallback_rate

    snapshot_decimal = Decimal(str(snapshot))
    if snapshot_decimal > 0:
        return snapshot_decimal

    return fallback_rate


def get_payout_usdt_amount(record, fallback_rate: Decimal) -> Decimal:
    if hasattr(record, 'original_text') and record.original_text:
        pm = re.match(r"^(下发)\s*(-?\d+(\.\d+)?)(u|U)?", record.original_text)
        if pm and pm.group(4):
            return Decimal(pm.group(2))

    rate = get_record_usd_rate(record, fallback_rate)
    if rate > 0:
        return Decimal(str(record.amount)) / rate

    return Decimal(0)

def build_default_start_welcome() -> str:
    return """<b>╔══════✦══════╗</b>
<b>欢迎使用本机器人</b>
<b>请按下方菜单开始操作</b>
<b>╚══════✦══════╝</b>"""

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

    service, session = await get_service()
    try:
        if not await check_operator_permission(update, context, service):
            return
    finally:
        await session.close()

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
    is_private_chat = update.effective_chat.type == "private"

    service, session = await get_service()
    try:
        if is_private_chat:
            btn_config = await get_bot_button_config(bot_id, session)
            start_welcome_text = (btn_config.get("start_welcome_text") or "").strip()
            welcome_flag = f"start_welcome_shown_{bot_id}"

            if not context.user_data.get(welcome_flag):
                welcome_message = start_welcome_text or build_default_start_welcome()
                try:
                    await update.message.reply_text(welcome_message, parse_mode='HTML')
                except Exception:
                    await update.message.reply_text(welcome_message)
                context.user_data[welcome_flag] = True

            await update.message.reply_text(
                "✅ 机器人已开启，请使用下方菜单开始操作",
                reply_markup=await get_main_menu_keyboard()
            )
            return

        if not await check_operator_permission(update, context, service):
            return # Silent return for no permission

        # Update Group Name when starting
        group_title = update.effective_chat.title
        # Ensure config exists and update name
        await service.get_group_config(chat_id, bot_id, group_name=group_title)

        await service.start_recording(chat_id, bot_id)

        await update.message.reply_text("✅ 机器人已开启，开始记录今日账单 (4:00 - 4:00)")
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
        if not await check_operator_permission(update, context, service):
            return # Silent return for no permission
            
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
        # Check permissions
        if not await check_operator_permission(update, context, service):
            return # Silent return for no permission

        # Check if active
        if not await service.is_group_active(chat_id, bot_id):
            return # Silent return for inactive group

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
        default_usd_rate = Decimal(str(config.usd_rate or 0))
        manual_usd_rate = extract_manual_usd_rate(text) if type_ == "deposit" else None
        effective_usd_rate = manual_usd_rate or default_usd_rate
        
        if is_usdt_amount:
            if effective_usd_rate <= 0:
                await update.message.reply_text("⚠️ 未设置美元汇率，无法使用 U 结算")
                return
            amount = amount * effective_usd_rate
            
        # Record
        await service.record_transaction(
            bot_id,
            chat_id,
            type_,
            amount,
            user.id,
            user.full_name,
            text,
            usd_rate_snapshot=effective_usd_rate,
        )
        
        # Reply with summary
        summary = await service.get_daily_summary(chat_id, bot_id)
        daily_records = await service.get_daily_records(chat_id, bot_id)
        
        # Calculate Logic (All Decimal)
        total_in = summary['total_deposit']
        fee = total_in * (config.fee_percent / Decimal(100))
        net_in = total_in - fee
        should_pay = net_in
        pending_pay = should_pay - summary['total_payout']
        
        # Construct Message
        reply = f"入款 ({summary['count_deposit']}笔)：\n"
        recent_deposits = await service.get_recent_records(chat_id, bot_id, limit=5, record_type="deposit")
        for r in recent_deposits:
            time_str = to_timezone(r.created_at).strftime("%H:%M:%S")
            # Format number with commas
            val_fmt = f"{int(r.amount):,}" if not config.decimal_mode else format_number(r.amount)
            val_str = f"<b>{val_fmt}</b>"

            record_usd_rate = get_record_usd_rate(r, default_usd_rate)
            if record_usd_rate > 0:
                fee_multiplier = (Decimal(100) - Decimal(config.fee_percent)) / Decimal(100)
                if fee_multiplier == Decimal(1):
                    usdt_val = r.amount / record_usd_rate
                    val_str += f"/{format_number(record_usd_rate)}={format_number(usdt_val)}"
                else:
                    usdt_val = r.amount * fee_multiplier / record_usd_rate
                    val_str += f"*{format_number(fee_multiplier)}/{format_number(record_usd_rate)}={format_number(usdt_val)}"
            reply += f"  {time_str} {val_str}\n"
        reply += "\n"
        
        reply += f"下发 ({summary['count_payout']}笔)：\n"
        recent_payouts = await service.get_recent_records(chat_id, bot_id, limit=5, record_type="payout")
        for r in recent_payouts:
             time_str = to_timezone(r.created_at).strftime("%H:%M:%S")
             
             # Check if original input was in U
             is_u_payout = False
             original_u_amount = None
             if hasattr(r, 'original_text') and r.original_text:
                 pm = re.match(r"^(下发)\s*(-?\d+(\.\d+)?)(u|U)?", r.original_text)
                 if pm and pm.group(4):
                     is_u_payout = True
                     original_u_amount = Decimal(pm.group(2))
             
             if is_u_payout and original_u_amount is not None:
                 val_fmt = f"{int(original_u_amount):,}U" if not config.decimal_mode else f"{format_number(original_u_amount)}U"
             else:
                 val_fmt = f"{int(r.amount):,}" if not config.decimal_mode else format_number(r.amount)
                 
             reply += f"  {time_str}  <b>{val_fmt}</b>\n"
        reply += "\n"

        total_in_fmt = f"{int(total_in):,}" if not config.decimal_mode else format_number(total_in)
        reply += f"总入款: {total_in_fmt}\n"
        
        # Display fee percent nicely (e.g. 7% or 5.5%)
        fee_str = f"{int(config.fee_percent)}%" if config.fee_percent == int(config.fee_percent) else f"{config.fee_percent}%"
        reply += f"费率: {fee_str}\n"
        
        usd_rates_used = {
            get_record_usd_rate(r, default_usd_rate)
            for r in daily_records
            if get_record_usd_rate(r, default_usd_rate) > 0
        }

        should_pay_usdt = Decimal(0)
        payout_usdt_total = Decimal(0)
        fee_multiplier = (Decimal(100) - Decimal(config.fee_percent)) / Decimal(100)

        for r in daily_records:
            record_usd_rate = get_record_usd_rate(r, default_usd_rate)
            if r.type == "deposit" and record_usd_rate > 0:
                should_pay_usdt += Decimal(str(r.amount)) * fee_multiplier / record_usd_rate
            elif r.type == "payout":
                payout_usdt_total += get_payout_usdt_amount(r, default_usd_rate)

        pending_pay_usdt = should_pay_usdt - payout_usdt_total

        if default_usd_rate > 0:
            reply += f"汇率: {format_number(default_usd_rate)}\n"
        elif usd_rates_used:
            only_rate = next(iter(usd_rates_used))
            reply += f"汇率: {format_number(only_rate)}\n"

        if usd_rates_used:
            
            should_pay_fmt = f"{int(should_pay):,}" if not config.decimal_mode else format_number(should_pay)
            pending_pay_fmt = f"{int(pending_pay):,}" if not config.decimal_mode else format_number(pending_pay)
            
            reply += f"\n应下发: {should_pay_fmt} | {format_number(should_pay_usdt)} U\n"
            reply += f"未下发: {pending_pay_fmt} | {format_number(pending_pay_usdt)} U\n"
        else:
             should_pay_fmt = f"{int(should_pay):,}" if not config.decimal_mode else format_number(should_pay)
             pending_pay_fmt = f"{int(pending_pay):,}" if not config.decimal_mode else format_number(pending_pay)
             reply += f"\n应下发: {should_pay_fmt}\n"
             reply += f"未下发: {pending_pay_fmt}\n"

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
        if not await check_operator_permission(update, context, service):
            return # Silent return for no permission
            
        records = await service.get_recent_records(chat_id, bot_id, limit=5)
        if not records:
            await update.message.reply_text("📭 暂无账单记录")
            return
            
        msg = "📄 <b>最近 5 笔账单：</b>\n\n"
        for r in records:
            icon = "🟢" if r.type == "deposit" else "🔴"
            t_name = "入款" if r.type == "deposit" else "下发"
            time_str = to_timezone(r.created_at).strftime("%H:%M:%S")
            
            amount_str = f"{r.amount}"
            if r.type == "payout" and hasattr(r, 'original_text') and r.original_text:
                pm = re.match(r"^(下发)\s*(-?\d+(\.\d+)?)(u|U)?", r.original_text)
                if pm and pm.group(4):
                    amount_str = f"{pm.group(2)}U"
            
            msg += f"{icon} {time_str} <b>{t_name}</b> {amount_str}\n"
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

    service, session = await get_service()
    try:
        if not await check_operator_permission(update, context, service):
            return

        await service.delete_today_records(chat_id, bot_id)
        await update.message.reply_text("🗑️ 今日数据已清理")
    finally:
        await session.close()
