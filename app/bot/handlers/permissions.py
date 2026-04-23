from telegram import Update
from telegram.ext import ContextTypes
from loguru import logger

async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the user is an admin or creator of the chat."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['creator', 'administrator']:
            return True
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
    return False

async def check_operator_permission(update: Update, context: ContextTypes.DEFAULT_TYPE, service) -> bool:
    """
    Check if the user has permission to operate the bot in this group.
    Rules:
    1. Admin/creator always allowed.
    2. If NO operators exist for this group, allow everyone.
    3. If operators EXIST, user must be in the operator list.
    """
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = f"@{update.effective_user.username}" if update.effective_user.username else None
    
    # 1. Admin check
    if await check_admin(update, context):
        return True
        
    # 2. Check if there are operators
    operators = await service.get_operators(chat_id)
    if not operators:
        return True # Default to allow all if no operators configured
        
    # 3. Operator check
    if await service.is_operator(chat_id, user_id, username):
        return True
        
    return False