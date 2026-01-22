from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.core.database import AsyncSessionLocal
from app.services.ledger_service import LedgerService
from app.services.price_service import price_service
from app.services.audit_service import AuditService
import re

async def get_service():
    session = AsyncSessionLocal()
    return LedgerService(session), session

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
        user = update.effective_user
        
        service, session = await get_service()
        try:
            config = await service.get_group_config(chat_id, bot_id)
            old_rate = config.fee_percent
            config.fee_percent = rate
            await session.commit()
            
            # Audit Log
            audit = AuditService(session)
            await audit.log_action(
                user_id=user.id,
                username=user.full_name,
                action="set_rate",
                target=f"group:{chat_id}",
                details={"old_rate": float(old_rate), "new_rate": rate}
            )
            
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
    user = update.effective_user
    service, session = await get_service()
    
    try:
        config = await service.get_group_config(chat_id, bot_id)
        updated = False
        msg = ""
        changes = {}
        
        for curr, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                val = Decimal(match.group(1))
                if curr == "usd": 
                    changes["usd_old"] = config.usd_rate
                    config.usd_rate = val
                elif curr == "php": 
                    changes["php_old"] = config.php_rate
                    config.php_rate = val
                elif curr == "myr": 
                    changes["myr_old"] = config.myr_rate
                    config.myr_rate = val
                elif curr == "thb": 
                    changes["thb_old"] = config.thb_rate
                    config.thb_rate = val
                updated = True
                msg = f"✅ {curr.upper()} 汇率已设为 {val}"
                changes["currency"] = curr
                changes["new_val"] = val
                break
        
        if updated:
            await session.commit()
            
            # Audit Log
            audit = AuditService(session)
            await audit.log_action(
                user_id=user.id,
                username=user.full_name,
                action="set_currency_rate",
                target=f"group:{chat_id}",
                details=changes
            )
            
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
    admin_user = update.effective_user
    
    # Check mentions
    entities = msg.parse_entities(types=["mention", "text_mention"])
    if not entities:
        await msg.reply_text("⚠️ 请@用户来设置操作人")
        return

    service, session = await get_service()
    try:
        added_names = []
        audit_details = []
        for ent, user in entities.items():
            if user: 
                # Text Mention
                await service.add_operator(chat_id, user.id, user.full_name)
                added_names.append(user.full_name)
                audit_details.append({"user_id": user.id, "name": user.full_name})
            else:
                # Standard Mention (@username)
                pass

        if added_names:
            # Audit Log
            audit = AuditService(session)
            await audit.log_action(
                user_id=admin_user.id,
                username=admin_user.full_name,
                action="add_operator",
                target=f"group:{chat_id}",
                details={"added_users": audit_details}
            )
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

async def renewal_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 自助续费
    """
    kb = [
        [InlineKeyboardButton("15天", callback_data="renew_15"), InlineKeyboardButton("1个月(9折)", callback_data="renew_30")],
        [InlineKeyboardButton("3个月(8折)", callback_data="renew_90")]
    ]
    await update.message.reply_text("自助续费暂只支持USDT的trc通道", reply_markup=InlineKeyboardMarkup(kb))

async def renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    days_map = {"renew_15": 15, "renew_30": 30, "renew_90": 90}
    days = days_map.get(data, 0)
    
    # In real world, generate payment address here
    await query.edit_message_text(f"暂未接入支付网关。\n请联系管理员手动续费 {days} 天。")

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
        amount = Decimal(match.group(2))
        
        type_map = {'k': 'card', 'z': 'ali', 'w': 'wx'}
        ptype = type_map[prefix]
        
        usdt = await price_service.calculate(amount, ptype)
        await update.message.reply_text(f"{amount} CNY = {usdt:.2f} USDT")

async def new_member_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Welcome new members
    """
    for member in update.message.new_chat_members:
        # Ignore if it's the bot itself
        if member.id == context.bot.id:
            continue
            
        name = member.full_name
        msg = f"""<b>HYPay国际支付</b>
⭐⭐⭐欢迎 🎉 "{name}" 💙💛💙⭐⭐⭐
            加入本群
      ⭐HYPay🔥国际支付⭐

🔥HYPay 🔥 业务供需频道 @HYPay_GX 🔥"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
