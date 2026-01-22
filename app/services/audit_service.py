from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog
from loguru import logger
import json
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_action(self, user_id: int, username: str, action: str, target: str = None, details: dict = None, ip_address: str = None):
        """
        Record an audit log entry.
        """
        try:
            details_str = json.dumps(details, ensure_ascii=False, cls=DecimalEncoder) if details else None
            
            log_entry = AuditLog(
                user_id=user_id,
                username=username,
                action=action,
                target=target,
                details=details_str,
                ip_address=ip_address
            )
            self.session.add(log_entry)
            await self.session.commit()
            logger.info(f"AUDIT: {username}({user_id}) performed {action} on {target}")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            # Do not raise exception to avoid breaking the main flow
