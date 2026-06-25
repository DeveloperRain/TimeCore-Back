from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from app.database.connection import SessionLocal
from app.models.system_user import SystemUser
from app.utils.response import success

router = APIRouter(prefix="/auth", tags=["Autenticación"])

SECRET_KEY = "timecore-secret-key-cambiala-despues"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer()


class LoginRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=6)


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=120)
    email: str
    password: str = Field(..., min_length=6)
    role: Optional[str] = "admin"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_role(role: Optional[str]) -> str:
    allowed_roles = {"admin", "soporte", "consulta"}
    clean_role = (role or "admin").strip().lower()
    return clean_role if clean_role in allowed_roles else "admin"


def validate_email(email: str):
    if "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Correo inválido")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload.update({"exp": expire})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def user_to_dict(user: SystemUser) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
    }


def ensure_default_admin():
    db = SessionLocal()

    try:
        existing = db.query(SystemUser).filter(
            SystemUser.email == "admin@timecore.com"
        ).first()

        if existing:
            return

        admin = SystemUser(
            full_name="Admin TimeCore",
            email="admin@timecore.com",
            password_hash=hash_password("Admin1234"),
            role="admin",
            is_active=True,
        )

        db.add(admin)
        db.commit()

    finally:
        db.close()


@router.post("/login", summary="Iniciar sesión")
def login(payload: LoginRequest):
    ensure_default_admin()

    db = SessionLocal()

    try:
        email = normalize_email(payload.email)
        validate_email(email)

        user = db.query(SystemUser).filter(SystemUser.email == email).first()

        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Usuario inactivo")

        token = create_access_token(
            {
                "sub": user.email,
                "user_id": user.id,
                "role": user.role,
            }
        )

        return success(
            data={
                "access_token": token,
                "token_type": "bearer",
                "user": user_to_dict(user),
            },
            message="Inicio de sesión correcto",
        )

    finally:
        db.close()


@router.post("/register", summary="Crear usuario del sistema")
def register(payload: RegisterRequest):
    ensure_default_admin()

    db = SessionLocal()

    try:
        email = normalize_email(payload.email)
        validate_email(email)

        existing = db.query(SystemUser).filter(SystemUser.email == email).first()

        if existing:
            raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo")

        user = SystemUser(
            full_name=payload.full_name.strip(),
            email=email,
            password_hash=hash_password(payload.password),
            role=normalize_role(payload.role),
            is_active=True,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return success(
            data=user_to_dict(user),
            message="Usuario creado correctamente",
        )

    finally:
        db.close()


@router.get("/me", summary="Obtener usuario autenticado")
def me(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")

        if not email:
            raise HTTPException(status_code=401, detail="Token inválido")

    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    db = SessionLocal()

    try:
        user = db.query(SystemUser).filter(SystemUser.email == email).first()

        if not user:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Usuario inactivo")

        return success(
            data=user_to_dict(user),
            message="Token válido",
        )
  
    finally:
        db.close()