#!/usr/bin/env python3
"""Respaldo automático de la base de datos Postgres de facturacion-sistema.

Hace 4 cosas en orden, y se detiene (código de salida != 0) si alguna falla
— así, si se corre desde GitHub Actions o un cron de Railway, la corrida
queda marcada como fallida en vez de fallar en silencio:

  1. pg_dump de la base de datos completa a un archivo .sql
  2. Comprime ese .sql a un .zip (cifrado con contraseña si se define ZIP_PASSWORD)
  3. Envía el .zip por correo a EMAIL_TO como adjunto
  4. Borra respaldos locales con más de RETENTION_DIAS días

Variables de entorno REQUERIDAS:
  DATABASE_URL        Cadena de conexión de Postgres (la misma que usa el backend)
  EMAIL_FROM           Cuenta de Gmail que ENVÍA el respaldo (necesita su propia
                        contraseña de aplicación, ver instrucciones abajo)
  EMAIL_APP_PASSWORD   Contraseña de aplicación de esa cuenta — NO la contraseña normal

Variables de entorno OPCIONALES:
  EMAIL_TO             A quién llega el respaldo (default: jose.colorvision@gmail.com)
  RETENTION_DIAS       Cuántos días de respaldo conservar localmente (default: 7)
  ZIP_PASSWORD         Si se define, el .zip queda cifrado con AES-256 usando esta
                        contraseña. MUY RECOMENDADO: el respaldo contiene datos
                        financieros y personales de clientes (cédulas, montos,
                        teléfonos), y un correo puede ser interceptado o el buzón
                        comprometido — cifrarlo es la diferencia entre una filtración
                        de datos real y un archivo inútil para quien no tenga la clave.
  BACKUP_DIR           Carpeta local de trabajo (default: ./backups)

Requiere el binario `pg_dump` instalado en el sistema donde corre este script
(no en el servidor de la base de datos — en la máquina/contenedor/runner que
EJECUTA este script). Ver instrucciones de instalación al final de este archivo.
"""
import glob
import os
import smtplib
import ssl
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from email.message import EmailMessage

LIMITE_GMAIL_MB = 24  # Gmail corta adjuntos alrededor de 25MB; se deja margen


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def fallar(msg: str) -> None:
    log(f"ERROR: {msg}")
    sys.exit(1)


def obtener_config() -> dict:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        fallar("Falta la variable de entorno DATABASE_URL")

    email_from = os.environ.get("EMAIL_FROM")
    email_password = os.environ.get("EMAIL_APP_PASSWORD")
    if not email_from or not email_password:
        fallar("Faltan las variables de entorno EMAIL_FROM y/o EMAIL_APP_PASSWORD")

    return {
        "database_url": database_url,
        "email_from": email_from,
        "email_password": email_password,
        "email_to": os.environ.get("EMAIL_TO", "jose.colorvision@gmail.com"),
        "retencion_dias": int(os.environ.get("RETENTION_DIAS", "7")),
        "zip_password": os.environ.get("ZIP_PASSWORD") or None,
        "backup_dir": os.environ.get("BACKUP_DIR", "./backups"),
    }


def hacer_dump(database_url: str, destino_sql: str) -> None:
    log("Exportando base de datos con pg_dump...")
    resultado = subprocess.run(
        ["pg_dump", database_url, "-f", destino_sql, "--no-owner", "--no-privileges"],
        capture_output=True, text=True,
    )
    if resultado.returncode != 0:
        fallar(f"pg_dump falló: {resultado.stderr.strip()}")
    if not os.path.exists(destino_sql) or os.path.getsize(destino_sql) == 0:
        fallar("pg_dump terminó sin error pero el archivo de salida está vacío o no existe")
    tam_kb = os.path.getsize(destino_sql) / 1024
    log(f"Dump generado: {destino_sql} ({tam_kb:.1f} KB)")


def comprimir(origen_sql: str, destino_zip: str, password: str | None) -> None:
    log("Comprimiendo respaldo..." + (" (cifrado con contraseña)" if password else ""))
    if password:
        try:
            import pyzipper
        except ImportError:
            fallar(
                "ZIP_PASSWORD está definida pero falta el paquete 'pyzipper' "
                "(instálalo con: pip install pyzipper --break-system-packages)"
            )
        with pyzipper.AESZipFile(
            destino_zip, "w",
            compression=pyzipper.ZIP_LZMA,
            encryption=pyzipper.WZ_AES,
        ) as zf:
            zf.setpassword(password.encode())
            zf.write(origen_sql, arcname=os.path.basename(origen_sql))
    else:
        with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.write(origen_sql, arcname=os.path.basename(origen_sql))

    tam_kb = os.path.getsize(destino_zip) / 1024
    log(f"Comprimido: {destino_zip} ({tam_kb:.1f} KB)")
    os.remove(origen_sql)  # no dejar el .sql sin comprimir tirado en disco


def enviar_correo(config: dict, ruta_zip: str) -> None:
    tam_mb = os.path.getsize(ruta_zip) / (1024 * 1024)
    if tam_mb > LIMITE_GMAIL_MB:
        fallar(
            f"El respaldo pesa {tam_mb:.1f}MB, supera el límite práctico de adjuntos "
            f"de Gmail (~{LIMITE_GMAIL_MB}MB). El archivo se conserva en {config['backup_dir']}, "
            f"pero necesitas subirlo a Google Drive manualmente o cambiar de estrategia "
            f"(por ejemplo, respaldar solo tablas específicas) — no se intenta el envío."
        )

    log(f"Enviando respaldo por correo a {config['email_to']}...")
    msg = EmailMessage()
    msg["Subject"] = f"Respaldo facturacion-sistema — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    msg["From"] = config["email_from"]
    msg["To"] = config["email_to"]
    cuerpo = "Respaldo automático de la base de datos adjunto.\n\n"
    if config["zip_password"]:
        cuerpo += "Este archivo está cifrado con contraseña (la misma ZIP_PASSWORD configurada).\n\n"
    cuerpo += "Generado automáticamente — no responder este correo."
    msg.set_content(cuerpo)

    with open(ruta_zip, "rb") as f:
        msg.add_attachment(
            f.read(), maintype="application", subtype="zip",
            filename=os.path.basename(ruta_zip),
        )

    contexto = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=contexto) as servidor:
        servidor.login(config["email_from"], config["email_password"])
        servidor.send_message(msg)
    log("Correo enviado correctamente.")


def rotar_respaldos(carpeta: str, dias_retencion: int) -> None:
    log(f"Revisando respaldos con más de {dias_retencion} día(s) en {carpeta}...")
    limite = time.time() - dias_retencion * 86400
    borrados = 0
    for ruta in glob.glob(os.path.join(carpeta, "backup_*.zip")):
        if os.path.getmtime(ruta) < limite:
            os.remove(ruta)
            borrados += 1
            log(f"  Borrado (más viejo que {dias_retencion} días): {ruta}")
    log(f"Rotación completa: {borrados} respaldo(s) viejo(s) eliminado(s).")


def main() -> None:
    config = obtener_config()
    os.makedirs(config["backup_dir"], exist_ok=True)

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_sql = os.path.join(config["backup_dir"], f"backup_{marca}.sql")
    ruta_zip = os.path.join(config["backup_dir"], f"backup_{marca}.zip")

    hacer_dump(config["database_url"], ruta_sql)
    comprimir(ruta_sql, ruta_zip, password=config["zip_password"])
    enviar_correo(config, ruta_zip)
    rotar_respaldos(config["backup_dir"], config["retencion_dias"])

    log("Respaldo completado exitosamente.")


if __name__ == "__main__":
    main()
