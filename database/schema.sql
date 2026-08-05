-- =========================================================
-- Esquema de referencia: Sistema de Facturación y Cobros
-- (Alembic gestiona las migraciones reales; este archivo sirve
--  como documentación y para inicializar rápido en Docker)
-- =========================================================

CREATE TYPE rol_usuario AS ENUM ('admin', 'cajero', 'cobrador');
CREATE TYPE estado_factura AS ENUM ('pendiente', 'parcial', 'pagada', 'anulada', 'vencida', 'reenganchada');
CREATE TYPE estado_mora AS ENUM ('al_dia', 'preventiva', 'administrativa', 'extrajudicial');
CREATE TYPE metodo_pago AS ENUM ('efectivo', 'transferencia', 'tarjeta', 'cheque', 'otro');
CREATE TYPE tipo_pago AS ENUM ('abono', 'total');

-- ---------------------------------------------------------
-- Usuarios (autenticación y roles)
-- ---------------------------------------------------------
CREATE TABLE usuarios (
    id              SERIAL PRIMARY KEY,
    nombre_completo VARCHAR(150) NOT NULL,
    email           VARCHAR(150) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    rol             rol_usuario NOT NULL DEFAULT 'cajero',
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------
-- Clientes (datos fiscales, contacto y crédito)
-- ---------------------------------------------------------
CREATE TABLE clientes (
    id                SERIAL PRIMARY KEY,
    tipo_documento    VARCHAR(20) NOT NULL DEFAULT 'CEDULA',
    numero_documento  VARCHAR(50) UNIQUE NOT NULL,
    razon_social      VARCHAR(200) NOT NULL,
    nombre_comercial  VARCHAR(200),
    email             VARCHAR(150),
    telefono          VARCHAR(30),
    direccion         TEXT,
    limite_credito    NUMERIC(14,2) NOT NULL DEFAULT 0,
    dias_credito      INTEGER NOT NULL DEFAULT 30,
    activo            BOOLEAN NOT NULL DEFAULT TRUE,
    notas             TEXT,
    creado_en         TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en    TIMESTAMPTZ
);

CREATE INDEX idx_clientes_documento ON clientes (numero_documento);

-- ---------------------------------------------------------
-- Facturas
-- ---------------------------------------------------------
CREATE TABLE facturas (
    id                 SERIAL PRIMARY KEY,
    numero_factura     VARCHAR(30) UNIQUE NOT NULL,
    cliente_id         INTEGER NOT NULL REFERENCES clientes(id),
    factura_origen_id  INTEGER REFERENCES facturas(id),  -- si nació de un reenganche
    fecha_emision      DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_vencimiento  DATE NOT NULL,
    frecuencia_pago    VARCHAR(20) NOT NULL DEFAULT 'mensual',  -- diario | quincenal | mensual

    subtotal           NUMERIC(14,2) NOT NULL DEFAULT 0,
    impuestos          NUMERIC(14,2) NOT NULL DEFAULT 0,
    descuento          NUMERIC(14,2) NOT NULL DEFAULT 0,
    total              NUMERIC(14,2) NOT NULL DEFAULT 0,

    saldo_capital      NUMERIC(14,2) NOT NULL DEFAULT 0,
    interes_acumulado  NUMERIC(14,2) NOT NULL DEFAULT 0,
    recargo_mora       NUMERIC(14,2) NOT NULL DEFAULT 0,

    estado             estado_factura NOT NULL DEFAULT 'pendiente',
    estado_mora        estado_mora NOT NULL DEFAULT 'al_dia',
    dias_atraso        INTEGER NOT NULL DEFAULT 0,

    notas              TEXT,
    creado_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en     TIMESTAMPTZ
);

CREATE INDEX idx_facturas_cliente ON facturas (cliente_id);
CREATE INDEX idx_facturas_estado ON facturas (estado);
CREATE INDEX idx_facturas_estado_mora ON facturas (estado_mora);
CREATE INDEX idx_facturas_origen ON facturas (factura_origen_id);

-- ---------------------------------------------------------
-- Ítems de factura (desglose de conceptos)
-- ---------------------------------------------------------
CREATE TABLE factura_items (
    id                    SERIAL PRIMARY KEY,
    factura_id            INTEGER NOT NULL REFERENCES facturas(id) ON DELETE CASCADE,
    descripcion           VARCHAR(300) NOT NULL,
    cantidad              NUMERIC(12,2) NOT NULL DEFAULT 1,
    precio_unitario       NUMERIC(14,2) NOT NULL DEFAULT 0,
    porcentaje_impuesto   NUMERIC(5,2) NOT NULL DEFAULT 0,
    subtotal_linea        NUMERIC(14,2) NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------
-- Cuotas (plan de pagos de una factura)
-- ---------------------------------------------------------
CREATE TABLE cuotas (
    id                 SERIAL PRIMARY KEY,
    factura_id         INTEGER NOT NULL REFERENCES facturas(id) ON DELETE CASCADE,
    numero_cuota       INTEGER NOT NULL,
    fecha_vencimiento  DATE NOT NULL,
    monto_capital      NUMERIC(14,2) NOT NULL DEFAULT 0,
    monto_interes      NUMERIC(14,2) NOT NULL DEFAULT 0,
    monto_recargo      NUMERIC(14,2) NOT NULL DEFAULT 0,
    monto_pagado       NUMERIC(14,2) NOT NULL DEFAULT 0,
    estado             estado_factura NOT NULL DEFAULT 'pendiente'
);

CREATE INDEX idx_cuotas_factura ON cuotas (factura_id);

-- ---------------------------------------------------------
-- Pagos (abonos y liquidaciones)
-- ---------------------------------------------------------
CREATE TABLE pagos (
    id              SERIAL PRIMARY KEY,
    factura_id      INTEGER NOT NULL REFERENCES facturas(id),
    cuota_id        INTEGER REFERENCES cuotas(id),
    usuario_id      INTEGER REFERENCES usuarios(id),

    tipo_pago       tipo_pago NOT NULL DEFAULT 'abono',
    metodo_pago     metodo_pago NOT NULL DEFAULT 'efectivo',

    monto_capital   NUMERIC(14,2) NOT NULL DEFAULT 0,
    monto_interes   NUMERIC(14,2) NOT NULL DEFAULT 0,
    monto_recargo   NUMERIC(14,2) NOT NULL DEFAULT 0,
    monto_total     NUMERIC(14,2) NOT NULL DEFAULT 0,
    vuelto          NUMERIC(14,2) NOT NULL DEFAULT 0,

    referencia      VARCHAR(100),
    notas           TEXT,
    fecha_pago      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pagos_factura ON pagos (factura_id);

-- ---------------------------------------------------------
-- Recibos de caja (generados automáticamente por cada pago)
-- ---------------------------------------------------------
CREATE TABLE recibos (
    id             SERIAL PRIMARY KEY,
    numero_recibo  VARCHAR(30) UNIQUE NOT NULL,
    pago_id        INTEGER UNIQUE NOT NULL REFERENCES pagos(id),
    monto_total    NUMERIC(14,2) NOT NULL,
    generado_en    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------
-- Usuario administrador inicial (password: admin123 -- CAMBIAR)
-- Hash bcrypt generado para "admin123"; regenerar en producción.
-- ---------------------------------------------------------
-- INSERT INTO usuarios (nombre_completo, email, password_hash, rol)
-- VALUES ('Administrador', 'admin@empresa.com', '<bcrypt_hash_aqui>', 'admin');
