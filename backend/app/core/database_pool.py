import asyncio
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database connection pool"""
        if self.session_factory:
            return

        async with self._init_lock:
            if self.session_factory:
                return
            await self._create_engine()

    async def _create_engine(self):
        try:
            # Create async engine with connection pooling
            database_url = settings.database_url
            for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
                if database_url.startswith(prefix):
                    database_url = "postgresql+asyncpg://" + database_url[len(prefix):]
                    break

            self.engine = create_async_engine(
                database_url,
                pool_size=20,  # Number of connections to maintain
                max_overflow=30,  # Additional connections when needed
                pool_pre_ping=True,  # Validate connections
                pool_recycle=3600,  # Recycle connections every hour
                echo=False  # Set to True for SQL debugging
            )
            
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("✅ Database connection pool initialized")
            
        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            self.engine = None
            self.session_factory = None
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session from pool"""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        session: AsyncSession = self.session_factory()
        try:
            yield session
        finally:
            await session.close()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
