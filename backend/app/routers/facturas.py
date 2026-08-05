from decimal import Decimal

def calcular_cuotas_prestamo(monto_capital, tasa_interes, num_cuotas, frecuencia, fecha_inicio):
    interes_total = monto_capital * (Decimal(str(tasa_interes)) / Decimal('100'))
    monto_total = monto_capital + interes_total
    valor_cuota = monto_total / num_cuotas
    
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
