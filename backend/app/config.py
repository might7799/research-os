import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
PRODUCTION_ENVS = {"prod", "production"}

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    if APP_ENV in PRODUCTION_ENVS:
        raise RuntimeError("DATABASE_URL must be configured for production")
    DATABASE_URL = f"sqlite:///{BASE_DIR / 'data' / 'research_os.db'}"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET or len(JWT_SECRET.encode("utf-8")) < 32:
    raise RuntimeError("JWT_SECRET must be set to at least 32 bytes")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
if JWT_ALGORITHM != "HS256":
    raise RuntimeError("JWT_ALGORITHM must be HS256")

if APP_ENV in PRODUCTION_ENVS and not DATABASE_URL.startswith("postgresql://"):
    raise RuntimeError("Production requires PostgreSQL")
if not DATABASE_URL.startswith(("postgresql://", "sqlite:///")):
    raise RuntimeError("DATABASE_URL must use PostgreSQL or SQLite")

JWT_ACCESS_TOKEN_TTL_SECONDS = int(os.getenv("JWT_ACCESS_TOKEN_TTL_SECONDS", "3600"))
if JWT_ACCESS_TOKEN_TTL_SECONDS <= 0:
    raise RuntimeError("JWT_ACCESS_TOKEN_TTL_SECONDS must be positive")
