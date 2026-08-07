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
    """Obtiene sesión de base de datos.

    :return: Generador que produce la sesión local de la base de datos.
    :rtype: Iterator[sqlalchemy.orm.Session]
    """
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Crea todas las tablas registradas en los modelos.

    :return: No retorna ningún valor.
    :rtype: None
    """
    from app.models.attendance import AttendanceRecord
    from app.models.branch import Branch
    from app.models.device import Device
    from app.models.log import Log
    from app.models.payroll_incident import PayrollIncident
    from app.models.system_user import SystemUser
    from app.models.user import User

    Base.metadata.create_all(bind=engine)
    ensure_user_profile_columns()
    ensure_device_company_column()
    ensure_device_password_column()
    ensure_device_auto_sync_columns()
    ensure_payroll_incident_soft_delete_columns()
    ensure_no_hard_delete_protection()
    ensure_performance_indexes()


def ensure_user_profile_columns():
    """Agrega columnas nuevas de perfil si la tabla users ya existía.

    :return: No retorna ningún valor.
    :rtype: None
    """
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


def ensure_device_company_column():
    """Agrega la columna empresa si la tabla devices ya existía.

    :return: No retorna ningún valor.
    :rtype: None
    """
    inspector = inspect(engine)

    if "devices" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("devices")
    }

    if "empresa" not in existing_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE devices ADD COLUMN empresa VARCHAR(100)")
            )



def ensure_device_password_column():
    """Agrega la columna password si la tabla devices ya existía.

    :return: No retorna ningún valor.
    :rtype: None
    """
    inspector = inspect(engine)

    if "devices" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("devices")
    }

    if "password" not in existing_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE devices ADD COLUMN password VARCHAR(100) DEFAULT ''")
            )



def ensure_device_auto_sync_columns():
    """Agrega configuración de sincronización automática por reloj.

    :return: No retorna ningún valor.
    :rtype: None
    """
    inspector = inspect(engine)

    if "devices" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("devices")
    }

    columns_to_add = {
        "auto_sync_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "sync_interval_minutes": "INTEGER NOT NULL DEFAULT 4",
        "last_sync_at": "TIMESTAMP NULL",
    }

    with engine.begin() as connection:
        for column_name, column_type in columns_to_add.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE devices ADD COLUMN {column_name} {column_type}")
                )

        connection.execute(
            text("UPDATE devices SET auto_sync_enabled = TRUE WHERE auto_sync_enabled IS NULL")
        )
        connection.execute(
            text("UPDATE devices SET sync_interval_minutes = 4 WHERE sync_interval_minutes IS NULL OR sync_interval_minutes < 1")
        )


def ensure_payroll_incident_soft_delete_columns():
    """Agrega las columnas necesarias para el borrado lógico de incidencias.

    :return: No retorna ningún valor.
    :rtype: None
    """
    inspector = inspect(engine)

    if "payroll_incidents" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("payroll_incidents")
    }

    columns_to_add = {
        "is_active": "BOOLEAN NOT NULL DEFAULT TRUE",
        "deleted_at": "TIMESTAMP NULL",
    }

    with engine.begin() as connection:
        for column_name, column_type in columns_to_add.items():
            if column_name not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE payroll_incidents "
                        f"ADD COLUMN {column_name} {column_type}"
                    )
                )

        connection.execute(
            text(
                "UPDATE payroll_incidents "
                "SET is_active = TRUE "
                "WHERE is_active IS NULL"
            )
        )


def ensure_no_hard_delete_protection():
    """Impide eliminaciones físicas en las tablas históricas de TimeCore.

    La protección se instala directamente en la base de datos para conservar
    empleados, asistencias, relojes, sucursales, incidencias y registros de
    auditoría aunque una operación intente ejecutar ``DELETE``.

    :return: No retorna ningún valor.
    :rtype: None
    """
    protected_tables = (
        "users",
        "attendance_records",
        "devices",
        "branches",
        "payroll_incidents",
        "logs",
    )
    existing_tables = set(inspect(engine).get_table_names())
    available_tables = [
        table_name
        for table_name in protected_tables
        if table_name in existing_tables
    ]

    if not available_tables:
        return

    dialect_name = engine.dialect.name

    with engine.begin() as connection:
        if dialect_name == "postgresql":
            connection.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION timecore_prevent_hard_delete()
                    RETURNS trigger
                    LANGUAGE plpgsql
                    AS $$
                    BEGIN
                        RAISE EXCEPTION
                            'TimeCore protege el historial: no se permite eliminación física en la tabla %',
                            TG_TABLE_NAME;
                        RETURN NULL;
                    END;
                    $$;
                    """
                )
            )

            for table_name in available_tables:
                trigger_name = f"trg_timecore_no_delete_{table_name}"
                truncate_trigger_name = f"trg_timecore_no_truncate_{table_name}"
                connection.execute(
                    text(
                        f'DROP TRIGGER IF EXISTS "{trigger_name}" '
                        f'ON "{table_name}"'
                    )
                )
                connection.execute(
                    text(
                        f'CREATE TRIGGER "{trigger_name}" '
                        f'BEFORE DELETE ON "{table_name}" '
                        "FOR EACH ROW "
                        "EXECUTE FUNCTION timecore_prevent_hard_delete()"
                    )
                )
                connection.execute(
                    text(
                        f'DROP TRIGGER IF EXISTS "{truncate_trigger_name}" '
                        f'ON "{table_name}"'
                    )
                )
                connection.execute(
                    text(
                        f'CREATE TRIGGER "{truncate_trigger_name}" '
                        f'BEFORE TRUNCATE ON "{table_name}" '
                        "FOR EACH STATEMENT "
                        "EXECUTE FUNCTION timecore_prevent_hard_delete()"
                    )
                )

        elif dialect_name == "sqlite":
            for table_name in available_tables:
                trigger_name = f"trg_timecore_no_delete_{table_name}"
                connection.execute(
                    text(
                        f'DROP TRIGGER IF EXISTS "{trigger_name}"'
                    )
                )
                connection.execute(
                    text(
                        f'CREATE TRIGGER "{trigger_name}" '
                        f'BEFORE DELETE ON "{table_name}" '
                        "BEGIN "
                        "SELECT RAISE(ABORT, "
                        "'TimeCore protege el historial: no se permite DELETE físico'); "
                        "END"
                    )
                )


def ensure_performance_indexes():
    """Crea índices para consultas frecuentes sin duplicarlos.

    :return: No retorna ningún valor.
    :rtype: None
    """
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_users_branch_status ON users (branch_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_users_name_lower ON users (LOWER(name))",
        "CREATE INDEX IF NOT EXISTS idx_attendance_branch_timestamp ON attendance_records (branch_id, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_attendance_user_timestamp ON attendance_records (user_id, timestamp DESC)",
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))