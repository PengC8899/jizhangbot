from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from app.core.database import Base
import datetime

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    group_id = Column(String, index=True) # Chat ID
    type = Column(String) # "deposit" (入款) or "payout" (下发)
    amount = Column(Float)
    currency = Column(String, default="USDT")
    status = Column(String, default="completed")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
