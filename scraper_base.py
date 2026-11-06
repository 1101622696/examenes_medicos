"""Base común para los scrapers nuevos (ICSA, SIMETRIC).
Los scrapers anteriores (ATIS, Zona Médica, HISESA, SSO) no la usan y siguen igual."""
import os
import re

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import config
from pdf_utils import es_pdf, pdf_de_respuestas, pdf_de_visor

# Botones de descarga típicos de un visor (incluye el visor pdf.js)
SELECTORES_DESCARGA = ['#download', '#secondaryDownload', 'a[download]', 'button[download]',
                       'a:has-text("Descargar")', 'button:has-text("Descargar")',
                       'input[value*="Descargar" i]', '[title*="Descargar" i]', '[title*="Download" i]']


class ScraperBase:
    NOMBRE = 'IPS'

    def __init__(self, usuario, password, etiqueta):
        self.usuario = usuario
        self.password = password
        self.etiqueta = etiqueta
        self._pw = self.browser = self.context = self.page = None
        self._descargas = []
        self._respuestas = []
        self._urls_probadas = set()
        os.makedirs(config.CARPETA_TEMP, exist_ok=True)

    # ── navegador ───────────────────────────────────────────────────
    def iniciar(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=config.HEADLESS, args=['--no-sandbox', '--disable-dev-shm-usage'])
        self.context = self.browser.new_context(accept_downloads=True)
        self.context.on('page', lambda p: p.on('download', self._on_download))
        self.page = self.context.new_page()
        self.page.set_default_timeout(config.TIMEOUT_MS)

    def _on_download(self, descarga):
        self._descargas.append(descarga)

    def _on_response(self, resp):
        self._respuestas.append(resp)

    def cerrar(self):
        for obj in (self.context, self.browser):
            try:
                obj and obj.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass

    def cerrar_visor_popup(self):
        for p in self.context.pages:
            if p != self.page:
                try:
                    p.close()
                except Exception:
                    pass

    # ── utilidades ──────────────────────────────────────────────────
    def _evaluar(self, js, arg=None):
        """evaluate tolerante a recargas de página (submit de formularios)."""
        try:
            return self.page.evaluate(js, arg)
        except Exception as e:
            if 'context was destroyed' in str(e) or 'navigat' in str(e).lower():
                try:
                    self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                    return self.page.evaluate(js, arg)
                except Exception:
                    return None
            raise

    def _esperar_red(self, ms=8000):
        try:
            self.page.wait_for_load_state('networkidle', timeout=ms)
        except PWTimeout:
            pass

    def _guardar(self, pdf, cedula, ident):
        nombre = re.sub(r'[^0-9A-Za-z_-]', '_', f'{self.NOMBRE}_{cedula}_{str(ident)[-24:]}')
        ruta = os.path.join(config.CARPETA_TEMP, f'{nombre}.pdf')
        with open(ruta, 'wb') as fh:
            fh.write(pdf)
        return ruta

    def _capturar_pdf(self, abrir_visor, segundos=20):
        """Ejecuta abrir_visor() (que devuelve la página del visor o None) y busca el PDF
        en: respuestas de red, iframes/embed/enlaces del visor, descargas, y por último
        el botón "Descargar" del visor."""
        self._descargas.clear()
        self._respuestas = respuestas = []
        self.context.on('response', self._on_response)
        visor, revisadas = None, 0
        try:
            visor = abrir_visor()
            for _ in range(segundos * 2):
                self.page.wait_for_timeout(500)
                nuevas, revisadas = respuestas[revisadas:], len(respuestas)
                pdf = pdf_de_respuestas(nuevas, self.context, (visor or self.page).url)
                if not es_pdf(pdf) and visor is not None:
                    pdf = pdf_de_visor(visor, self.context, self._urls_probadas)
                if not es_pdf(pdf):
                    pdf = self._pdf_de_descargas()
                if es_pdf(pdf):
                    return pdf
            if visor is not None:
                pdf = self._clic_descargar(visor)
                if es_pdf(pdf):
                    return pdf
            self._diagnostico(respuestas, visor)
            return None
        finally:
            self.context.remove_listener('response', self._on_response)

    def _pdf_de_descargas(self):
        for d in reversed(self._descargas):
            try:
                with open(d.path(), 'rb') as fh:
                    data = fh.read()
                if es_pdf(data):
                    return data
            except Exception:
                continue
        return None

    def _clic_descargar(self, visor):
        for fr in [visor.main_frame] + [f for f in visor.frames if f != visor.main_frame]:
            for sel in SELECTORES_DESCARGA:
                try:
                    loc = fr.locator(sel).first
                    if not loc.count() or not loc.is_visible():
                        continue
                    with visor.expect_download(timeout=15000) as info:
                        loc.click()
                    with open(info.value.path(), 'rb') as fh:
                        data = fh.read()
                    if es_pdf(data):
                        return data
                except Exception:
                    continue
        return None

    def _diagnostico(self, respuestas, visor):
        print(f"   [diag {self.NOMBRE}] respuestas:",
              [(r.url[:100], r.headers.get('content-type')) for r in respuestas][-15:])
        if visor is not None:
            print(f"   [diag {self.NOMBRE}] visor:", visor.url[:120],
                  "frames:", [f.url[:100] for f in visor.frames])
