from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from sqlalchemy import text

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_schema(conn)
    await _seed_default_admin()


async def _seed_default_admin():
    from sqlalchemy import select

    from app.models import ConsoleUser
    from app.services.console_auth import hash_password

    async with async_session() as session:
        result = await session.execute(
            select(ConsoleUser).where(ConsoleUser.username == "admin")
        )
        if result.scalar_one_or_none():
            return
        session.add(ConsoleUser(
            username="admin",
            first_name="Admin",
            last_name="Console",
            email="admin@lab-console.local",
            password_hash=hash_password("admin"),
            must_change_password=False,
            is_admin=True,
            is_active=True,
        ))
        await session.commit()


async def _migrate_schema(conn):
    """Add columns introduced after initial deploy."""
    migrations = [
        "ALTER TABLE workshops ADD COLUMN duration_days INTEGER DEFAULT 5",
        "ALTER TABLE azure_connections ADD COLUMN auth_type VARCHAR(16) DEFAULT 'oauth'",
        """CREATE TABLE IF NOT EXISTS app_settings (
            key VARCHAR(64) PRIMARY KEY,
            value TEXT DEFAULT ''
        )""",
        """CREATE TABLE IF NOT EXISTS azure_auth_sessions (
            id VARCHAR(36) PRIMARY KEY,
            flow_type VARCHAR(16),
            flow_data_encrypted TEXT,
            status VARCHAR(16) DEFAULT 'pending',
            tenant_id VARCHAR(64) DEFAULT '',
            tenant_name VARCHAR(256) DEFAULT '',
            username VARCHAR(256) DEFAULT '',
            refresh_token_encrypted TEXT DEFAULT '',
            oauth_client_id VARCHAR(64) DEFAULT '',
            subscriptions_json TEXT DEFAULT '[]',
            error_message TEXT DEFAULT '',
            created_at DATETIME,
            expires_at DATETIME
        )""",
        "ALTER TABLE azure_auth_sessions ADD COLUMN oauth_client_id VARCHAR(64) DEFAULT ''",
        "ALTER TABLE workshops ADD COLUMN created_by_user_id INTEGER",
    ]
    for sql in migrations:
        try:
            await conn.execute(text(sql))
        except Exception:
            pass


async def get_db():
    async with async_session() as session:
        yield session
