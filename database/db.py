from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import DATABASE_URL
from database.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)

async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Создаёт все таблицы, если их ещё нет. Вызывается один раз при старте бота."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)