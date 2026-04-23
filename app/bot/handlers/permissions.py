from telegram import Update
from telegram.ext import ContextTypes
from loguru import logger

def normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    return username.strip().lower()

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
    1. Bot Admin (from admin panel) - allowed in ALL groups.
    2. Group Operator - allowed only in the group where they were added.
    3. Everyone else - denied.
    """
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = normalize_username(
        f"@{update.effective_user.username}" if update.effective_user.username else None
    )
    bot_id = context.bot_data.get("db_id")

    # 1. Bot Admin (from admin panel) - global access for this bot
    if await service.is_bot_admin(bot_id, user_id, username):
        return True

    # 2. Group Operator - allowed only in the current bot + current group
    if await service.is_operator(chat_id, user_id, username, bot_id):
        return True

    # 3. No operator configured or not matched - deny
    return False

async def check_operator_management_permission(update: Update, context: ContextTypes.DEFAULT_TYPE, service) -> bool:
    """
    Users who already have bot permission can manage group operators.
    This includes:
    1. Bot Admin (global for this bot)
    2. Group Operator (current group only)
    """
    return await check_operator_permission(update, context, service)
