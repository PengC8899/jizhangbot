from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, BigInteger
from sqlalchemy.orm import relationship
from app.core.database import Base
from sqlalchemy.sql import func

class GroupConfig(Base):
    __tablename__ = "group_configs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    group_id = Column(BigInteger, index=True) # Telegram Chat ID
    group_name = Column(String, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=False) # "开始" command toggles this
    active_start_time = Column(DateTime, nullable=True) # Record when started
    
    # Rates & Configs
    fee_percent = Column(Float, default=0.0) # 费率
    usd_rate = Column(Float, default=0.0) # 美元汇率 (0 = hidden)
    php_rate = Column(Float, default=0.0) # 比索汇率
    myr_rate = Column(Float, default=0.0) # 马币汇率
    thb_rate = Column(Float, default=0.0) # 泰铢汇率
    
    # Display Modes
    decimal_mode = Column(Boolean, default=True) # True=Show decimals, False=No decimals
    simple_mode = Column(Boolean, default=False) # True=只显示入款简洁模式
    
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Licensing
    expire_at = Column(DateTime, nullable=True) # Expiration date
    license_key = Column(String, nullable=True) # Bound license key

class LicenseCode(Base):
    __tablename__ = "license_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    days = Column(Integer) # Duration in days
    is_used = Column(Boolean, default=False)
    used_by_group = Column(BigInteger, nullable=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

class Operator(Base):
    __tablename__ = "operators"
    
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(BigInteger, index=True)
    user_id = Column(BigInteger) # Telegram User ID
    username = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())

class LedgerRecord(Base):
    __tablename__ = "ledger_records"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    group_id = Column(BigInteger, index=True)
    operator_id = Column(BigInteger, nullable=True) # Who performed the action
    operator_name = Column(String, nullable=True)
    
    type = Column(String) # "deposit" (入款), "payout" (下发)
    amount = Column(Float)
    currency = Column(String, default="RMB") # Base currency usually RMB/CNY
    
    # Snapshot of rates at the time of transaction
    fee_applied = Column(Float, default=0.0)
    usd_rate_snapshot = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=func.now())
    original_text = Column(String, nullable=True) # The command text

class TrialRequest(Base):
    __tablename__ = "trial_requests"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    user_id = Column(BigInteger, index=True) # Requesting User ID (chat_id)
    username = Column(String, nullable=True)
    status = Column(String, default="pending") # pending, approved, rejected
    duration_days = Column(Integer, default=1) # Default trial duration
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
