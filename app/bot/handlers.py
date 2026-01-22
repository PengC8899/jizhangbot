import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.services.ledger_service import LedgerService
from app.models.group import GroupConfig, TrialRequest
from app.core.config import settings
from loguru import logger

from app.services.license_service import LicenseService
from app.core.utils import to_timezone, get_now

# ... (Previous imports)

async def activate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: /activate CODE
    """
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    
    # Permission: Only admin/creator
    user = update.effective_user
    member = await context.bot.get_chat_member(chat_id, user.id)
    if member.status not in ['creator', 'administrator']:
        await update.message.reply_text("⚠️ 只有管理员可以激活机器人")
        return

    # Get Code
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ 请输入激活码 (例如: /activate HY-XXXX-XXXX-XXXX)")
        return
    code = args[0]
    
    session = AsyncSessionLocal()
    service = LicenseService(session)
    try:
        success, msg = await service.redeem_code(code, chat_id, bot_id)
        if success:
            await update.message.reply_text(f"🎉 {msg}")
        else:
            await update.message.reply_text(f"❌ 激活失败: {msg}")
    finally:
        await session.close()

async def check_license_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Global Middleware to check license
    """
    if not update.effective_chat or update.effective_chat.type == "private":
        return True # Allow private or no-chat updates? Or block?
        
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    
    # Allow /activate command always
    if update.message and update.message.text:
        text = update.message.text
        if text.startswith("/activate"):
            return True
        # Allow start commands to pass through (so they can be handled or rejected with message)
        if text.startswith("/start") or text == "开始" or text == "试用":
            return True
        
    session = AsyncSessionLocal()
    service = LicenseService(session)
    try:
        # Check license for Group OR User (Creator)
        user_id = update.effective_user.id if update.effective_user else None
        
        is_valid = await service.check_license(chat_id, bot_id, user_id)
        
        if not is_valid:
            # Rate limit warning to avoid spamming
            # For now, just return False (ignore command) or send warning once per day?
            # Sending warning on every command is annoying.
            # Let's just ignore or maybe reply once.
            # Simple: Reply "License Expired"
            # But we need to be careful not to loop.
            # Only reply if it's a known command?
            # Let's just silently ignore for now or send a very short msg.
            # await update.effective_message.reply_text("⚠️ 授权已过期，请联系管理员续费。\n使用 /activate 激活")
            return False
        return True
    finally:
        await session.close()

from app.services.price_service import price_service

async def get_service():
    session = AsyncSessionLocal()
    return LedgerService(session), session

async def get_main_menu_keyboard():
    keyboard = [
        ["试用", "开始"],
        ["到期时间", "详细说明书"],
        ["自助续费", "如何设置权限人"],
        ["如何设置群内操作人", "开启/关闭计算功能"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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
             # Default trial or not active?
             await update.message.reply_text("⏳ 暂无授权信息，请使用 /activate 激活")
             return

        expire_str = to_timezone(config.expire_at).strftime("%Y-%m-%d %H:%M")
        await update.message.reply_text(f"📅 你已有权限啦，结束时间：{expire_str}")
    finally:
        await session.close()

async def renewal_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 自助续费
    """
    kb = [
        [InlineKeyboardButton("15天", callback_data="renew_15"), InlineKeyboardButton("1个月(9折)", callback_data="renew_30")],
        [InlineKeyboardButton("3个月(8折)", callback_data="renew_90")]
    ]
    await update.message.reply_text("自助续费暂只支持USDT的trc通道", reply_markup=InlineKeyboardMarkup(kb))

async def help_manual_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 详细说明书
    """
    msg = """
<b>📝 HYPay 机器人使用说明书</b>

<b>1. 基础指令</b>
- <code>开始</code> : 每天记账前必须发送
- <code>+100</code> : 记一笔入款
- <code>下发100</code> : 记一笔下发
- <code>下发100u</code> : 记一笔 U 下发 (需设置汇率)
- <code>显示账单</code> : 查看最近 5 笔

<b>2. 设置指令</b>
- <code>设置费率5%</code> : 设置费率
- <code>设置美元汇率7.3</code> : 设置 U 汇率
- <code>设置操作人 @xxx</code> : 添加操作员
- <code>删除操作人 @xxx</code> : 删除操作员
- <code>清理今天数据</code> : 重置今日账单 (慎用)

<b>3. 工具指令</b>
- <code>k100</code> : 计算 100 元卡价换 U
- <code>lz</code> / <code>lw</code> : 查支付宝/微信价格

如有问题，请联系客服。
    """
    await update.message.reply_text(msg, parse_mode='HTML')

async def permission_help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 如何设置权限人
    """
    await update.message.reply_text("请购买后再使用此功能！(目前仅限群主/管理员可操作)")

async def operator_help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 如何设置群内操作人
    """
    msg = "群内发：设置操作人 @xxxxx\n先打空格再打@，会弹出选择更方便。"
    await update.message.reply_text(msg)

async def calc_toggle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 开启/关闭计算功能
    """
    # Mock toggle
    await update.message.reply_text("已关闭计算功能 (此为模拟开关)")

# Callback Handler for Renewal
async def renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    days_map = {"renew_15": 15, "renew_30": 30, "renew_90": 90}
    days = days_map.get(data, 0)
    
    # In real world, generate payment address here
    await query.edit_message_text(f"暂未接入支付网关。\n请联系管理员手动续费 {days} 天。")

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

async def set_rate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Match: 设置费率X.X% or 更改费率X.X%
    """
    text = update.message.text
    match = re.search(r"(设置|更改)费率\s*([\d\.]+)%", text)
    if match:
        rate = float(match.group(2))
        bot_id = context.bot_data.get("db_id")
        chat_id = update.effective_chat.id
        
        service, session = await get_service()
        try:
            config = await service.get_group_config(chat_id, bot_id)
            config.fee_percent = rate
            await session.commit()
            await update.message.reply_text(f"✅ 费率已设置为: {rate}%")
        finally:
            await session.close()

async def set_currency_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Match: 设置美元汇率6.5 etc.
    """
    text = update.message.text
    # Generic regex for currency rates
    patterns = {
        "usd": r"设置美元汇率\s*([\d\.]+)",
        "php": r"设置比索汇率\s*([\d\.]+)",
        "myr": r"设置马币汇率\s*([\d\.]+)",
        "thb": r"设置泰铢汇率\s*([\d\.]+)"
    }
    
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    service, session = await get_service()
    
    try:
        config = await service.get_group_config(chat_id, bot_id)
        updated = False
        msg = ""
        
        for curr, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                val = float(match.group(1))
                if curr == "usd": config.usd_rate = val
                elif curr == "php": config.php_rate = val
                elif curr == "myr": config.myr_rate = val
                elif curr == "thb": config.thb_rate = val
                updated = True
                msg = f"✅ {curr.upper()} 汇率已设为 {val}"
                break
        
        if updated:
            await session.commit()
            await update.message.reply_text(msg)
            
    finally:
        await session.close()

async def set_operator_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    设置操作人 @user1 @user2
    """
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    msg = update.message
    
    # Check mentions
    entities = msg.parse_entities(types=["mention", "text_mention"])
    if not entities:
        await msg.reply_text("⚠️ 请@用户来设置操作人")
        return

    service, session = await get_service()
    try:
        added_names = []
        for ent, user in entities.items():
            if user: 
                # Text Mention
                await service.add_operator(chat_id, user.id, user.full_name)
                added_names.append(user.full_name)
            else:
                # Standard Mention (@username)
                # PTB parse_entities keys are MessageEntity objects, values are text/User
                # For 'mention', value is None usually if user not resolved? 
                # Wait, msg.parse_entities() returns {entity: text} if no User object?
                # No, parse_entities(types=...) returns dict {entity: text_content} usually?
                # Let's check PTB docs or source logic.
                # Actually parse_entities returns {MessageEntity: str}
                # But parse_data (not existing). 
                # For 'text_mention', entity.user is the User object.
                # For 'mention', we only have the text "@username".
                
                # We can't easily get ID from @username without bot interaction history or API call.
                # Simplified: Just tell user to use text mention or reply?
                pass

        if added_names:
            await msg.reply_text(f"✅ 已添加操作人: {', '.join(added_names)}")
        else:
            await msg.reply_text("⚠️ 只能添加已识别的用户 (请使用有效的@)")
            
    finally:
        await session.close()

async def show_operator_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    显示操作人
    """
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    
    service, session = await get_service()
    try:
        operators = await service.get_operators(chat_id)
        if not operators:
            await update.message.reply_text("📭 当前无操作人")
            return
            
        msg = "👤 <b>当前操作人列表：</b>\n"
        for op in operators:
            msg += f"- {op.username} (ID: {op.user_id})\n"
        
        await update.message.reply_text(msg, parse_mode='HTML')
    finally:
        await session.close()

async def delete_operator_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    删除操作人 @user
    """
    chat_id = update.effective_chat.id
    msg = update.message
    
    entities = msg.parse_entities(types=["mention", "text_mention"])
    if not entities:
        await msg.reply_text("⚠️ 请@用户来删除操作人")
        return

    service, session = await get_service()
    try:
        deleted_names = []
        for ent, user in entities.items():
            if user:
                await service.remove_operator(chat_id, user.id)
                deleted_names.append(user.full_name)
        
        if deleted_names:
            await msg.reply_text(f"🗑️ 已删除操作人: {', '.join(deleted_names)}")
        else:
            await msg.reply_text("⚠️ 未能识别要删除的用户")
            
    finally:
        await session.close()

async def usdt_price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    lk/lz/lw/k100/z100/w100
    """
    text = update.message.text.lower().strip()
    
    # List Prices
    if text in ['lk', 'lz', 'lw']:
        prices = await price_service.get_prices()
        # Mock logic
        type_map = {'lk': 'card', 'lz': 'ali', 'lw': 'wx'}
        name_map = {'lk': '银行卡', 'lz': '支付宝', 'lw': '微信'}
        
        ptype = type_map[text]
        price = prices.get(ptype)
        
        await update.message.reply_text(f"欧易 {name_map[text]} 实时价格: {price}")
        return

    # Calculate
    # k100 -> card, 100 RMB -> ? USDT
    match = re.match(r"^([kzw])(\d+(\.\d+)?)$", text)
    if match:
        prefix = match.group(1)
        amount = float(match.group(2))
        
        type_map = {'k': 'card', 'z': 'ali', 'w': 'wx'}
        ptype = type_map[prefix]
        
        usdt = await price_service.calculate(amount, ptype)
        await update.message.reply_text(f"{amount} CNY = {usdt:.2f} USDT")

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

async def mode_setting_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    设置为无小数 / 设置为计数模式 / 设置为原始模式
    """
    text = update.message.text
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    
    service, session = await get_service()
    try:
        config = await service.get_group_config(chat_id, bot_id)
        
        if "无小数" in text:
            config.decimal_mode = False
            msg = "✅ 已设置为无小数模式"
        elif "计数模式" in text:
            config.simple_mode = True
            msg = "✅ 已设置为计数模式"
        elif "原始模式" in text:
            config.decimal_mode = True
            config.simple_mode = False
            msg = "✅ 已恢复原始模式"
            
        await session.commit()
        await update.message.reply_text(msg)
    finally:
        await session.close()

import json
from app.models.bot import Bot

async def handle_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle: +1000, 下发1000, 下发100u, 入款-100 (Correction)
    """
    # ... (Keep existing code)
    text = update.message.text
    if not text: return
    
    # 1. Parse Command
    deposit_match = re.match(r"^(\+|入款)\s*(-?\d+(\.\d+)?)", text)
    payout_match = re.match(r"^(下发)\s*(-?\d+(\.\d+)?)(u|U)?", text)
    
    if not (deposit_match or payout_match):
        return

    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    service, session = await get_service()
    try:
        # Check if active
        if not await service.is_group_active(chat_id, bot_id):
            await update.message.reply_text("⚠️ 请先输入“开始”以开启今日记录")
            return

        type_ = "deposit"
        amount = 0.0
        is_usdt_amount = False
        
        if deposit_match:
            type_ = "deposit"
            amount = float(deposit_match.group(2))
        elif payout_match:
            type_ = "payout"
            amount = float(payout_match.group(2))
            if payout_match.group(4): # 'u' suffix
                is_usdt_amount = True
            
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
        
        # Calculate Logic
        total_in = summary['total_deposit']
        fee = total_in * (config.fee_percent / 100.0)
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
            [InlineKeyboardButton(bill_text, url=f"https://{settings.DOMAIN}/bill/{chat_id}")],
            [InlineKeyboardButton(biz_text, url=biz_url), InlineKeyboardButton(complaint_text, url=complaint_url)],
            [InlineKeyboardButton(support_text, url=support_url)]
        ]
        
        await update.message.reply_text(reply, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        
    finally:
        await session.close()

def setup_handlers(application):
    # Activate Command
    application.add_handler(CommandHandler("activate", activate_cmd))
    
    # Middleware Enforcer (High Priority)
    # We use a global handler with group=-1 to check license before others.
    # If license is invalid, we stop propagation.
    
    async def license_enforcer(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await check_license_middleware(update, context):
            # Block all other handlers
            from telegram.ext import ApplicationHandlerStop
            raise ApplicationHandlerStop 
            
    from telegram.ext import TypeHandler
    application.add_handler(TypeHandler(Update, license_enforcer), group=-1)

    # Regex handlers
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^开始$"), start_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^结束记录$"), stop_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"(设置|更改)费率"), set_rate_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"设置.*汇率"), set_currency_rate))
    
    # New Handlers
    application.add_handler(MessageHandler(filters.Regex(r"^显示账单$"), show_bill_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^清理今天数据$"), clear_data_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^设置为(无小数|计数模式|原始模式)$"), mode_setting_cmd))
    
    # USDT Commands
    application.add_handler(MessageHandler(filters.Regex(re.compile(r"^(lk|lz|lw|k\d+|z\d+|w\d+)$", re.IGNORECASE)), usdt_price_cmd))
    
    # Transactions (Updated regex for negative & 'u')
    # Allow leading spaces: ^\s*
    application.add_handler(MessageHandler(filters.Regex(r"^\s*(\+|入款|下发)"), handle_transaction))
    
    # Operator Management
    application.add_handler(MessageHandler(filters.Regex(r"^设置操作人"), set_operator_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^显示操作人$"), show_operator_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^删除操作人"), delete_operator_cmd))

    # Fallback handler to catch messages that might be commands but not matched by strict regex
    # Especially for "+1000" or "1000" which might be treated as text
    # Allow leading spaces: ^\s*
    application.add_handler(MessageHandler(filters.Regex(r"^\s*(\+|-)?\d+"), handle_transaction))

    # Menu Handlers
    application.add_handler(MessageHandler(filters.Regex(r"^试用$"), trial_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^到期时间$"), license_info_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^自助续费$"), renewal_menu_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^详细说明书$"), help_manual_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^如何设置权限人$"), permission_help_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^如何设置群内操作人$"), operator_help_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^开启/关闭计算功能$"), calc_toggle_cmd))
    
async def new_member_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Welcome new members
    """
    for member in update.message.new_chat_members:
        # Ignore if it's the bot itself (handled by other logic usually, or just ignore)
        if member.id == context.bot.id:
            continue
            
        name = member.full_name
        # Match the style in screenshot:
        # HYPay国际支付
        # ⭐⭐⭐欢迎 🎉 "Name" 💙💛💙⭐⭐⭐
        # 加入本群
        # ⭐HYPay🔥国际支付⭐
        # 🔥HYPay 🔥 业务供需频道 @HYPay_GX 🔥
        
        msg = f"""<b>HYPay国际支付</b>
⭐⭐⭐欢迎 🎉 "{name}" 💙💛💙⭐⭐⭐
            加入本群
      ⭐HYPay🔥国际支付⭐

🔥HYPay 🔥 业务供需频道 @HYPay_GX 🔥"""
        
        await update.message.reply_text(msg, parse_mode='HTML')

    # Callback
    application.add_handler(CallbackQueryHandler(renewal_callback, pattern=r"^renew_"))
    
    # Welcome Message
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_welcome))

