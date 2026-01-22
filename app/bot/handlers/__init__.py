import re
from telegram.ext import CommandHandler, MessageHandler, filters, CallbackQueryHandler, TypeHandler, Application
from telegram import Update

# Import handlers
from .system import (
    check_license_middleware, activate_cmd, trial_cmd, license_info_cmd, broadcast_cmd
)
from .transaction import (
    start_cmd, stop_cmd, handle_transaction, show_bill_cmd, clear_data_cmd
)
from .admin import (
    set_rate_cmd, set_currency_rate, set_operator_cmd, show_operator_cmd, delete_operator_cmd,
    mode_setting_cmd, renewal_menu_cmd, renewal_callback, help_manual_cmd,
    permission_help_cmd, operator_help_cmd, calc_toggle_cmd, usdt_price_cmd, new_member_welcome
)

def setup_handlers(application: Application):
    # Activate Command
    application.add_handler(CommandHandler("activate", activate_cmd))
    
    # Broadcast Command
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    
    # Middleware Enforcer (High Priority)
    async def license_enforcer(update: Update, context):
        if not await check_license_middleware(update, context):
            # Block all other handlers
            from telegram.ext import ApplicationHandlerStop
            raise ApplicationHandlerStop 
            
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
    application.add_handler(MessageHandler(filters.Regex(r"^\s*(\+|-)?\d+"), handle_transaction))

    # Menu Handlers
    application.add_handler(MessageHandler(filters.Regex(r"^试用$"), trial_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^到期时间$"), license_info_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^自助续费$"), renewal_menu_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^详细说明书$"), help_manual_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^如何设置权限人$"), permission_help_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^如何设置群内操作人$"), operator_help_cmd))
    application.add_handler(MessageHandler(filters.Regex(r"^开启/关闭计算功能$"), calc_toggle_cmd))
    
    # Callback
    application.add_handler(CallbackQueryHandler(renewal_callback, pattern=r"^renew_"))
    
    # Welcome Message
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_welcome))
