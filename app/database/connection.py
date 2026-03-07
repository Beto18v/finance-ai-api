# Conecta la API con PostgreSQL utilizando SQLAlchemy. Crea un motor de base de datos y una fábrica de sesiones para manejar las conexiones a la base de datos.

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

connect_args: dict[str, str] = {}

# Supabase Postgres requires SSL; if the URL doesn't include sslmode, default to require.
db_sslmode = os.getenv("DB_SSLMODE")
if db_sslmode:
    connect_args["sslmode"] = db_sslmode
elif "supabase.co" in DATABASE_URL and "sslmode=" not in DATABASE_URL:
    connect_args["sslmode"] = "require"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=300,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)