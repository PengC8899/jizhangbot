from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=True) # Telegram User ID or Admin ID
    username = Column(String, nullable=True)
    action = Column(String, nullable=False, index=True) # e.g., "broadcast", "change_rate"
    target = Column(String, nullable=True) # e.g., "group:12345", "bot:1"
    details = Column(Text, nullable=True) # JSON or text details
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
