import re
from telegram.ext import CommandHandler, MessageHandler, filters, CallbackQueryHandler, TypeHandler, Application
from telegram import Update

# Import handlers
from .system import (
    check_license_middleware, activate_cmd, trial_cmd, license_info_cmd, broadcast_cmd
)
from app.bot.handlers.transaction import (
    start_cmd, stop_cmd, handle_transaction, show_bill_cmd, clear_data_cmd, group_broadcast_menu_cmd
)
from app.bot.handlers.otc import otc_query_cmd
from .admin import (
    set_rate_cmd, set_currency_rate, set_operator_cmd, show_operator_cmd, delete_operator_cmd,
    mode_setting_cmd, renewal_menu_cmd, renewal_callback, help_manual_cmd,
    permission_help_cmd, operator_help_cmd, calc_toggle_cmd, usdt_price_cmd, new_member_welcome,
    set_web_password_cmd
)

def setup_handlers(application: Application):
    # System Commands (English Only for CommandHandler)
    application.add_handler(CommandHandler("activate", activate_cmd))
    application.add_handler(CommandHandler("set_password", set_web_password_cmd))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    
    # Chinese 'Commands' (Handled as Text/Regex to avoid invalid command name error)
    # Matches "/激活" or "激活"
    application.add_handler(MessageHandler(filters.Regex(r"^/?激活"), activate_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^/?设置密码"), set_web_password_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^/?(群发|广播)$"), broadcast_cmd)) # Strict match to avoid conflict with "群发管理"

    # Middleware Enforcer (High Priority)
    async def license_enforcer(update: Update, context):
        if not await check_license_middleware(update, context):
            # Block all other handlers
            from telegram.ext import ApplicationHandlerStop
            raise ApplicationHandlerStop 
            
    application.add_handler(TypeHandler(Update, license_enforcer), group=-1)

    # Start/Stop Commands (English)
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("stop", stop_cmd))

    # Start/Stop Commands (Chinese - Regex)
    application.add_handler(MessageHandler(filters.Regex(r"^/?开始$"), start_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^/?(结束|结束记录)$"), stop_cmd))
    
    # Text Triggers (Regex) - Keep for backward compatibility and keyboard buttons
    application.add_handler(MessageHandler(filters.Regex(r"(设置|更改)费率"), set_rate_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"设置.*汇率"), set_currency_rate))
    
    # New Handlers
    application.add_handler(MessageHandler(filters.Regex(r"^显示账单$"), show_bill_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^清理今天数据$"), clear_data_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^设置为(无小数|计数模式|原始模式)$"), mode_setting_cmd))
    
    # USDT Commands
    # Moving usdt_price_cmd down below
    # application.add_handler(MessageHandler(filters.Regex(re.compile(r"^(lk|lz|lw|k\d+|z\d+|w\d+)$", re.IGNORECASE)), usdt_price_cmd))
    
    # Transactions (Updated regex for negative & 'u')
    # Allow leading spaces: ^\s*
    # Fix: Ensure +10000 is matched. 
    # Current regex: r"^\s*(\+|入款|下发)" - This only checks prefix.
    # The handler itself re-checks regex.
    # Let's broaden it to include numbers starting with +
    application.add_handler(MessageHandler(filters.Regex(r"^\s*(\+|入款|下发)"), handle_transaction))
    
    # Also add specific catch for just "+Number" which might be missed if filter is too strict
    # Use simpler regex for robustness
    application.add_handler(MessageHandler(filters.Regex(r"^\s*\+\d+"), handle_transaction))
    
    # And catch any number that looks like a transaction (fallback)
    # application.add_handler(MessageHandler(filters.Regex(r"^\s*(\+|-)?\d+(\.\d+)?$"), handle_transaction))

    # Support transactions in photo captions (without regex filter because filters.Regex only checks message.text)
    # This handler specifically catches captioned media
    application.add_handler(MessageHandler(filters.CAPTION & ~filters.COMMAND, handle_transaction))

    # Operator Management
    application.add_handler(MessageHandler(filters.Regex(r"^设置操作人"), set_operator_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^显示操作人$"), show_operator_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^删除操作人"), delete_operator_cmd))

    # OTC Query Commands (z0, z1, z2) - MUST be here to not be intercepted by general handler
    otc_regex = re.compile(r"^\s*(z0|z1|z2)\s*$", re.IGNORECASE)
    # Using a dedicated group to avoid any interception by default handlers
    application.add_handler(MessageHandler(filters.Regex(otc_regex), otc_query_cmd), group=5)
    application.add_handler(MessageHandler(filters.CAPTION & filters.Regex(otc_regex), otc_query_cmd), group=5)

    # Re-enable USDT commands here to ensure they run after transaction
    # Exclude exactly z0, z1, z2 from matching the USDT calculator
    usdt_regex = re.compile(r"^(lk|lz|lw|[kw]\d+(?:\.\d+)?|z(?!(?:0|1|2)$)\d+(?:\.\d+)?)$", re.IGNORECASE)
    application.add_handler(MessageHandler(filters.Regex(usdt_regex), usdt_price_cmd))

    # Fallback logging handler to debug missed messages
    # This should be at the very end
    async def log_missed_message(update: Update, context):
        if update.message:
            text = update.message.text or update.message.caption
            if text:
                from loguru import logger
                logger.info(f"Missed message: {text}")
            
    application.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, log_missed_message), group=99)

    # Fallback handler to catch messages that might be commands but not matched by strict regex
    # application.add_handler(MessageHandler(filters.Regex(r"^\s*(\+|-)?\d+"), handle_transaction))

    # Menu Handlers
    application.add_handler(MessageHandler(filters.Regex(r"^试用$"), trial_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^到期时间$"), license_info_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^自助续费$"), renewal_menu_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^详细说明书$"), help_manual_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^如何设置权限人$"), permission_help_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^如何设置群内操作人$"), operator_help_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^开启/关闭计算功能$"), calc_toggle_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^群发管理$"), group_broadcast_menu_cmd))
    
    # Callback
    application.add_handler(CallbackQueryHandler(renewal_callback, pattern=r"^renew_"))
    
    # Welcome Message
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_welcome))
