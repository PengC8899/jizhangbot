import redis.asyncio as redis
from app.core.config import settings
import json
from loguru import logger

class CacheService:
    def __init__(self):
        self.redis = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        self.ttl = 300 # 5 minutes default

    async def get_group_config(self, group_id: int, bot_id: int):
        key = f"group_config:{bot_id}:{group_id}"
        try:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
        return None

    async def set_group_config(self, group_id: int, bot_id: int, config_dict: dict):
        key = f"group_config:{bot_id}:{group_id}"
        try:
            # Filter out non-serializable fields (like datetime) before caching
            # For now, we assume caller handles serialization or we do simple dump
            # We need to be careful with datetime objects.
            serializable = {k: str(v) if k in ['created_at', 'updated_at', 'active_start_time', 'expire_at'] and v else v 
                           for k, v in config_dict.items()}
            
            await self.redis.setex(key, self.ttl, json.dumps(serializable))
        except Exception as e:
            logger.error(f"Redis set error: {e}")

    async def invalidate_group_config(self, group_id: int, bot_id: int):
        key = f"group_config:{bot_id}:{group_id}"
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error: {e}")

cache_service = CacheService()