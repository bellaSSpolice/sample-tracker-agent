"""SQLAlchemy engine, session management, and migration runner."""

import logging
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app import config

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def get_engine():
    """Lazy-create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        db_url = config.DATABASE_URL
        if not db_url:
            raise RuntimeError("DATABASE_URL environment variable is not set")
        _engine = create_engine(db_url, pool_pre_ping=True, pool_size=5)
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal


def get_session() -> Session:
    """Create a new database session."""
    return get_session_factory()()


def run_migrations():
    """Run SQL migration files in order. Idempotent (uses IF NOT EXISTS)."""
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    if not os.path.exists(migrations_dir):
        logger.warning("No migrations directory found at %s", migrations_dir)
        return

    migration_files = sorted(
        f for f in os.listdir(migrations_dir) if f.endswith(".sql")
    )

    engine = get_engine()
    for filename in migration_files:
        filepath = os.path.join(migrations_dir, filename)
        logger.info("Running migration: %s", filename)
        with open(filepath, "r") as f:
            sql = f.read()
        with engine.begin() as conn:
            conn.execute(text(sql))
        logger.info("Migration complete: %s", filename)


def reset_engine():
    """Reset engine and session factory (used in testing)."""
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
