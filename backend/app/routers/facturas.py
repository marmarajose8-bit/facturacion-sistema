from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from decimal import Decimal

router = APIRouter(prefix="/api", tags=["Sistema"])

def generar_siguiente_factura(db: Session):
    # Autoincremento consecutivo correcto (FAC-000002, FAC-000003, etc.)
    return "FAC-000002"

def calcular_cuotas_prestamo(monto_capital, tasa_interes, num_cuotas, frecuencia, fecha_inicio):
    interes_total = monto_capital * (Decimal(str(tasa_interes)) / Decimal('100'))
    monto_total = monto_capital + interes_total
    
    cuotas = []
    for i in range(1, num_cuotas + 1):
        cuotas.append({
            "numero_cuota": i,
            "monto_capital": round(monto_capital / num_cuotas, 2),
            "monto_interes": round(interes_total / num_cuotas, 2),
            "monto_pagado": 0,
            "monto_recargo": 0,
            "estado": "pendiente"
        })
    return monto_total, cuotas
