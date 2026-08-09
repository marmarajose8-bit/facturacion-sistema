# Referencia rápida de la API

Documentación interactiva completa (Swagger) disponible en `/docs` una vez
levantado el backend, y `/redoc` para la versión alternativa.

## Autenticación
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/auth/registro` | Crea un usuario (admin/cajero/cobrador) |
| POST | `/api/auth/login` | Devuelve JWT + datos del usuario |

Todas las demás rutas requieren header `Authorization: Bearer <token>`.

## Clientes
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/clientes?q=&activo=` | Lista/busca clientes |
| POST | `/api/clientes` | Crea cliente |
| GET | `/api/clientes/{id}` | Detalle |
| PUT | `/api/clientes/{id}` | Actualiza |
| DELETE | `/api/clientes/{id}` | Baja lógica (no elimina historial) |

## Facturación
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/facturas?cliente_id=&estado=&estado_mora=` | Lista facturas (recalcula mora al vuelo) |
| POST | `/api/facturas` | Crea factura con ítems y plan de cuotas opcional |
| GET | `/api/facturas/{id}` | Detalle con ítems y cuotas |
| POST | `/api/facturas/{id}/anular` | Anula una factura no pagada |

## Pagos
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/pagos?factura_id=` | Historial de pagos |
| POST | `/api/pagos` | Registra abono/pago total; genera recibo automáticamente. Orden de aplicación: recargo → interés → capital |
| GET | `/api/pagos/{id}/recibo` | Recibo asociado a un pago |

## Cartera y mora
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/cartera/resumen` | Totales agrupados por clasificación |
| GET | `/api/cartera/vencidas?estado_mora=` | Listado detallado de cuentas vencidas |

## Dashboard
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/dashboard/totales` | Total facturado / cobrado / pendiente |
| GET | `/api/dashboard/facturado-mensual` | Serie mensual para gráficos |

## Parámetros de negocio configurables (`.env`)
- `TASA_INTERES_MORA_MENSUAL`: tasa de interés corriente mensual aplicada al saldo en mora.
- `DIAS_MORA_PREVENTIVA` / `DIAS_MORA_ADMINISTRATIVA` / `DIAS_MORA_EXTRAJUDICIAL`: umbrales de días de atraso que determinan la clasificación de cartera y el recargo escalonado.
