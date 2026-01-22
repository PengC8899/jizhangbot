from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base
import datetime

class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, nullable=False)  # In real world, encrypt this!
    name = Column(String, nullable=True)
    status = Column(String, default="active") # active, disabled
    created_at = Column(DateTime, default=func.now())
    webhook_secret = Column(String, nullable=True)
    
    # Relationships
    fee_template = relationship("BotFeeTemplate", back_populates="bot", uselist=False)
    exchange_template = relationship("BotExchangeTemplate", back_populates="bot", uselist=False)

class BotFeeTemplate(Base):
    __tablename__ = "bot_fee_templates"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), unique=True)
    fee_percent = Column(Float, default=0.0)
    
    bot = relationship("Bot", back_populates="fee_template")

class BotExchangeTemplate(Base):
    __tablename__ = "bot_exchange_templates"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), unique=True)
    usd_rate = Column(Float, default=1.0)
    php_rate = Column(Float, default=1.0)
    myr_rate = Column(Float, default=1.0)
    thb_rate = Column(Float, default=1.0)
    decimal_mode = Column(Integer, default=2)

    bot = relationship("Bot", back_populates="exchange_template")

# Group level override would be similar, but let's stick to the prompt's main request for Bot level first
# and mention Group level in design.
