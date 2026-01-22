import secrets
import string
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.group import LicenseCode, GroupConfig
from datetime import datetime, timedelta

from app.core.cache import cache_service

class LicenseService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_code(self, days: int) -> str:
        """Generate a random license code"""
        # Format: HY-XXXX-XXXX-XXXX
        chars = string.ascii_uppercase + string.digits
        part = lambda: ''.join(secrets.choice(chars) for _ in range(4))
        code = f"HY-{part()}-{part()}-{part()}"
        
        license_obj = LicenseCode(code=code, days=days)
        self.session.add(license_obj)
        await self.session.commit()
        return code

    async def redeem_code(self, code: str, group_id: int, bot_id: int) -> tuple[bool, str]:
        """
        Redeem a code for a group.
        Returns (success, message)
        """
        # 1. Find Code
        stmt = select(LicenseCode).where(LicenseCode.code == code)
        result = await self.session.execute(stmt)
        license_obj = result.scalars().first()
        
        if not license_obj:
            return False, "无效的激活码"
            
        if license_obj.is_used:
            return False, "激活码已被使用"
            
        # 2. Find Group Config
        stmt_group = select(GroupConfig).where(
            GroupConfig.group_id == group_id, GroupConfig.bot_id == bot_id
        )
        result_group = await self.session.execute(stmt_group)
        group_config = result_group.scalars().first()
        
        if not group_config:
            # Should exist if user is interacting, but just in case
            group_config = GroupConfig(group_id=group_id, bot_id=bot_id)
            self.session.add(group_config)
        
        # 3. Apply License
        now = datetime.now()
        current_expire = group_config.expire_at or now
        
        # If expired, start from now. If active, extend.
        if current_expire < now:
            new_expire = now + timedelta(days=license_obj.days)
        else:
            new_expire = current_expire + timedelta(days=license_obj.days)
            
        group_config.expire_at = new_expire
        group_config.license_key = code
        
        # 4. Mark Code Used
        license_obj.is_used = True
        license_obj.used_by_group = group_id
        license_obj.used_at = now
        
        await self.session.commit()
        
        # Invalidate Cache
        await cache_service.invalidate_group_config(group_id, bot_id)
        
        return True, f"激活成功！有效期至：{new_expire.strftime('%Y-%m-%d %H:%M')}"

    async def check_license(self, group_id: int, bot_id: int, user_id: int = None) -> bool:
        """Check if group OR user has active license (Cached)"""
        # Helper to check dict config
        def is_valid_config(conf: dict) -> bool:
            if not conf: return False
            expire_str = conf.get('expire_at')
            if not expire_str or expire_str == 'None':
                return False
            try:
                # Handle ISO format
                expire_at = datetime.fromisoformat(str(expire_str))
                return expire_at > datetime.now()
            except:
                return False

        # 1. Check Group License
        cached = await cache_service.get_group_config(group_id, bot_id)
        if cached:
            if is_valid_config(cached):
                return True
        else:
            # Cache Miss: Fetch from DB and Cache
            stmt = select(GroupConfig).where(
                GroupConfig.group_id == group_id, GroupConfig.bot_id == bot_id
            )
            result = await self.session.execute(stmt)
            config = result.scalars().first()
            if config:
                if config.expire_at and config.expire_at > datetime.now():
                    # Cache it for future
                    config_dict = {c.name: getattr(config, c.name) for c in config.__table__.columns}
                    await cache_service.set_group_config(group_id, bot_id, config_dict)
                    return True
                else:
                     # Even if expired, cache it so we don't hit DB again immediately
                     config_dict = {c.name: getattr(config, c.name) for c in config.__table__.columns}
                     await cache_service.set_group_config(group_id, bot_id, config_dict)

        # 2. Check User License (if provided)
        if user_id:
            # Try Cache first
            cached_user = await cache_service.get_group_config(user_id, bot_id)
            if cached_user:
                if is_valid_config(cached_user):
                    return True
            else:
                 stmt_user = select(GroupConfig).where(
                    GroupConfig.group_id == user_id, GroupConfig.bot_id == bot_id
                )
                 result_user = await self.session.execute(stmt_user)
                 user_config = result_user.scalars().first()
                 if user_config:
                     config_dict = {c.name: getattr(user_config, c.name) for c in user_config.__table__.columns}
                     await cache_service.set_group_config(user_id, bot_id, config_dict)
                     
                     if user_config.expire_at and user_config.expire_at > datetime.now():
                         return True
                 
        return False
