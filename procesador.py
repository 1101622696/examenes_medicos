import os
import re
from collections import defaultdict
import config
from sheets_handler import SheetsHandler, normalizar
from drive_handler import DriveHandler
from date_matcher import elegir_mejor_resultado
from atis_scraper import AtisScraper
from zonamedica_scraper import ZonaMedicaScraper
from hisesa_scraper import HisesaScraper
from sso_scraper import SsoScraper
from icsa_scraper import IcsaScraper
from simetric_scraper import SimetricScraper

ETIQUETAS = {'ALTURAS': 'Alturas', 'POSINCAPACIDAD': 'Posincapacidad',
             'EGRESO': 'Retiro', 'NORMAL': 'concepto médico',
             'PSICOFISICO': 'Psicofísico', 'PSICOSENSOMETRICO': 'Psicosensométrico'}

ICSA_CERTIFICADO = 'CERTIFICADO PARA EL USO DE ARMAS'   # único texto aceptado en ICSA


def nombre_archivo_examen(f):
    """Igual que el cargue manual: CEDULA_TIPO_yyyy-MM-dd[_Componente].pdf
    (_Alturas, _Psicofisico, _Psicosensometrico; el principal no lleva sufijo)."""
    comp = re.sub(r'[\s,]+', '', f['componente'] or '')
    sufijo = '' if normalizar(comp) in ('', 'PRINCIPAL') else '_' + comp
    return f"{f['cedula']}_{f['tipo_examen'].strip()}_{f['fecha_examen']:%Y-%m-%d}{sufijo}.pdf"


def _es_psico(plataforma):
    return plataforma.startswith(config.IPS_ICSA) or plataforma.startswith(config.IPS_SIMETRIC)


def _categoria_fila(f):
    if f.get('psico'):
        return f['psico']
    if 'ALTURA' in normalizar(f['componente']):
        return 'ALTURAS'
    tipo = normalizar(f['tipo_examen'])
    if 'POSINCAPACIDAD' in tipo:
        return 'POSINCAPACIDAD'
    if tipo == 'EGRESO':
        return 'EGRESO'
    return 'NORMAL'        # Ingreso, Periodico, Seguimiento, Complementario


def _categoria_certificado(plataforma, concepto):
    c = normalizar(concepto)
    if plataforma.startswith(config.IPS_SIMETRIC):         # columna EXAMEN
        if 'SEG VIAL' in c:
            return 'PSICOSENSOMETRICO'
        if 'SEG PRIVADA' in c:
            return 'PSICOFISICO'
        return 'OTRO'
    if plataforma.startswith(config.IPS_ICSA):              # solo el texto exacto
        return 'PSICOFISICO' if c == ICSA_CERTIFICADO else 'OTRO'
    if 'ALTURA' in c:
        return 'ALTURAS'
    if 'POST INCAPACIDAD' in c or 'POSINCAPACIDAD' in c or 'VALORACION MEDICO LABORAL' in c:
        return 'POSINCAPACIDAD'
    if plataforma == config.IPS_ATIS and 'RETIRO' in c:
        return 'EGRESO'
    return 'NORMAL'


def _filtrar_por_tipo(resultados, f, plataforma):
    if plataforma.startswith('HISESA'):
        return resultados                        # HISESA sin filtro
    cat = _categoria_fila(f)
    if _es_psico(plataforma):
        return [r for r in resultados
                if _categoria_certificado(plataforma, r.get('concepto', '')) == cat]
    if cat == 'EGRESO' and plataforma != config.IPS_ATIS:
        cat = 'NORMAL'                           # en Zona Médica el egreso sale normal
    return [r for r in resultados
            if _categoria_certificado(plataforma, r.get('concepto', '')) == cat]

def _procesar_plataforma(scraper, nombre, items, sheets, drive):
    """Devuelve (filas_cargadas:set, motivos:{fila: texto}). No escribe en Sheets (solo buffers)."""
    por_cedula = defaultdict(list)
    for it in items:
        por_cedula[it['cedula']].append(it)

    cargadas, motivos = set(), {}
    try:
        scraper.iniciar()
        scraper.login()
        scraper.ir_a_certificados()

        for cedula, filas in por_cedula.items():
            print(f"🔎 [{nombre}] {cedula}")
            try:
                resultados = scraper.buscar_cedula(cedula)
            except Exception as e:
                for f in filas:
                    motivos[f['fila']] = f"{nombre}: error buscando ({e})"
                continue

            if not resultados:
                for f in filas:
                    motivos[f['fila']] = f"{nombre}: no encontrado en plataforma"
                continue

            links = {}   # identificador -> (link, nombre_archivo)
            for f in filas:
                if f['fecha_examen'] is None:
                    motivos[f['fila']] = f"{nombre}: sin fecha de examen válida en el sheet ('{f['texto_fecha_examen']}')"
                    continue
                cat = _categoria_fila(f)
                if nombre.startswith('HISESA') and cat == 'ALTURAS':
                    motivos[f['fila']] = f"{nombre}: Alturas no automatizado en HISESA"
                    continue

                candidatos = _filtrar_por_tipo(resultados, f, nombre)
                if not candidatos:
                    motivos[f['fila']] = f"{nombre}: la persona aparece, pero sin certificado de {ETIQUETAS[cat]}"
                    continue

                mejor, dif = elegir_mejor_resultado(candidatos, f['fecha_examen'])
                if mejor is None:
                    motivos[f['fila']] = f"{nombre}: encontrado pero sin fechas legibles"
                    continue
                if dif > config.TOLERANCIA_DIAS:
                    motivos[f['fila']] = (f"{nombre}: {ETIQUETAS[cat]} más cercano {mejor['texto_fecha']} "
                                          f"a {dif} días (> {config.TOLERANCIA_DIAS})")
                    continue
                ident = mejor.get('identificador') or mejor.get('sufijo')
                if not ident:
                    motivos[f['fila']] = f"{nombre}: examen encontrado, aún sin certificado para imprimir"
                    continue
                try:
                    if ident not in links:
                        archivo = nombre_archivo_examen(f)
                        ruta = scraper.descargar_certificado(ident, cedula)
                        links[ident] = (drive.subir_archivo(ruta, archivo), archivo)
                        try:
                            os.remove(ruta)
                        except OSError:
                            pass
                    link, archivo = links[ident]
                    sheets.marcar_cargado(f, link, nombre, mejor['texto_fecha'], dif, archivo)
                    cargadas.add(f['fila'])
                except Exception as e:
                    motivos[f['fila']] = f"{nombre}: error descargando/subiendo ({e})"
                    try:
                        scraper.cerrar_visor_popup()
                    except Exception:
                        pass
    except Exception as e:
        for it in items:
            if it['fila'] not in cargadas and it['fila'] not in motivos:
                motivos[it['fila']] = f"{nombre}: error general ({e})"
    finally:
        scraper.cerrar()
    return cargadas, motivos


def _procesar_multicuenta(nombre, fabrica, cuentas, items, sheets, drive, cargados):
    """Cuenta 1 con todo; cada cuenta siguiente solo con lo que no cargaron las anteriores.
    Devuelve el número de cargados."""
    cargadas, motivos_todas, escritos = set(), defaultdict(list), []
    for n, (usr, pwd) in enumerate(cuentas, 1):
        restantes = [it for it in items if it['fila'] not in cargadas]
        if not restantes or not usr:
            continue
        ok, motivos = _procesar_plataforma(
            fabrica(usr, pwd, f'cuenta {n}'), f'{nombre}-{n}', restantes, sheets, drive)
        cargadas |= ok
        for fila, m in motivos.items():
            motivos_todas[fila].append(m)
        nuevos = sheets.flush()
        escritos += nuevos
        cargados += nuevos
    for it in items:
        if it['fila'] not in cargadas:
            sheets.registrar_log(it, ' | '.join(motivos_todas[it['fila']]) or f'{nombre}: sin resultado')
    sheets.flush()
    return len(escritos)


def _fuera_de_ventana(p, hoy):
    """Misma regla que validarCargue_: un Solicitado sin fecha o fuera de ±DIAS_VENTANA_CARGUE
    no se puede cargar. Para psico (ICSA/SIMETRIC) la ventana aplica también a Confirmado."""
    if normalizar(p['estado']) != 'SOLICITADO' and not p.get('psico'):
        return False
    return p['fecha_examen'] is None or abs((hoy - p['fecha_examen']).days) > config.DIAS_VENTANA_CARGUE


def ejecutar(resumen=None):
    inicio = config.ahora()
    sheets, drive = SheetsHandler(), DriveHandler()
    pendientes = sheets.obtener_pendientes()
    hoy = config.ahora().date()
    validos = []
    for p in pendientes:
        if _fuera_de_ventana(p, hoy):
            detalle = '' if p.get('psico') else ', sin confirmar'
            sheets.registrar_log(p, f"Fuera de ventana de cargue (±{config.DIAS_VENTANA_CARGUE} días"
                                    f"{detalle}): debe reprogramarse")
            continue
        validos.append(p)
    pendientes = validos
    sheets.flush()
    por_ips = defaultdict(list)
    for p in pendientes:
        por_ips[p['ips']].append(p)

    # Plataformas sin credenciales: se dejan en el log y no se abren
    for ips in config.IPS_SOPORTADAS:
        if por_ips.get(ips) and not config.plataforma_habilitada(ips):
            for it in por_ips.pop(ips):
                sheets.registrar_log(it, f"{ips}: plataforma desactivada (faltan credenciales en .env)")
    sheets.flush()

    cargados, por_plataforma = [], {}
    if resumen is not None:
        resumen.update(revisados=len(pendientes), cargados=cargados, por_plataforma=por_plataforma)

    # ── Una cuenta: Zona Médica, SAOCSS (ATIS), SSO, ICSA ───────────
    for ips, fabrica in ((config.IPS_ZONAMEDICA, ZonaMedicaScraper),
                         (config.IPS_ATIS, AtisScraper),
                         (config.IPS_SSO, SsoScraper),
                         (config.IPS_ICSA, IcsaScraper)):
        items = por_ips.get(ips, [])
        if not items:
            continue
        ok, motivos = _procesar_plataforma(fabrica(), ips, items, sheets, drive)
        for it in items:
            if it['fila'] in motivos:
                sheets.registrar_log(it, motivos[it['fila']])
        escritos = sheets.flush()
        cargados += escritos
        por_plataforma[ips] = {'revisados': len(items), 'cargados': len(escritos)}

    # ── HISESA: dos cuentas, la 2ª solo con lo que no cargó la 1ª ───
    items = por_ips.get(config.IPS_HISESA, [])
    if items:
        cuentas = [(config.HISESA_USERNAME1, config.HISESA_PASSWORD1),
                   (config.HISESA_USERNAME2, config.HISESA_PASSWORD2)]
        cargadas_h, motivos_h, escritos_h = set(), defaultdict(list), []
        for n, (usr, pwd) in enumerate(cuentas, 1):
            restantes = [it for it in items if it['fila'] not in cargadas_h]
            if not restantes or not usr:
                continue
            ok, motivos = _procesar_plataforma(
                HisesaScraper(usr, pwd, f'cuenta {n}'), f'HISESA-{n}', restantes, sheets, drive)
            cargadas_h |= ok
            for fila, m in motivos.items():
                motivos_h[fila].append(m)
            nuevos = sheets.flush()
            escritos_h += nuevos
            cargados += nuevos       # guarda cargados de esta pasada
        for it in items:
            if it['fila'] not in cargadas_h:
                sheets.registrar_log(it, ' | '.join(motivos_h[it['fila']]) or 'HISESA: sin resultado')
        sheets.flush()
        por_plataforma[config.IPS_HISESA] = {'revisados': len(items), 'cargados': len(escritos_h)}

    # ── SIMETRIC: cuenta 1 (psicofísico) y cuenta 2 (psicosensométrico) ──
    # Un "SEG VIAL" puede aparecer en la cuenta 1: por eso la 1 busca todo y la 2 lo que falte.
    # Cada resultado se empareja por la columna EXAMEN, no por la cuenta.
    items = por_ips.get(config.IPS_SIMETRIC, [])
    if items:
        cuentas = [(config.SIMETRIC_USERNAME1, config.SIMETRIC_PASSWORD1),
                   (config.SIMETRIC_USERNAME2, config.SIMETRIC_PASSWORD2)]
        n = _procesar_multicuenta(config.IPS_SIMETRIC, SimetricScraper, cuentas,
                                  items, sheets, drive, cargados)
        por_plataforma[config.IPS_SIMETRIC] = {'revisados': len(items), 'cargados': n}

    return {
        'inicio': inicio.strftime('%Y-%m-%d %H:%M:%S'),
        'fin': config.ahora().strftime('%Y-%m-%d %H:%M:%S'),
        'revisados': len(pendientes),
        'por_plataforma': por_plataforma,
        'cargados': cargados,
    }
