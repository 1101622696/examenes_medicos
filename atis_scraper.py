import os
import re
import base64
import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import config


def _parsear_fecha_sheet(texto):
    """
    Intenta parsear la fecha de la columna E del sheet.
    Soporta 'YYYY-MM-DD' (formato principal esperado) y 'DD/MM/YYYY' como respaldo.
    """
    texto = texto.strip()
    formatos = ['%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y']
    for fmt in formatos:
        try:
            return datetime.datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def _parsear_fecha_plataforma(texto):
    """Fecha tipo '06/05/25' (dd/mm/aa) que muestra el grid F.Emision."""
    texto = texto.strip()
    try:
        return datetime.datetime.strptime(texto, '%d/%m/%y').date()
    except ValueError:
        return None


class AtisScraper:
    def __init__(self):
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None
        os.makedirs(config.CARPETA_TEMP, exist_ok=True)

    def iniciar(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=config.HEADLESS, args=['--no-sandbox', '--disable-dev-shm-usage'])
        self.context = self.browser.new_context(accept_downloads=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(config.TIMEOUT_MS)

    def cerrar(self):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self._pw:
            self._pw.stop()

    def login(self):
        print("🔐 Iniciando sesión en ATIS Salud...")
        self.page.goto(config.ATIS_URL)

        self.page.wait_for_selector('#vUSERNAME')
        self.page.fill('#vUSERNAME', config.ATIS_USERNAME)
        self.page.fill('#vUSERPASSWORD', config.ATIS_PASSWORD)
        self.page.click('#LOGIN')

        # Esperamos a que cargue algo del panel principal.
        # Ajustar este selector si la plataforma tarda más o redirige distinto.
        self.page.wait_for_load_state('networkidle')
        print("✅ Sesión iniciada")

    def ir_a_certificados(self):
        """Navega a la sección de certificados de empresa."""
        self.page.wait_for_selector('#vCERTIFICADOS', timeout=config.TIMEOUT_MS)
        self.page.click('#vCERTIFICADOS')
        self.page.wait_for_selector('#vDOCUMENTO', timeout=config.TIMEOUT_MS)

    def buscar_cedula(self, cedula):
        campo = self.page.locator('#vDOCUMENTO')
        span0 = self.page.locator('#span_CERTIFICADOFECHAREALIZACION_0001')
        fecha_anterior = span0.inner_text().strip() if span0.count() else None

        campo.fill(cedula)
        campo.press('Enter')

        try:
            self.page.wait_for_load_state('networkidle', timeout=10000)
        except PWTimeout:
            pass
        try:
            # Espera a que el grid cambie (o desaparezca si no hay resultados)
            self.page.wait_for_function(
                """(ant) => {
                    const el = document.querySelector('#span_CERTIFICADOFECHAREALIZACION_0001');
                    const t = el ? el.innerText.trim() : null;
                    return t !== ant;
                }""",
                arg=fecha_anterior, timeout=6000)
        except PWTimeout:
            pass  # misma fecha que la búsqueda anterior, o sigue sin resultados

        filas = self.page.locator('tr[id^="Grid1ContainerRow_"]')
        resultados = []
        encabezados = self.page.locator('#Grid1ContainerTbl th').all_inner_texts()
        idx_concepto = next((k for k, t in enumerate(encabezados)
                             if t.strip().upper() == 'CONCEPTO'), None)        
        for i in range(filas.count()):
            sufijo = filas.nth(i).get_attribute('id').split('_')[-1]
            span = self.page.locator(f'#span_CERTIFICADOFECHAREALIZACION_{sufijo}')
            if not span.count():
                continue
            texto_fecha = span.inner_text().strip()
            celdas = filas.nth(i).locator('td')
            if idx_concepto is not None and idx_concepto < celdas.count():
                concepto = celdas.nth(idx_concepto).inner_text().strip()
            else:
                concepto = filas.nth(i).inner_text()            
            resultados.append({'sufijo': sufijo,
                               'fecha': _parsear_fecha_plataforma(texto_fecha),
                               'texto_fecha': texto_fecha,
                               'concepto': concepto,})
        return resultados
    
    def elegir_mejor_resultado(self, resultados, fecha_examen_sheet):
        """
        Elige la fila cuya fecha esté más cerca de fecha_examen_sheet.
        Empate -> se toma la más reciente.
        Devuelve (resultado_elegido, diferencia_dias) o (None, None) si no hay candidatos válidos.
        """
        print("\nResultados encontrados:")
        candidatos = [r for r in resultados if r['fecha'] is not None]
        
        if not candidatos:
            return None, None

        def clave(r):
            diff = abs((r['fecha'] - fecha_examen_sheet).days)
            # Ordena por menor diferencia, y como desempate por fecha más reciente (negativo = más reciente primero)
            return (diff, -r['fecha'].toordinal())

        candidatos.sort(key=clave)
        mejor = candidatos[0]
        diferencia = abs((mejor['fecha'] - fecha_examen_sheet).days)
        return mejor, diferencia

    def descargar_certificado(self, sufijo, cedula):
        icono = self.page.locator(f'#vIMPRESION_{sufijo}')
        icono.click()

        # Esperamos a que aparezca el iframe con el visor y capturamos su URL real
        self.page.wait_for_selector("#gxp0_ifrm")
        frame = None
        for _ in range(40):
            frame = next((f for f in self.page.frames
                          if "aprintcertificado" in f.url.lower()), None)
            if frame:
                break
            self.page.wait_for_timeout(250)
        if not frame:
            raise RuntimeError("No apareció el visor del certificado en ATIS")
        pdf_url = frame.url

        # Pedimos esa URL directo con el mismo contexto (mismas cookies/sesión)
        response = self.context.request.get(pdf_url)
        if not response.ok:
            raise RuntimeError(f"No se pudo descargar el PDF ({response.status}) de {pdf_url}")

        pdf_data = response.body()

        if len(pdf_data) < 1000 or not pdf_data.startswith(b'%PDF'):
            raise RuntimeError(f"La respuesta no parece un PDF válido ({len(pdf_data)} bytes)")

        nombre_seguro = re.sub(r'[^0-9A-Za-z_-]', '_', cedula)
        ruta_local = os.path.join(config.CARPETA_TEMP, f"{nombre_seguro}.pdf")
        with open(ruta_local, 'wb') as f:
            f.write(pdf_data)

        # Cerramos el visor si quedó como pestaña/página extra
        if len(self.context.pages) > 1:
            self.context.pages[-1].close()

        self.cerrar_visor_popup()
        return ruta_local

    def cerrar_visor_popup(self):
        """Cierra el popup modal de GeneXus que muestra el certificado."""
        selectores_posibles = [
            '.ui-dialog-titlebar-close',
            '[id^="gxp"][id$="_close"]',
            '.gx-popup-close',
            'span.ui-icon-closethick',
        ]

        for sel in selectores_posibles:
            boton = self.page.locator(sel)
            if boton.count() > 0 and boton.first.is_visible():
                boton.first.click()
                self.page.wait_for_selector('.gx-mask', state='hidden', timeout=5000)
                return

        # Plan B: Escape suele cerrar diálogos modales
        self.page.keyboard.press('Escape')
        try:
            self.page.wait_for_selector('.gx-mask', state='hidden', timeout=5000)
        except PWTimeout:
            pass