import httpx
from loguru import logger
from decimal import Decimal

class PriceService:
    """
    Mock Price Service for USDT/CNY.
    In a real-world scenario, this would connect to OKEx, Binance, or other OTC API.
    """
    
    # Mock base prices
    _mock_prices = {
        "okex": {"card": 7.35, "ali": 7.38, "wx": 7.39},
        "binance": {"card": 7.34, "ali": 7.37, "wx": 7.38}
    }

    async def get_prices(self):
        # TODO: Implement real API call
        # For now, return mock data with slight random variation? 
        # Or just static for "reproduction" purpose.
        return self._mock_prices["okex"]

    async def calculate(self, cny_amount: Decimal, method: str = "card") -> Decimal:
        prices = await self.get_prices()
        # Ensure rate is Decimal
        rate_val = prices.get(method, 7.35)
        rate = Decimal(str(rate_val))
        
        if rate == 0: return Decimal(0)
        return cny_amount / rate

price_service = PriceService()
