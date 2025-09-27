import os
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Default to local SQLite for dev/test if no explicit DATABASE_URL provided.
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./dev.db"

# If using Postgres without explicit driver, prefer psycopg (v3) driver
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Modern SQLAlchemy 2.0 declarative base - maintains backward compatibility with existing models
class Base(DeclarativeBase):
    pass


def _ensure_sqlite_schema_current():
    """For local SQLite dev/test only: ensure all model tables & columns exist.

    This is a pragmatic fallback because we introduced new columns (tenant_id, etc.)
    and some tests create tables via metadata while an existing dev.db may have an
    old schema. SQLite's CREATE TABLE IF NOT EXISTS won't add columns, so we detect
    drift and rebuild (data-destructive) ONLY for the lightweight local sqlite db.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    try:
        inspector = inspect(engine)
        recreate = False
        for tbl_name, tbl in Base.metadata.tables.items():
            if not inspector.has_table(tbl_name):
                recreate = True
                break
            existing_cols = {c["name"] for c in inspector.get_columns(tbl_name)}
            model_cols = set(tbl.columns.keys())
            # If any model column missing in existing, mark for recreate
            if not model_cols.issubset(existing_cols):
                recreate = True
                break
        # Simple heuristic: if any drift, drop & recreate all (fast, tests only)
        if recreate:
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
    except Exception:
        # Fail soft; tests that call create_all will still attempt creation.
        pass


# Optionally execute auto schema sync for sqlite dev/test on import only if explicitly enabled.
# This safety valve can help during rapid iterative changes but should be OFF (unset) in CI/production
# so that Alembic migrations remain the single source of truth.
if os.getenv("AUTO_SQLITE_SYNC", "0") == "1":
    _ensure_sqlite_schema_current()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()