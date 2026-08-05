from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.cliente import Cliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate, ClienteOut

router = APIRouter(prefix="/api/clientes", tags=["Clientes"], dependencies=[Depends(decode_token)])


@router.get("", response_model=List[ClienteOut])
def listar_clientes(
    db: Session = Depends(get_db),
    q: Optional[str] = Query(None, description="Buscar por nombre o documento"),
    activo: Optional[bool] = None,
):
    query = db.query(Cliente)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Cliente.razon_social.ilike(like)) | (Cliente.numero_documento.ilike(like))
        )
    if activo is not None:
        query = query.filter(Cliente.activo == activo)
    return query.order_by(Cliente.razon_social).all()


@router.post("", response_model=ClienteOut, status_code=201)
def crear_cliente(payload: ClienteCreate, db: Session = Depends(get_db)):
    existente = db.query(Cliente).filter(Cliente.numero_documento == payload.numero_documento).first()
    if existente:
        raise HTTPException(400, "Ya existe un cliente con ese número de documento")
    cliente = Cliente(**payload.model_dump())
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.get("/{cliente_id}", response_model=ClienteOut)
def obtener_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).get(cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    return cliente


@router.put("/{cliente_id}", response_model=ClienteOut)
def actualizar_cliente(cliente_id: int, payload: ClienteUpdate, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).get(cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    for campo, valor in payload.model_dump(exclude_unset=True).items():
        setattr(cliente, campo, valor)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.delete("/{cliente_id}", status_code=204)
def desactivar_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Baja lógica: nunca se elimina físicamente un cliente con historial financiero."""
    cliente = db.query(Cliente).get(cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    cliente.activo = False
    db.commit()
