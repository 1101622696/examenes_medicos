import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _int(nombre, defecto=None):
    """Lee un entero del .env; None (o el defecto) si no está."""
    valor = os.getenv(nombre)
    if valor is None or str(valor).strip() == '':
        return defecto
    return int(valor)


# ── Plataforma ATIS Salud (SAOCSS) ──────────────────────────────────
ATIS_URL = os.getenv('ATIS_URL')
ATIS_USERNAME = os.getenv('ATIS_USERNAME')
ATIS_PASSWORD = os.getenv('ATIS_PASSWORD')

# ── Plataforma HISESA (dos cuentas) ─────────────────────────────────
HISESA_URL = os.getenv('HISESA_URL')
HISESA_USERNAME1 = os.getenv('HISESA_USERNAME1')
HISESA_PASSWORD1 = os.getenv('HISESA_PASSWORD1')
HISESA_USERNAME2 = os.getenv('HISESA_USERNAME2')
HISESA_PASSWORD2 = os.getenv('HISESA_PASSWORD2')

# ── Plataforma SSO ──────────────────────────────────────────────────
SSO_URL = os.getenv('SSO_URL')
SSO_USERNAME = os.getenv('SSO_USERNAME')
SSO_PASSWORD = os.getenv('SSO_PASSWORD')

# ── Plataforma Zona Médica IPS ──────────────────────────────────────
ZONAMEDICA_URL = os.getenv('ZONAMEDICA_URL')
ZONAMEDICA_USERNAME = os.getenv('ZONAMEDICA_USERNAME')
ZONAMEDICA_PASSWORD = os.getenv('ZONAMEDICA_PASSWORD')

# ── Plataforma ICSA (psicofísico Bucaramanga, una cuenta) ───────────
ICSA_URL = os.getenv('ICSA_URL', 'https://icsa.com.co/mindefensa.html')
ICSA_USERNAME = os.getenv('ICSA_USERNAME')
ICSA_PASSWORD = os.getenv('ICSA_PASSWORD')

# ── Plataforma SIMETRIC (dos cuentas: 1 = psicofísico, 2 = psicosensométrico) ─
SIMETRIC_URL = os.getenv('SIMETRIC_URL', 'http://190.60.193.163/sga2/index.php')
SIMETRIC_USERNAME1 = os.getenv('SIMETRIC_USERNAME1')
SIMETRIC_PASSWORD1 = os.getenv('SIMETRIC_PASSWORD1')
SIMETRIC_USERNAME2 = os.getenv('SIMETRIC_USERNAME2')
SIMETRIC_PASSWORD2 = os.getenv('SIMETRIC_PASSWORD2')

# ── Google Sheets ───────────────────────────────────────────────────
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
SHEET_NAME = os.getenv('SHEET_NAME')
LOGS_SHEET_NAME = os.getenv('LOGS_SHEET_NAME')
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE')

BITACORA_SHEET_NAME = os.getenv('BITACORA_SHEET_NAME', 'Bitacora')
BITACORA_ORIGEN = os.getenv('BITACORA_ORIGEN', 'AUTOMATIZACION')
BITACORA_ACCION = os.getenv('BITACORA_ACCION', 'CARGAR')

# ── Google Drive ────────────────────────────────────────────────────
DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')

# ── Columnas de la hoja Examenes (índices base 0) ───────────────────
COL_ID_EXAMEN = _int('COL_ID_EXAMEN')
COL_CEDULA = _int('COL_CEDULA')
COL_FECHA_EXAMEN = _int('COL_FECHA_EXAMEN')
COL_LINK_CERTIFICADO = _int('COL_LINK_CERTIFICADO')
COL_IPS = _int('COL_IPS')
COL_ESTADO = _int('COL_ESTADO')
COL_FECHA_CARGUE = _int('COL_FECHA_CARGUE')
COL_TIPO_EXAMEN = _int('COL_TIPO_EXAMEN')
COL_COMPONENTE = _int('COL_COMPONENTE')
COL_ESPECIALIDAD = _int('COL_ESPECIALIDAD')          # nueva (U = 20)

# Fila donde empiezan los datos (1 = primera fila de la hoja)
INICIO_FILA = _int('INICIO_FILA', 2)

# ── Reglas de negocio ───────────────────────────────────────────────
TOLERANCIA_DIAS = _int('TOLERANCIA_DIAS', 25)       # certificado vs. fecha del sheet
DIAS_VENTANA_CARGUE = _int('DIAS_VENTANA_CARGUE', 20)
USUARIO_CARGA = os.getenv('USUARIO_CARGA', 'AUTOMATIZACION')
ESTADOS_ORIGEN = ['Solicitado', 'Confirmado']
ESTADO_ORIGEN = 'Confirmado'      # compatibilidad con código anterior
ESTADO_DESTINO = 'Cargado'

# ── IPS automatizadas (como aparecen en la columna IPS) ─────────────
IPS_ATIS = 'SAOCSS'
IPS_ZONAMEDICA = 'ZONA MEDICA'
IPS_HISESA = 'HISESA'
IPS_SSO = 'SSO - CRC SERVICIOS DE SALUD OCUPACIONAL S.A.S'
IPS_ICSA = 'ICSA'
IPS_SIMETRIC = 'SIMETRIC'

IPS_PSICO = [IPS_ICSA, IPS_SIMETRIC]          # solo se buscan filas psico
IPS_SOPORTADAS = [IPS_ZONAMEDICA, IPS_ATIS, IPS_HISESA, IPS_SSO] + IPS_PSICO

ESPECIALIDADES_PSICO = ['PSICOFISICO', 'PSICOSENSOMETRICO']   # normalizadas

# ── Ejecución ───────────────────────────────────────────────────────
HEADLESS = os.getenv('HEADLESS', 'true').lower() == 'true'
TIMEOUT_MS = _int('TIMEOUT_MS', 30000)
CARPETA_TEMP = os.getenv('CARPETA_TEMP', 'temp_descargas')

HISESA_ESPERA_MS = _int('HISESA_ESPERA_MS', 3500)
SSO_ESPERA_MS = _int('SSO_ESPERA_MS', 3500)
ICSA_ESPERA_MS = _int('ICSA_ESPERA_MS', 8000)          # máximo a esperar resultados
SIMETRIC_ESPERA_MS = _int('SIMETRIC_ESPERA_MS', 8000)

TOKEN_PROCESO_PYTHON = os.getenv('TOKEN_PROCESO_PYTHON')
URL_WEBAPP = os.getenv('URL_WEBAPP')
TZ_NEGOCIO = os.getenv('TZ_NEGOCIO', 'America/Bogota')


def ahora():
    """Hora de Colombia (Render corre en UTC)."""
    return datetime.now(ZoneInfo(TZ_NEGOCIO))


# ── Plataformas habilitadas ─────────────────────────────────────────
def _faltantes_plataforma(ips):
    """Lista de variables que le faltan a una plataforma ([] = habilitada)."""
    requeridas = {
        IPS_ATIS: ['ATIS_URL', 'ATIS_USERNAME', 'ATIS_PASSWORD'],
        IPS_ZONAMEDICA: ['ZONAMEDICA_URL', 'ZONAMEDICA_USERNAME', 'ZONAMEDICA_PASSWORD'],
        IPS_HISESA: ['HISESA_URL', 'HISESA_USERNAME1', 'HISESA_PASSWORD1'],
        IPS_SSO: ['SSO_URL', 'SSO_USERNAME', 'SSO_PASSWORD'],
        IPS_ICSA: ['ICSA_URL', 'ICSA_USERNAME', 'ICSA_PASSWORD', 'COL_ESPECIALIDAD'],
        IPS_SIMETRIC: ['SIMETRIC_URL', 'SIMETRIC_USERNAME1', 'SIMETRIC_PASSWORD1', 'COL_ESPECIALIDAD'],
    }.get(ips, [])
    return [v for v in requeridas if globals().get(v) in (None, '')]


def plataforma_habilitada(ips):
    return not _faltantes_plataforma(ips)


def validar_config():
    """Valida lo común. Una plataforma sin credenciales solo se desactiva (no frena las demás)."""
    errores = []

    if not GOOGLE_SHEET_ID or not SHEET_NAME:
        errores.append("❌ GOOGLE_SHEET_ID o SHEET_NAME no configurados")
    if not DRIVE_FOLDER_ID:
        errores.append("❌ DRIVE_FOLDER_ID no configurado")
    if not TOKEN_PROCESO_PYTHON or not URL_WEBAPP:
        errores.append("❌ TOKEN_PROCESO_PYTHON o URL_WEBAPP no configurados")
    if not CREDENTIALS_FILE or not os.path.exists(CREDENTIALS_FILE):
        errores.append(f"❌ Archivo de credenciales no encontrado: {CREDENTIALS_FILE}")
    for col in ('COL_ID_EXAMEN', 'COL_CEDULA', 'COL_FECHA_EXAMEN', 'COL_IPS',
                'COL_ESTADO', 'COL_TIPO_EXAMEN', 'COL_COMPONENTE'):
        if globals().get(col) is None:
            errores.append(f"❌ {col} no configurada")

    for ips in IPS_SOPORTADAS:
        faltan = _faltantes_plataforma(ips)
        if faltan:
            print(f"⚠️ {ips} desactivada: falta {', '.join(faltan)}")

    if errores:
        print("\n".join(errores))
        return False
    return True
