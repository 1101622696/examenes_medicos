import re
import datetime
import unicodedata
import gspread
from gspread.utils import rowcol_to_a1
import config


# ── Funciones auxiliares (FUERA de la clase) ────────────────────────
def normalizar(texto):
    t = unicodedata.normalize('NFD', str(texto or '')).encode('ascii', 'ignore').decode()
    return ' '.join(t.upper().split())


def limpiar_cedula(texto):
    return re.sub(r'[.,\s]', '', str(texto or ''))


def parsear_fecha_sheet(texto):
    texto = (texto or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def _letra(idx0):
    """Índice base 0 → letra de columna (0→A, 26→AA)."""
    return rowcol_to_a1(1, idx0 + 1).rstrip('0123456789')


ESTADOS_ORIGEN_N = {normalizar(e) for e in config.ESTADOS_ORIGEN}
IPS_N = {normalizar(i) for i in config.IPS_SOPORTADAS}


class SheetsHandler:
    def __init__(self):
        self.client = gspread.service_account(filename=config.CREDENTIALS_FILE)
        self.libro = self.client.open_by_key(config.GOOGLE_SHEET_ID)
        self.sheet = self.libro.worksheet(config.SHEET_NAME)

        try:
            self.logs_sheet = self.libro.worksheet(config.LOGS_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            print(f"⚠️  No se encontró la hoja '{config.LOGS_SHEET_NAME}'.")
            self.logs_sheet = None

        try:
            self.bitacora_sheet = self.libro.worksheet(config.BITACORA_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            print(f"⚠️  No se encontró la hoja '{config.BITACORA_SHEET_NAME}'")
            self.bitacora_sheet = None

        self._cargados = []
        self._logs = []
        print(f"✅ Conectado a Google Sheets: '{config.SHEET_NAME}'")

    # ── LECTURA: una sola llamada, solo columnas necesarias ──────────
    def obtener_pendientes(self):
        ini = config.INICIO_FILA
        campos = {'estado': config.COL_ESTADO, 'cedula': config.COL_CEDULA,
                  'ips': config.COL_IPS, 'fecha': config.COL_FECHA_EXAMEN,
                  'tipo': config.COL_TIPO_EXAMEN, 'componente': config.COL_COMPONENTE,}
        if config.COL_ID_EXAMEN is not None:
            campos['id'] = config.COL_ID_EXAMEN

        rangos = [f'{_letra(c)}{ini}:{_letra(c)}' for c in campos.values()]
        bloques = self.sheet.batch_get(rangos)   # ← 1 llamada a la API

        cols = {k: [r[0] if r else '' for r in b] for k, b in zip(campos, bloques)}
        n = max((len(v) for v in cols.values()), default=0)

        def get(k, i):
            return str(cols[k][i]).strip() if k in cols and i < len(cols[k]) else ''

        pendientes = []
        for i in range(n):
            estado = get('estado', i)
            if normalizar(estado) not in ESTADOS_ORIGEN_N:      # filtro 1: estado
                continue
            ips = normalizar(get('ips', i))
            if ips not in IPS_N:                                 # filtro 2: IPS
                continue
            cedula = limpiar_cedula(get('cedula', i))
            if not cedula:
                continue
            componente = get('componente', i)
            if normalizar(componente) not in ('PRINCIPAL', 'ALTURAS', ''):
                continue
            texto_fecha = get('fecha', i)
            pendientes.append({
                'fila': ini + i,
                'cedula': cedula,
                'ips': ips,
                'estado': estado,
                'tipo_examen': get('tipo', i),
                'texto_fecha_examen': texto_fecha,
                'fecha_examen': parsear_fecha_sheet(texto_fecha),
                'id_examen': get('id', i),
                'componente': componente,
            })

        print(f"📋 {len(pendientes)} exámenes pendientes (Solicitado/Confirmado en IPS automatizadas)")
        return pendientes

    # ── BUFFERS ─────────────────────────────────────────────────────
    def marcar_cargado(self, item, link, plataforma, texto_fecha_cert, dias, nombre_archivo):
        detalle = (f"Cargue automático {plataforma} | certificado {texto_fecha_cert} "
                   f"({dias} días de diferencia) | {link}")
        self._cargados.append({'item': item, 'link': link, 'plataforma': plataforma,
                               'detalle': detalle, 'fecha_cert': texto_fecha_cert,
                               'nombre_archivo': nombre_archivo})

    def registrar_log(self, item, motivo):
        self._logs.append(self._fila_log(item, motivo))
        print(f"   📝 {item['cedula']} -> {motivo}")

    def _fila_log(self, item, motivo):
        return [item['cedula'], motivo, config.ahora().strftime('%Y-%m-%d %H:%M:%S'),
                item['ips'], item['id_examen']]

    # ── VERIFICACIÓN previa a escribir (1 llamada) ──────────────────
    def _filas_vigentes(self, items):
        rangos = []
        for it in items:
            rangos += [f"{_letra(config.COL_ESTADO)}{it['fila']}",
                       f"{_letra(config.COL_CEDULA)}{it['fila']}"]
        bloques = self.sheet.batch_get(rangos)

        def celda(b):
            return b[0][0] if b and b[0] else ''

        vigentes = set()
        for k, it in enumerate(items):
            estado, cedula = celda(bloques[2 * k]), celda(bloques[2 * k + 1])
            if normalizar(estado) in ESTADOS_ORIGEN_N and limpiar_cedula(cedula) == it['cedula']:
                vigentes.add(it['fila'])
        return vigentes

    # ── ESCRITURA en lote ───────────────────────────────────────────
    def flush(self):
        """Escribe cargados + Bitácora + Logs. Devuelve los cargados efectivamente escritos."""
        escritos = []
        if self._cargados:
            vigentes = self._filas_vigentes([c['item'] for c in self._cargados])
            ahora = config.ahora().strftime('%Y-%m-%d %H:%M:%S')
            updates, bitacora = [], []

            for c in self._cargados:
                it, f = c['item'], c['item']['fila']
                if f not in vigentes:
                    self._logs.append(self._fila_log(
                        it, f"NO escrito: la fila cambió durante la revisión. PDF en Drive: {c['link']}"))
                    continue
                updates += [
                    {'range': f'{_letra(config.COL_LINK_CERTIFICADO)}{f}', 'values': [[c['link']]]},
                    {'range': f'{_letra(config.COL_ESTADO)}{f}', 'values': [[config.ESTADO_DESTINO]]},
                    {'range': f'{_letra(config.COL_FECHA_CARGUE)}{f}', 'values': [[ahora]]},
                ]
                bitacora.append([ahora, config.USUARIO_CARGA, config.BITACORA_ORIGEN,
                                 it['id_examen'], it['cedula'], config.BITACORA_ACCION,
                                 it['estado'], config.ESTADO_DESTINO, c['nombre_archivo']])
                self._logs.append(self._fila_log(it, f"Cargado: {c['detalle']}"))
                escritos.append({
                    'fila': f, 'cedula': it['cedula'], 'id_examen': it['id_examen'],
                    'ips': it['ips'], 'plataforma': c['plataforma'], 'link': c['link'],
                    'nombre_archivo': c['nombre_archivo'],
                    'fecha_examen': it['texto_fecha_examen'], 'fecha_certificado': c['fecha_cert'],
                    'estado_anterior': it['estado'],
                })

            if updates:
                self.sheet.batch_update(updates, value_input_option='USER_ENTERED')
                print(f"   💾 {len(escritos)} filas marcadas como Cargado")
            if bitacora and self.bitacora_sheet:
                self.bitacora_sheet.append_rows(bitacora, value_input_option='USER_ENTERED',
                                                table_range='A1')

        if self._logs and self.logs_sheet:
            self.logs_sheet.append_rows(self._logs, value_input_option='USER_ENTERED',
                                        table_range='A1')

        self._cargados, self._logs = [], []
        return escritos