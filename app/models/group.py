from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, BigInteger, Numeric, Table
from sqlalchemy.orm import relationship
from app.core.database import Base
from sqlalchemy.sql import func

# Association Table for Many-to-Many
group_category_association = Table(
    'group_category_association',
    Base.metadata,
    Column('group_config_id', Integer, ForeignKey('group_configs.id'), primary_key=True),
    Column('category_id', Integer, ForeignKey('group_categories.id'), primary_key=True)
)

class GroupCategory(Base):
    __tablename__ = "group_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=True) # Optional for backward compatibility, but recommended
    name = Column(String, index=True) # Removed unique=True to allow same name for different bots
    created_at = Column(DateTime, default=func.now())
    
    # Relationship
    groups = relationship("GroupConfig", secondary=group_category_association, back_populates="categories")

class GroupConfig(Base):
    __tablename__ = "group_configs"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"))
    group_id = Column(BigInteger, index=True) # Telegram Chat ID
    group_name = Column(String, nullable=True)
    
    # Categories
    categories = relationship("GroupCategory", secondary=group_category_association, back_populates="groups")
    
    # Status
    is_active = Column(Boolean, default=False) # "开始" command toggles this
    active_start_time = Column(DateTime, nullable=True) # Record when started
    
    # Rates & Configs
    fee_percent = Column(Numeric(10, 2), default=0.00) # 费率 (Decimal)
    usd_rate = Column(Numeric(10, 4), default=0.0000) # 美元汇率 (0 = hidden)
    php_rate = Column(Numeric(10, 4), default=0.0000) # 比索汇率
    myr_rate = Column(Numeric(10, 4), default=0.0000) # 马币汇率
    thb_rate = Column(Numeric(10, 4), default=0.0000) # 泰铢汇率
    
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
    amount = Column(Numeric(18, 4)) # Supports high precision
    currency = Column(String, default="RMB") # Base currency usually RMB/CNY
    
    # Snapshot of rates at the time of transaction
    fee_applied = Column(Numeric(18, 4), default=0.0)
    usd_rate_snapshot = Column(Numeric(10, 4), default=0.0)
    
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
