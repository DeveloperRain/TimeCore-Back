"""Configuración de conexión a base de datos con SQLAlchemy."""
import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine, pool
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()


# Por defecto usa SQLite (sin servidor externo)
# Para PostgreSQL, cambia a: postgresql://user:password@host:port/database
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "zk_attendance")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite")  # "sqlite" o "postgresql"
DATABASE_URL_ENV = os.getenv("DATABASE_URL")

# Configurar URL según el motor
if DATABASE_URL_ENV:
    DATABASE_URL = DATABASE_URL_ENV
elif DB_ENGINE.lower() == "postgresql":
    user = quote_plus(DB_USER)
    password = quote_plus(DB_PASSWORD)
    DATABASE_URL = f"postgresql+psycopg://{user}:{password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    # SQLite - archivo local (recomendado para desarrollo)
    DATABASE_URL = f"sqlite:///./zk_attendance.db"

engine = create_engine(
    DATABASE_URL,
    poolclass=pool.NullPool if DB_ENGINE.lower() == "postgresql" else pool.StaticPool,
    echo=False,
    connect_args={"check_same_thread": False} if DB_ENGINE.lower() == "sqlite" else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Obtiene sesión de base de datos."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """Crea todas las tablas en la base de datos."""
    from app.models.user import User
    from app.models.attendance import AttendanceRecord

    Base.metadata.create_all(bind=engine)
       