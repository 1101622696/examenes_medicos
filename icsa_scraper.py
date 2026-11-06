"""ICSA (https://icsa.com.co/mindefensa.html). Solo psicofísico, una cuenta.

Resultados agrupados por fecha:
    Atendidos EL 17/10/2026
    1  1098727916  DIAZ FUENTES ...  CERTIFICADO PARA EL USO DE ARMAS  [imprimir]
El ícono de imprimir: onclick='ImprimirConcepto("178426","http://...","pdf")' abre
https://www.icsa.com.co/Documentos.html?id=178426 en una ventana emergente con el PDF.
Un examen sin certificado todavía no aparece (ni su título de fecha).
"""
import re

from playwright.sync_api import TimeoutError as PWTimeout

import config
from pdf_utils import es_pdf, norm, parsear_fecha, solo_digitos
from scraper_base import ScraperBase

URL_DOCUMENTO = 'https://www.icsa.com.co/Documentos.html?id={}'

# Recorre en orden del documento los títulos "Atendidos EL dd/mm/aaaa" y los íconos de
# imprimir; cada ícono queda con la fecha del último título visto antes de él.
JS_RESULTADOS = r"""() => {
  const RE = /ATENDIDOS\s+EL\s+(\d{1,2}\/\d{1,2}\/\d{4})/i;
  const titulos = [...document.querySelectorAll('body *')].filter(el =>
      RE.test(el.textContent || '') && ![...el.children].some(c => RE.test(c.textContent || '')));
  const iconos = [...document.querySelectorAll('[onclick*="ImprimirConcepto"]')];
  const items = titulos.map(el => ({el, t: 'h'})).concat(iconos.map(el => ({el, t: 'p'})));
  items.sort((a, b) => a.el === b.el ? 0 :
      (a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);
  let fecha = '', titulo = '';
  const out = [];
  for (const it of items) {
    if (it.t === 'h') {
      titulo = (it.el.textContent || '').replace(/\s+/g, ' ').trim();
      fecha = (titulo.match(RE) || [])[1] || '';
      continue;
    }
    const fila = it.el.closest('tr') || (it.el.parentElement && it.el.parentElement.parentElement);
    let celdas = [];
    if (fila && fila.cells) celdas = [...fila.cells].map(c => (c.innerText || '').trim());
    else if (fila) celdas = (fila.innerText || '').split(/\t|\n/).map(s => s.trim()).filter(Boolean);
    out.push({fecha, titulo, celdas, onclick: it.el.getAttribute('onclick') || ''});
  }
  return out;
}"""

RE_ID = re.compile(r"""ImprimirConcepto\(\s*["']?([^"',\s)]+)""")


class IcsaScraper(ScraperBase):
    NOMBRE = 'ICSA'

    def __init__(self, usuario=None, password=None, etiqueta='ICSA'):
        super().__init__(usuario or config.ICSA_USERNAME, password or config.ICSA_PASSWORD, etiqueta)

    def login(self):
        print("🔐 Iniciando sesión en ICSA...")
        self.page.goto(config.ICSA_URL, wait_until='domcontentloaded')
        self.page.locator('#TxtUsuario').wait_for(timeout=20000)
        self.page.fill('#TxtUsuario', self.usuario)
        self.page.fill('#TxtContrasena', self.password)
        self.page.click('#submit')
        try:
            self.page.locator('#TxtFiltro').wait_for(timeout=25000)
        except PWTimeout:
            raise RuntimeError("Login ICSA falló")
        print("✅ Sesión iniciada en ICSA")

    def ir_a_certificados(self):
        self.page.locator('#TxtFiltro').wait_for(timeout=20000)

    def _leer(self, cedula):
        resultados = []
        for f in self._evaluar(JS_RESULTADOS) or []:
            celdas = f['celdas']
            if not any(solo_digitos(c) == cedula for c in celdas):
                continue
            # Concepto = la celda con el tipo de certificado (solo se acepta el texto exacto)
            concepto = next((c for c in celdas if norm(c) == 'CERTIFICADO PARA EL USO DE ARMAS'),
                            ' | '.join(celdas))
            m = RE_ID.search(f['onclick'])
            resultados.append({
                'identificador': m.group(1) if m else None,
                'fecha': parsear_fecha(f['fecha']),
                'texto_fecha': f['fecha'],
                'concepto': concepto,
            })
        vistos, unicos = set(), []
        for r in resultados:
            if r['identificador'] not in vistos:
                vistos.add(r['identificador'])
                unicos.append(r)
        return unicos

    def buscar_cedula(self, cedula):
        # Fechas vacías = todo el histórico de la persona
        self.page.evaluate("""() => {
            for (const id of ['TxtDesde', 'TxtHasta']) {
                const el = document.getElementById(id);
                if (el) { el.value = ''; el.dispatchEvent(new Event('change', {bubbles: true})); }
            }
        }""")
        campo = self.page.locator('#TxtFiltro')
        campo.fill('')
        campo.fill(cedula)
        self.page.click('input[type="button"][value="Filtrar"]')
        self._esperar_red()
        espera = 0
        while True:
            resultados = self._leer(cedula)
            if resultados or espera >= config.ICSA_ESPERA_MS:
                return resultados
            self.page.wait_for_timeout(500)
            espera += 500

    def descargar_certificado(self, identificador, cedula):
        def abrir():
            icono = self.page.locator(
                f'[onclick*="ImprimirConcepto"][onclick*="{identificador}"]').first
            try:
                with self.context.expect_page(timeout=10000) as info:
                    icono.click()
                visor = info.value
            except Exception:                     # si no abre ventana, ir directo al visor
                visor = self.context.new_page()
                try:
                    visor.goto(URL_DOCUMENTO.format(identificador), timeout=30000)
                except Exception:
                    pass
            try:
                visor.wait_for_load_state('domcontentloaded', timeout=15000)
            except Exception:
                pass
            return visor

        pdf = self._capturar_pdf(abrir)
        self.cerrar_visor_popup()
        if not es_pdf(pdf):
            raise RuntimeError("No se pudo obtener el PDF desde ICSA")
        return self._guardar(pdf, cedula, identificador)
