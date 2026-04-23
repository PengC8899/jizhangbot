from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.core.database import AsyncSessionLocal
from app.services.ledger_service import LedgerService
from app.services.price_service import price_service
from app.services.audit_service import AuditService
from app.bot.handlers.permissions import check_admin, check_operator_permission
from decimal import Decimal
import re
import logging

logger = logging.getLogger(__name__)

async def get_service():
    session = AsyncSessionLocal()
    return LedgerService(session), session

async def set_rate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Match: 设置费率X.X% or 更改费率X.X%
    """
    text = update.message.text
    match = re.search(r"(设置|更改)费率\s*([\d\.]+)(%?)", text)
    if match:
        rate = float(match.group(2))
        bot_id = context.bot_data.get("db_id")
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        service, session = await get_service()
        try:
            if not await check_operator_permission(update, context, service):
                return # Silent return for no permission
                
            config = await service.get_group_config(chat_id, bot_id)
            old_rate = config.fee_percent
            await service.update_group_config(chat_id, bot_id, fee_percent=rate)
            
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
        "usd": r"设置(?:美元)?汇率\s*([\d\.]+)",
        "php": r"设置比索汇率\s*([\d\.]+)",
        "myr": r"设置马币汇率\s*([\d\.]+)",
        "thb": r"设置泰铢汇率\s*([\d\.]+)"
    }
    
    bot_id = context.bot_data.get("db_id")
    chat_id = update.effective_chat.id
    user = update.effective_user
    service, session = await get_service()
    
    try:
        if not await check_operator_permission(update, context, service):
            return # Silent return for no permission
            
        config = await service.get_group_config(chat_id, bot_id)
        updated = False
        msg = ""
        changes = {}
        
        for curr, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                val = Decimal(match.group(1))
                update_kwargs = {}
                if curr == "usd": 
                    changes["usd_old"] = config.usd_rate
                    update_kwargs["usd_rate"] = val
                elif curr == "php": 
                    changes["php_old"] = config.php_rate
                    update_kwargs["php_rate"] = val
                elif curr == "myr": 
                    changes["myr_old"] = config.myr_rate
                    update_kwargs["myr_rate"] = val
                elif curr == "thb": 
                    changes["thb_old"] = config.thb_rate
                    update_kwargs["thb_rate"] = val
                
                await service.update_group_config(chat_id, bot_id, **update_kwargs)
                updated = True
                msg = f"✅ {curr.upper()} 汇率已设为 {val}"
                changes["currency"] = curr
                changes["new_val"] = float(val)
                break
        
        if updated:
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
    
    if not await check_admin(update, context):
        await msg.reply_text("⚠️ 只有群管理员才能设置操作人")
        return
        
    # Check mentions
    entities = msg.parse_entities(types=["mention", "text_mention"])
    if not entities:
        await msg.reply_text("⚠️ 请@用户来设置操作人")
        return

    service, session = await get_service()
    try:
        added_names = []
        audit_details = []
        for ent, text in entities.items():
            if ent.type == "text_mention" and ent.user: 
                # Text Mention
                await service.add_operator(chat_id, ent.user.id, ent.user.full_name)
                added_names.append(ent.user.full_name)
                audit_details.append({"user_id": ent.user.id, "name": ent.user.full_name})
            elif ent.type == "mention":
                # Standard Mention (@username)
                username = text.strip()
                await service.add_operator(chat_id, 0, username)
                added_names.append(username)
                audit_details.append({"user_id": 0, "name": username})

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
    
    if not await check_admin(update, context):
        await msg.reply_text("⚠️ 只有群管理员才能删除操作人")
        return
        
    entities = msg.parse_entities(types=["mention", "text_mention"])
    if not entities:
        await msg.reply_text("⚠️ 请@用户来删除操作人")
        return

    service, session = await get_service()
    try:
        deleted_names = []
        for ent, text in entities.items():
            if ent.type == "text_mention" and ent.user:
                await service.remove_operator(chat_id, ent.user.id)
                deleted_names.append(ent.user.full_name)
            elif ent.type == "mention":
                username = text.strip()
                await service.remove_operator(chat_id, 0, username=username)
                deleted_names.append(username)
        
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
            await service.update_group_config(chat_id, bot_id, decimal_mode=False)
            await update.message.reply_text("✅ 已切换为无小数模式")
        elif "计数模式" in text:
            await service.update_group_config(chat_id, bot_id, simple_mode=True)
            await update.message.reply_text("✅ 已切换为计数模式")
        elif "原始模式" in text:
            await service.update_group_config(chat_id, bot_id, decimal_mode=True, simple_mode=False)
            await update.message.reply_text("✅ 已恢复原始模式")
    finally:
        await session.close()

async def renewal_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 自助续费
    """
    msg = """<code>TA2A9WZVtu6SXdRQU3HovdBx2WCRNKyn9C</code>

付款后联系管理 @Pcccc6"""
    await update.message.reply_text(msg, parse_mode='HTML')

async def renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Deprecated callback but kept to avoid errors if old buttons exist
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("请联系管理 @Pcccc6")

async def help_manual_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 详细说明书
    """
    msg = """
<b>📝 HYPay 机器人使用说明书</b>

<b>1. 基础指令 (支持中文命令)</b>
- <code>/开始</code> (或 <code>/start</code>) : 每天记账前必须发送
- <code>/结束</code> (或 <code>/stop</code>) : 停止记账
- <code>+100</code> : 记一笔入款 (或 <code>入款100</code>)
- <code>下发100</code> : 记一笔下发
- <code>下发100u</code> : 记一笔 U 下发 (需设置汇率)
- <code>显示账单</code> : 查看最近 5 笔

<b>2. 设置指令</b>
- <code>设置费率5%</code> : 设置费率
- <code>设置美元汇率7.3</code> : 设置 U 汇率
- <code>设置操作人 @xxx</code> : 添加操作员
- <code>删除操作人 @xxx</code> : 删除操作员
- <code>清理今天数据</code> : 重置今日账单 (慎用)

<b>3. 管理指令</b>
- <code>/激活 code</code> : 激活机器人
- <code>/群发</code> : 广播消息 (或 <code>群发管理</code> 按钮)

<b>4. 工具指令</b>
- <code>k100</code> : 计算 100 元卡价换 U
- <code>lz</code> / <code>lw</code> : 查支付宝/微信价格

如有问题，请联系客服。
    """
    await update.message.reply_text(msg, parse_mode='HTML')

async def permission_help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 如何设置权限人
    """
    await update.message.reply_text("联系管理 @Pcccc6")

async def set_web_password_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User: 设置密码 <password>
    Sets the password for the Web Management Interface.
    """
    bot_id = context.bot_data.get("db_id")
    args = context.args
    
    # Permission Check: Only group creator/administrator can set password
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text("⚠️ 只有群管理员可以设置密码")
            return
    except Exception as e:
        logger.error(f"Failed to check admin status: {e}")
        await update.message.reply_text("⚠️ 无法验证权限，请联系客服")
        return

    if not args:
        await update.message.reply_text("⚠️ 请输入密码，例如: /设置密码 123456")
        return
        
    password = args[0]
    if len(password) < 6:
        await update.message.reply_text("⚠️ 密码长度至少为 6 位")
        return
        
    service, session = await get_service()
    try:
        from app.models.bot import Bot
        bot = await session.get(Bot, bot_id)
        if bot:
            bot.web_password = password
            await session.commit()
            await update.message.reply_text(f"✅ 管理后台密码已设置为: {password}\n请在群发管理页面使用 Bot ID ({bot_id}) 和此密码登录。")
        else:
            await update.message.reply_text("❌ 机器人数据不存在")
    finally:
        await session.close()

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
