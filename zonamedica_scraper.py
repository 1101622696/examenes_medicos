import os
import re
import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import config
from date_matcher import elegir_mejor_resultado  # reexportado para usar igual que en AtisScraper

ZONAMEDICA_URL = 'https://certificados.zonamedicaips.com/certificado/'


def _parsear_fecha_zonamedica(texto):
    """Fecha tipo '2025-10-02 00:00:00' que muestra la columna Fecha."""
    texto = texto.strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


class ZonaMedicaScraper:
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
        print("🔐 Iniciando sesión en Zona Médica IPS...")
        self.page.goto(config.ZONAMEDICA_URL, wait_until='domcontentloaded')

        # login_frame = self.page.frame_locator('frame[src*="valida"]')
        login_frame = self.page.frame_locator('frame[name="TopFrame"]')
        login_frame.locator('#usuario').wait_for(timeout=15000)
        login_frame.locator('#usuario').fill(config.ZONAMEDICA_USERNAME)
        login_frame.locator('#numero').fill(config.ZONAMEDICA_PASSWORD)
        login_frame.locator('input[name="commit"][value="Entrar"]').click()

        self.page.wait_for_load_state('networkidle')
        print("✅ Sesión iniciada en Zona Médica")

        print("Frames tras login:", [f.url for f in self.page.frames])
        self.page.screenshot(path="debug_post_login.png", full_page=True)

    def ir_a_certificados(self):
        content_frame = self.page.frame_locator('frame[name="TopFrame"]')
        content_frame.locator('input[name="cert"][value="CERTIFICADOS"]').click()
        self.page.wait_for_load_state('networkidle')
        print("Frame tras clic en CERTIFICADOS:", self.page.frame(name="TopFrame").url)


        # """No-op: en Zona Médica el login ya deja en la pantalla de búsqueda."""
        # pass

    def buscar_cedula(self, cedula):
        # """
        # Busca la cédula y devuelve una lista de dicts:

        content_frame = self.page.frame_locator('frame[name="TopFrame"]')
        campo = content_frame.locator('input[name="id"]')
        campo.wait_for(timeout=15000)
        campo.fill('')
        campo.fill(cedula)
        content_frame.locator('input[name="tipo"][value="Identificacion"]').click()

        try:
            content_frame.locator(f'td:text-is("{cedula}")').first.wait_for(timeout=15000)
        except PWTimeout:
            return []  # no se encontró esa cédula en la plataforma

        filas = content_frame.locator('table tr').filter(
            has=content_frame.locator('a[href*="tipo=1"]')
        )
        total = filas.count()
        resultados = []
        try:
            encabezados = content_frame.locator(
                'tr:has(th:text-is("Tipo")), tr:has(td:text-is("Tipo"))'
            ).first.locator('th, td').all_inner_texts()
            idx_tipo = next((k for k, t in enumerate(encabezados)
                             if t.strip().upper() == 'TIPO'), None)
        except Exception:
            idx_tipo = None
        for i in range(total):
            fila = filas.nth(i)
            celdas = fila.locator('td')
            # href = fila.locator('a[href*="tipo=1"]').first.get_attribute('href')

            identificacion_fila = celdas.nth(3).inner_text().strip()
            if identificacion_fila != str(cedula):
                continue

            href = fila.locator('a[href*="tipo=1"]').first.get_attribute('href')
            m = re.search(r'num=(\d+)', href or '')
            if not m:
                continue
            identificador = m.group(1)

            # celdas = fila.locator('td')
            texto_fecha = celdas.nth(7).inner_text().strip()
            fecha = _parsear_fecha_zonamedica(texto_fecha)
            if idx_tipo is not None and idx_tipo < celdas.count():
                concepto = celdas.nth(idx_tipo).inner_text().strip()
            else:
                concepto = fila.inner_text()
            resultados.append({
                # 'numero_certificado': numero_certificado,
                'identificador': identificador,
                'concepto': concepto,
                'fecha': fecha,
                'texto_fecha': texto_fecha,
                # 'href_pdf': href_pdf,
            })

        return resultados

    def descargar_certificado(self, identificador, cedula):
        """
        Recibe el dict elegido por elegir_mejor_resultado (con 'numero_certificado')
        y descarga el PDF correspondiente.
        """

        content_frame = self.page.frame_locator('frame[name="TopFrame"]')
        link = content_frame.locator(f'a[href*="num={identificador}"][href*="tipo=1"]').first

        with self.page.expect_download() as descarga_info:
            link.click()
        descarga = descarga_info.value

        nombre_seguro = re.sub(r'[^0-9A-Za-z_-]', '_', cedula)
        ruta_local = os.path.join(config.CARPETA_TEMP, f"{nombre_seguro}.pdf")
        descarga.save_as(ruta_local)

        return ruta_local

    def cerrar_visor_popup(self):
        """No-op: Zona Médica descarga directo, no hay popup que cerrar."""
        pass