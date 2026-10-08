import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine
)
from config.settings import DATABASE_URL
from db.models import Base

logger = logging.getLogger(__name__)


# Normalize URL for async driver if needed
normalized_db_url = (DATABASE_URL or "").strip()
if normalized_db_url.startswith("postgres://"):
    normalized_db_url = normalized_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif normalized_db_url.startswith("postgresql://"):
    normalized_db_url = normalized_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif normalized_db_url.startswith("sqlite://"):
    normalized_db_url = normalized_db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

# SQLite concurrency tuning or PostgreSQL connection pool
engine_kwargs = {"echo": False, "future": True}

if "sqlite" in normalized_db_url:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Handle cloud PostgreSQL (Neon, Supabase, Render, Aiven)
    if "postgresql+asyncpg://" in normalized_db_url:
        # Strip query parameters that asyncpg doesn't parse natively, and enforce SSL
        if "?" in normalized_db_url:
            base_url, query_part = normalized_db_url.split("?", 1)
            normalized_db_url = base_url
        engine_kwargs["connect_args"] = {"ssl": "require"}

    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_pre_ping"] = True

engine: AsyncEngine = create_async_engine(normalized_db_url, **engine_kwargs)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

def _run_migrations(sync_conn):
    """Safely adds missing columns to existing SQLite / PostgreSQL tables without data loss."""
    inspector = inspect(sync_conn)
    tables = inspector.get_table_names()

    # Migration for youtube_accounts
    if "youtube_accounts" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("youtube_accounts")}
        col_defs = {
            "name": "VARCHAR(128) DEFAULT 'YouTube Account'",
            "channel_id": "VARCHAR(64)",
            "channel_title": "VARCHAR(255)",
            "status": "VARCHAR(32) DEFAULT 'ACTIVE'",
            "uploads_today": "INTEGER DEFAULT 0",
            "last_upload_at": "TIMESTAMP",
            "limit_detected_at": "TIMESTAMP",
            "cooldown_until": "TIMESTAMP",
            "priority": "INTEGER DEFAULT 1",
            "last_error": "TEXT",
            "last_error_type": "VARCHAR(64)",
            "quota_reset_date": "TIMESTAMP"
        }
        for col_name, col_type in col_defs.items():
            if col_name not in existing_cols:
                try:
                    sync_conn.execute(text(f"ALTER TABLE youtube_accounts ADD COLUMN {col_name} {col_type}"))
                except Exception as ex:
                    logger.debug(f"[MIGRATION] Column {col_name} already exists or alter skipped: {ex}")

    # Migration for videos
    if "videos" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("videos")}
        col_defs = {
            "youtube_channel_id": "VARCHAR(64)",
            "youtube_account_id": "VARCHAR(64)",
            "youtube_url": "VARCHAR(512)",
            "upload_completed_at": "TIMESTAMP"
        }
        for col_name, col_type in col_defs.items():
            if col_name not in existing_cols:
                try:
                    sync_conn.execute(text(f"ALTER TABLE videos ADD COLUMN {col_name} {col_type}"))
                except Exception as ex:
                    logger.debug(f"[MIGRATION] Column {col_name} on videos skipped: {ex}")

    # Migration for youtube_uploads
    if "youtube_uploads" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("youtube_uploads")}
        col_defs = {
            "account_id": "VARCHAR(64)",
            "channel_id": "VARCHAR(64)",
            "youtube_url": "VARCHAR(512)",
            "upload_completed_at": "TIMESTAMP"
        }
        for col_name, col_type in col_defs.items():
            if col_name not in existing_cols:
                try:
                    sync_conn.execute(text(f"ALTER TABLE youtube_uploads ADD COLUMN {col_name} {col_type}"))
                except Exception as ex:
                    logger.debug(f"[MIGRATION] Column {col_name} on youtube_uploads skipped: {ex}")

async def init_db():
    """Initializes all database tables safely and runs pending migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_migrations)
    logger.info("Database tables verified / initialized successfully.")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for obtaining an async DB session."""
    session: AsyncSession = AsyncSessionFactory()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e
    finally:
        await session.close()

async def get_db_dependency() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for injecting DB session into endpoints."""
    async with get_db_session() as session:
        yield session
