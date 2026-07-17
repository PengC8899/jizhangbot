from telegram import Update
from telegram.ext import ContextTypes
from loguru import logger
from datetime import datetime
from app.services.okx_service import okx_service
import time

def format_otc_prices(prices: list, pay_method_name: str) -> str:
    if not prices:
        return "暂无符合条件的广告。"

    lines = [f"【欧易OTC实时报价 - {pay_method_name}】\n"]
    for item in prices:
        # Keep 2 decimals, don't truncate merchant name
        lines.append(f"{item['price']:.2f} {item['merchant']}")
    
    lines.append(f"\n更新时间：\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)

async def otc_query_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle: z0, z1, z2
    """
    logger.info("otc_query_cmd triggered")
    
    # Debug info
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    logger.info(f"OTC query context - Chat Type: {chat_type}, User ID: {user_id}")
    
    raw_text = update.message.text or update.message.caption
    if not raw_text: return
    text = raw_text.strip().lower()
    
    pay_methods = {
        "z0": ("aliPay", "支付宝"),
        "z1": ("bank", "银行卡"),
        "z2": ("wxPay", "微信")
    }
    
    if text not in pay_methods:
        return
        
    method_code, method_name = pay_methods[text]
    
    start_time = time.time()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        prices = await okx_service.get_otc_prices(pay_method=method_code)
        
        elapsed = time.time() - start_time
        logger.info(f"OTC Query | chat_id:{chat_id} | user_id:{user_id} | time:{elapsed:.2f}s | count:{len(prices)}")
        
        if not prices:
            await update.message.reply_text("欧易OTC报价获取失败或暂无符合条件的广告，请稍后再试。")
            return
            
        reply_text = format_otc_prices(prices, method_name)
        await update.message.reply_text(reply_text)
        
    except Exception as e:
        logger.error(f"Error handling OTC query: {e}")
        await update.message.reply_text("欧易OTC报价获取失败，请稍后再试。")
