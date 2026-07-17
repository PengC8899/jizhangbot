import httpx
from loguru import logger
from app.core.cache import cache_service
from datetime import datetime

class OkxService:
    def __init__(self):
        self.api_url = "https://www.okx.com/v3/c2c/tradingOrders/books"
        self.timeout = 5.0

    async def get_otc_prices(self, pay_method: str = "aliPay") -> list:
        cache_key = f"okx_otc_prices_{pay_method}"
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Connection": "keep-alive"
        }
        params = {
            "quoteCurrency": "CNY",
            "baseCurrency": "USDT",
            "side": "sell",
            "paymentMethod": pay_method,
            "tType": "sell",
            "size": "10"
        }
        
        # Retry up to 3 times
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    res = await client.get(self.api_url, params=params, headers=headers)
                    res.raise_for_status()
                    data = res.json()
                    
                    if data.get("code") != 0:
                        logger.error(f"OKX API Error: {data}")
                        continue
                    
                    sell_orders = data.get("data", {}).get("sell", [])
                    
                    # Parse and sort
                    parsed_orders = []
                    for order in sell_orders:
                        try:
                            price = float(order.get("price", 0))
                            merchant = order.get("nickName", "")
                            if price > 0 and merchant:
                                parsed_orders.append({"price": price, "merchant": merchant})
                        except ValueError:
                            continue
                    
                    # Sort by price ascending
                    parsed_orders.sort(key=lambda x: x["price"])
                    
                    # Take top 10
                    top_10 = parsed_orders[:10]
                    
                    # Cache for 10 seconds
                    if top_10:
                        await cache_service.set(cache_key, top_10, ttl=10)
                    
                    return top_10
                    
            except Exception as e:
                logger.error(f"Failed to fetch OKX OTC prices (attempt {attempt+1}/3): {e}")
                if attempt == 2:
                    return []

okx_service = OkxService()
