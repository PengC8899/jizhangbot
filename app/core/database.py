from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event
from sqlalchemy.engine import Engine
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL

# SQLite Optimization for High Concurrency (WAL Mode)
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000") # Wait up to 5s before locking
        cursor.close()

# Connection Pool Configuration
# For SQLite: NullPool is usually recommended if using a file, but here we use default (QueuePool/SingletonThreadPool depending on driver)
# For asyncpg (PostgreSQL) we would set pool_size=20, max_overflow=10 etc.
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_async_engine(
    DATABASE_URL, 
    echo=False, 
    future=True,
    connect_args=connect_args,
    pool_pre_ping=True # Health check connections
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
