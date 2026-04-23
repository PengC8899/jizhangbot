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
    1. Admin/creator always allowed (telegram group admin).
    2. Bot Admin (from admin panel) - allowed in ALL groups.
    3. Group Operator - allowed only in the group where they were added.
    4. Everyone else - denied.
    """
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = f"@{update.effective_user.username}" if update.effective_user.username else None
    bot_id = context.bot_data.get("db_id")

    # 1. Telegram Group Admin check
    if await check_admin(update, context):
        return True

    # 2. Bot Admin (from admin panel) - global access for this bot
    if await service.is_bot_admin(bot_id, user_id):
        return True

    # 3. Group Operator - check if operators exist for this bot in this group
    operators = await service.get_operators(chat_id, bot_id)
    if operators:
        # If operators are configured, only they can operate (except admins)
        if await service.is_operator(chat_id, user_id, username, bot_id):
            return True
        return False

    # 4. No operators configured AND not a bot admin - deny
    return False