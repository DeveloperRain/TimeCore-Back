"""Configuración de conexión a base de datos con SQLAlchemy."""
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, pool, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "zk_attendance")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite")
DATABASE_URL_ENV = os.getenv("DATABASE_URL")

if DATABASE_URL_ENV:
    DATABASE_URL = DATABASE_URL_ENV
elif DB_ENGINE.lower() == "postgresql":
    user = quote_plus(DB_USER)
    password = quote_plus(DB_PASSWORD)
    DATABASE_URL = f"postgresql+psycopg://{user}:{password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    DATABASE_URL = "sqlite:///./zk_attendance.db"

engine = create_engine(
    DATABASE_URL,
    poolclass=pool.NullPool if DB_ENGINE.lower() == "postgresql" else pool.StaticPool,
    echo=False,
    connect_args={"check_same_thread": False} if DB_ENGINE.lower() == "sqlite" else {},
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
    """Crea todas las tablas registradas en los modelos."""
    from app.models.attendance import AttendanceRecord
    from app.models.branch import Branch
    from app.models.device import Device
    from app.models.log import Log
    from app.models.system_user import SystemUser
    from app.models.user import User

    Base.metadata.create_all(bind=engine)
    ensure_user_profile_columns()


def ensure_user_profile_columns():
    """Agrega columnas nuevas de perfil si la tabla users ya existía."""
    inspector = inspect(engine)

    if "users" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("users")
    }

    columns_to_add = {
        "area": "VARCHAR(100)",
        "empresa": "VARCHAR(100)",
    }

    with engine.begin() as connection:
        for column_name, column_type in columns_to_add.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                )
