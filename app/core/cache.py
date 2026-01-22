import redis.asyncio as redis
from app.core.config import settings
import json
from loguru import logger
import asyncio
import time
from decimal import Decimal

class CacheEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

class CacheService:
    def __init__(self):
        self.redis = None
        self.enabled = False
        self.ttl = 300 # 5 minutes default
        self._last_connect_attempt = 0
        self._retry_interval = 60  # Retry every 60 seconds

        if settings.REDIS_URL:
            self._init_redis()
    
    def _init_redis(self):
        try:
            self.redis = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            self.enabled = True
            logger.info("Redis initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client: {e}")
            self.enabled = False
            self._last_connect_attempt = time.time()

    async def _ensure_connection(self):
        if self.enabled:
            return True
            
        now = time.time()
        if now - self._last_connect_attempt < self._retry_interval:
            return False
            
        self._last_connect_attempt = now
        try:
            if not self.redis:
                self.redis = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            
            await self.redis.ping()
            self.enabled = True
            logger.info("Redis reconnected successfully")
            return True
        except Exception as e:
            logger.error(f"Redis reconnection failed: {e}")
            self.enabled = False
            return False

    async def get_group_config(self, group_id: int, bot_id: int):
        if not self.enabled:
            if not await self._ensure_connection():
                return None
            
        key = f"group_config:{bot_id}:{group_id}"
        try:
            data = await self.redis.get(key)
            if data:
                return json.loads(data, parse_float=Decimal)
        except Exception as e:
            # If connection refused, disable cache to avoid spam
            if "Connection refused" in str(e) or "Error 61" in str(e):
                logger.error(f"Redis connection lost: {e}. Disabling cache.")
                self.enabled = False
            else:
                logger.error(f"Redis get error: {e}")
        return None

    async def set_group_config(self, group_id: int, bot_id: int, config_dict: dict):
        if not self.enabled:
            return

        key = f"group_config:{bot_id}:{group_id}"
        try:
            # Filter out non-serializable fields (like datetime) before caching
            serializable = {k: str(v) if k in ['created_at', 'updated_at', 'active_start_time', 'expire_at'] and v else v 
                           for k, v in config_dict.items()}
            
            await self.redis.setex(key, self.ttl, json.dumps(serializable, cls=CacheEncoder))
        except Exception as e:
            if "Connection refused" in str(e) or "Error 61" in str(e):
                self.enabled = False
            logger.error(f"Redis set error: {e}")

    async def invalidate_group_config(self, group_id: int, bot_id: int):
        if not self.enabled:
            return

        key = f"group_config:{bot_id}:{group_id}"
        try:
            await self.redis.delete(key)
        except Exception as e:
            if "Connection refused" in str(e) or "Error 61" in str(e):
                self.enabled = False
            logger.error(f"Redis delete error: {e}")

cache_service = CacheService()
