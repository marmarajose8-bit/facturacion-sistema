from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, decode_token
from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioCreate, UsuarioOut, LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


@router.post("/registro", response_model=UsuarioOut, status_code=201)
def registrar_usuario(payload: UsuarioCreate, db: Session = Depends(get_db)):
    existente = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if existente:
        raise HTTPException(400, "Ya existe un usuario con ese email")

    usuario = Usuario(
        nombre_completo=payload.nombre_completo,
        email=payload.email,
        password_hash=hash_password(payload.password),
        rol=payload.rol,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if not usuario or not verify_password(payload.password, usuario.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")
    if not usuario.activo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario inactivo")

    token = create_access_token({"sub": str(usuario.id), "rol": usuario.rol})
    return TokenResponse(access_token=token, usuario=usuario)


def obtener_usuario_actual(payload: dict = Depends(decode_token), db: Session = Depends(get_db)) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.id == int(payload["sub"])).first()
    if not usuario:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado")
    return usuario
