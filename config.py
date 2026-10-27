import os
from dotenv import load_dotenv

from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv()

# ── Plataforma ATIS Salud ──────────────────────────────────────────
ATIS_URL = os.getenv('ATIS_URL')
ATIS_USERNAME = os.getenv('ATIS_USERNAME')
ATIS_PASSWORD = os.getenv('ATIS_PASSWORD')

# ── Plataforma HISESA ──────────────────────────────────────────
HISESA_URL = os.getenv('HISESA_URL')
HISESA_USERNAME1 = os.getenv('HISESA_USERNAME1')
HISESA_USERNAME2 = os.getenv('HISESA_USERNAME2')
HISESA_PASSWORD1 = os.getenv('HISESA_PASSWORD1')
HISESA_PASSWORD2 = os.getenv('HISESA_PASSWORD2')

# ── Plataforma Zona Médica IPS ───────────────────────────────────────
ZONAMEDICA_URL=os.getenv('ZONAMEDICA_URL')
ZONAMEDICA_USERNAME = os.getenv('ZONAMEDICA_USERNAME')
ZONAMEDICA_PASSWORD = os.getenv('ZONAMEDICA_PASSWORD')

# ── Google Sheets ───────────────────────────────────────────────────
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
SHEET_NAME = os.getenv('SHEET_NAME')
LOGS_SHEET_NAME = os.getenv('LOGS_SHEET_NAME')
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE')

# ── Google Drive ────────────────────────────────────────────────────
DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')

# ── Reglas de negocio ───────────────────────────────────────────────
TOLERANCIA_DIAS = int(os.getenv('TOLERANCIA_DIAS'))
USUARIO_CARGA = os.getenv('USUARIO_CARGA')
ESTADO_ORIGEN = 'Confirmado'
ESTADO_DESTINO = 'Cargado'

# ── Configuración de ejecución ───────────────────────────────────────
HEADLESS = os.getenv('HEADLESS', 'false').lower() == 'true'
TIMEOUT_MS = int(os.getenv('TIMEOUT_MS', 30000))
CARPETA_TEMP = os.getenv('CARPETA_TEMP', 'temp_descargas')

TOKEN_PROCESO_PYTHON = os.getenv('TOKEN_PROCESO_PYTHON')
URL_WEBAPP = os.getenv('URL_WEBAPP')
TZ_NEGOCIO = os.getenv('TZ_NEGOCIO', 'America/Bogota')

def ahora():
    """Hora de Colombia (Render corre en UTC)."""
    return datetime.now(ZoneInfo(TZ_NEGOCIO))

# ── Columnas de la hoja Examenes (índices base 0) ──────
COL_ID_EXAMEN = int(os.getenv('COL_ID_EXAMEN'))
COL_CEDULA = int(os.getenv('COL_CEDULA'))
COL_FECHA_EXAMEN = int(os.getenv('COL_FECHA_EXAMEN'))
COL_LINK_CERTIFICADO = int(os.getenv('COL_LINK_CERTIFICADO'))
COL_IPS = int(os.getenv('COL_IPS'))
COL_ESTADO = int(os.getenv('COL_ESTADO'))
COL_FECHA_CARGUE = int(os.getenv('COL_FECHA_CARGUE'))
COL_TIPO_EXAMEN = int(os.getenv('COL_TIPO_EXAMEN'))
COL_COMPONENTE = int(os.getenv('COL_COMPONENTE'))

IPS_ATIS = 'SAOCSS'

# Fila donde empiezan los datos (1 = primera fila de la hoja)
INICIO_FILA = int(os.getenv('INICIO_FILA'))

BITACORA_SHEET_NAME = os.getenv('BITACORA_SHEET_NAME', 'Bitacora')
BITACORA_ORIGEN = os.getenv('BITACORA_ORIGEN', 'AUTOMATIZACION')
BITACORA_ACCION = os.getenv('BITACORA_ACCION', 'CARGAR')

# ── Reglas de negocio (REEMPLAZA las actuales) ──────────────────────
TOLERANCIA_DIAS = int(os.getenv('TOLERANCIA_DIAS', 25))
USUARIO_CARGA = os.getenv('USUARIO_CARGA', 'AUTOMATIZACION')
ESTADOS_ORIGEN = ['Solicitado', 'Confirmado']      # reemplaza ESTADO_ORIGEN
ESTADO_DESTINO = 'Cargado'

IPS_ZONAMEDICA = 'ZONA MEDICA'
IPS_HISESA = 'HISESA'
IPS_SOPORTADAS = [IPS_ZONAMEDICA, IPS_ATIS, IPS_HISESA]

HISESA_ESPERA_MS = int(os.getenv('HISESA_ESPERA_MS', 3500))

# ── Ejecución (REEMPLAZA) ───────────────────────────────────────────
HEADLESS = os.getenv('HEADLESS', 'true').lower() == 'true'
INICIO_FILA = int(os.getenv('INICIO_FILA', 2))

def validar_config():
    """Valida que la configuración esté completa antes de correr el script."""
    errores = []

    if not ATIS_USERNAME or not ATIS_PASSWORD:
        errores.append("❌ ATIS_USERNAME o ATIS_PASSWORD no están configurados en .env")

    if not ZONAMEDICA_USERNAME or not ZONAMEDICA_PASSWORD:
        errores.append("❌ ZONAMEDICA_USERNAME o ZONAMEDICA_PASSWORD no están configurados en .env")

    if not GOOGLE_SHEET_ID:
        errores.append("❌ GOOGLE_SHEET_ID no está configurado en .env")

    if not DRIVE_FOLDER_ID:
        errores.append("❌ DRIVE_FOLDER_ID no está configurado en .env")

    if not HISESA_URL or not HISESA_USERNAME1 or not HISESA_PASSWORD1:
        errores.append("❌ Credenciales HISESA (cuenta 1) incompletas")
    
    if not HISESA_USERNAME2 or not HISESA_PASSWORD2:
        errores.append("❌ Credenciales HISESA (cuenta 2) incompletas")
    
    if not ATIS_URL or not ZONAMEDICA_URL:
        errores.append("❌ ATIS_URL o ZONAMEDICA_URL no configuradas")
    
    if not TOKEN_PROCESO_PYTHON or not URL_WEBAPP:
        errores.append("❌ TOKEN_PROCESO_PYTHON o URL_WEBAPP no configurados")
    
    if not CREDENTIALS_FILE or not os.path.exists(CREDENTIALS_FILE):
        errores.append(f"❌ Archivo de credenciales no encontrado: {CREDENTIALS_FILE}")

    if errores:
        print("\n".join(errores))
        return False
    
    return True