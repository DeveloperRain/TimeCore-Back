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
    """Modelo de solicitud para el inicio de sesión."""
    email: str
    password: str = Field(..., min_length=6)


class RegisterRequest(BaseModel):
    """Modelo de solicitud para el registro de un nuevo usuario."""
    full_name: str = Field(..., min_length=3, max_length=120)
    email: str
    password: str = Field(..., min_length=6)
    role: Optional[str] = "admin"


def normalize_email(email: str) -> str:
    """
    Normaliza el correo electrónico eliminando espacios y convirtiéndolo a minúsculas.

    :param email: Correo electrónico a normalizar.
    :type email: str
    :return: Correo electrónico normalizado.
    :rtype: str
    """
    return email.strip().lower()


def normalize_role(role: Optional[str]) -> str:
    """
    Normaliza y valida el rol de usuario asignando un valor predeterminado si no es válido.

    :param role: Rol del usuario a normalizar.
    :type role: typing.Optional[str]
    :return: Rol normalizado y permitido.
    :rtype: str
    """
    allowed_roles = {"admin", "soporte", "consulta"}
    clean_role = (role or "admin").strip().lower()
    return clean_role if clean_role in allowed_roles else "admin"


def validate_email(email: str):
    """
    Valida que el correo electrónico tenga una estructura básica correcta.

    :param email: Correo electrónico a validar.
    :type email: str
    :return: No retorna ningún valor.
    :rtype: None
    :raises fastapi.HTTPException: Si el correo no contiene '@' o '.'.
    """
    if "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Correo inválido")


def hash_password(password: str) -> str:
    """
    Genera el hash seguro de una contraseña en texto plano.

    :param password: Contraseña en texto plano.
    :type password: str
    :return: Hash cifrado de la contraseña.
    :rtype: str
    """
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verifica si una contraseña en texto plano coincide con su respectivo hash.

    :param password: Contraseña en texto plano a verificar.
    :type password: str
    :param password_hash: Hash cifrado contra el cual se comparará.
    :type password_hash: str
    :return: Verdadero si coinciden, falso en caso contrario.
    :rtype: bool
    """
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def create_access_token(data: dict) -> str:
    """
    Crea un token de acceso JWT codificado con una fecha de expiración.

    :param data: Datos o reclamaciones (claims) a incluir dentro del token.
    :type data: dict
    :return: El token JWT generado en formato de cadena.
    :rtype: str
    """
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload.update({"exp": expire})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def user_to_dict(user: SystemUser) -> dict:
    """
    Convierte la instancia de un usuario del sistema en un diccionario serializable.

    :param user: Instancia del modelo SystemUser.
    :type user: app.models.system_user.SystemUser
    :return: Diccionario con los datos principales del usuario.
    :rtype: dict
    """
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
    }


def ensure_default_admin():
    """
    Asegura la existencia de un usuario administrador por defecto en el sistema.

    :return: No retorna ningún valor.
    :rtype: None
    """
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
    """
    Autentica a un usuario del sistema mediante sus credenciales y genera un token de acceso.

    :param payload: Datos de inicio de sesión que incluyen correo y contraseña.
    :type payload: LoginRequest
    :return: Respuesta estructurada que contiene el token de acceso y los datos del usuario.
    :rtype: dict
    :raises fastapi.HTTPException: Si las credenciales son incorrectas o el usuario está inactivo.
    """
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
    """
    Registra un nuevo usuario en el sistema con un rol y contraseña cifrada.

    :param payload: Datos necesarios para el registro del usuario.
    :type payload: RegisterRequest
    :return: Respuesta estructurada con los datos del usuario recién creado.
    :rtype: dict
    :raises fastapi.HTTPException: Si el correo ya se encuentra registrado.
    """
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
    """
    Obtiene la información del usuario autenticado actualmente a partir de su token Bearer.

    :param credentials: Las credenciales de autorización HTTP extraídas de la petición.
    :type credentials: fastapi.security.HTTPAuthorizationCredentials
    :return: Respuesta estructurada con la información del usuario autenticado.
    :rtype: dict
    :raises fastapi.HTTPException: Si el token es inválido, ha expirado o el usuario no existe/está inactivo.
    """
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