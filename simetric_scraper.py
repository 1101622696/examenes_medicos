"""SIMETRIC (http://190.60.193.163/sga2/index.php).

Dos cuentas con el mismo enlace: 1 = psicofísico, 2 = psicosensométrico. Igual el tipo
se decide por la columna EXAMEN de cada fila ("SEG PRIVADA" = psicofísico,
"SEG VIAL" = psicosensométrico), porque un vial puede salir en la cuenta 1.

Tabla de resultados: CEDULA | NOMBRE | APELLIDO | FECHA SOLICITUD | EXAMEN | APTO | CENTRO | CERTIFICADO
El certificado es un enlace "Ver.." con onclick="abrirVentana('https://.../4306207.pdf')":
el PDF se baja directo de esa URL.
"""
import re

from playwright.sync_api import TimeoutError as PWTimeout

import config
from pdf_utils import es_pdf, parsear_fecha, solo_digitos
from scraper_base import ScraperBase

# Filas de las tablas que tengan encabezados CEDULA y EXAMEN
JS_FILAS = r"""() => {
  const N = t => (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
                          .toUpperCase().replace(/\s+/g, ' ').trim();
  const out = [];
  for (const tb of document.querySelectorAll('table')) {
    let headers = [...tb.querySelectorAll('thead th, thead td')].map(c => N(c.innerText));
    let filas = [...tb.querySelectorAll('tbody tr')];
    if (!headers.length) {
      const todas = [...tb.querySelectorAll('tr')];
      if (!todas.length) continue;
      headers = [...todas[0].cells].map(c => N(c.innerText));
      filas = todas.slice(1);
    }
    if (!headers.some(h => h.includes('CEDULA')) || !headers.some(h => h.includes('EXAMEN'))) continue;
    for (const tr of filas) {
      if (!tr.cells || tr.cells.length < 3) continue;
      out.push({
        headers,
        celdas: [...tr.cells].map(c => (c.innerText || '').trim()),
        enlaces: [...tr.querySelectorAll('[onclick], a[href]')]
                   .map(a => (a.getAttribute('onclick') || '') + ' ' + (a.getAttribute('href') || '')),
      });
    }
  }
  return out;
}"""

RE_VENTANA = re.compile(r"""abrirVentana\(\s*['"]([^'"]+)['"]""")
RE_PDF = re.compile(r"""(https?://[^'"\s]+\.pdf)""", re.I)

# Posiciones por defecto si no se reconocen los encabezados
POS = {'CEDULA': 0, 'FECHA': 3, 'EXAMEN': 4, 'APTO': 5, 'CERTIFICADO': 7}


def _col(headers, clave):
    for i, h in enumerate(headers):
        if clave in h:
            return i
    return POS[clave]


def _celda(celdas, i):
    return celdas[i] if 0 <= i < len(celdas) else ''


class SimetricScraper(ScraperBase):
    NOMBRE = 'SIMETRIC'

    def __init__(self, usuario=None, password=None, etiqueta='cuenta 1'):
        super().__init__(usuario or config.SIMETRIC_USERNAME1,
                         password or config.SIMETRIC_PASSWORD1, etiqueta)

    def login(self):
        print(f"🔐 Iniciando sesión en SIMETRIC ({self.etiqueta})...")
        self.page.goto(config.SIMETRIC_URL, wait_until='domcontentloaded')
        self.page.locator('#name').wait_for(timeout=20000)
        self.page.fill('#name', self.usuario)
        self.page.fill('#password', self.password)
        self.page.click('input[type="submit"][name="submit"]')
        try:
            self.page.locator('#cedula').wait_for(timeout=20000)
        except PWTimeout:
            raise RuntimeError(f"Login SIMETRIC falló ({self.etiqueta})")
        print(f"✅ Sesión iniciada en SIMETRIC ({self.etiqueta})")

    def ir_a_certificados(self):
        self.page.locator('#cedula').wait_for(timeout=20000)

    def _leer(self, cedula):
        resultados = []
        for f in self._evaluar(JS_FILAS) or []:
            h, c = f['headers'], f['celdas']
            if solo_digitos(_celda(c, _col(h, 'CEDULA'))) != cedula:
                continue
            texto_fecha = _celda(c, _col(h, 'FECHA'))
            enlaces = ' '.join(f['enlaces'])
            m = RE_VENTANA.search(enlaces) or RE_PDF.search(enlaces)
            resultados.append({
                'identificador': m.group(1) if m else None,     # None = aún sin certificado
                'fecha': parsear_fecha(texto_fecha),
                'texto_fecha': texto_fecha,
                'concepto': _celda(c, _col(h, 'EXAMEN')),       # SEG PRIVADA / SEG VIAL
                'apto': _celda(c, _col(h, 'APTO')),
            })
        # sin repetidos (la tabla inicial puede traer la misma fila)
        vistos, unicos = set(), []
        for r in resultados:
            k = (r['identificador'], r['texto_fecha'], r['concepto'])
            if k not in vistos:
                vistos.add(k)
                unicos.append(r)
        return unicos

    def buscar_cedula(self, cedula):
        campo = self.page.locator('#cedula')
        campo.fill('')
        campo.fill(cedula)
        self.page.locator('button[type="submit"]:has-text("Consultar")').first.click()
        self._esperar_red()
        # Esperar a que aparezcan filas de esta cédula (o agotar la espera = no encontrado)
        espera = 0
        while True:
            resultados = self._leer(cedula)
            if resultados or espera >= config.SIMETRIC_ESPERA_MS:
                return resultados
            self.page.wait_for_timeout(500)
            espera += 500

    def descargar_certificado(self, identificador, cedula):
        url = identificador
        pdf = None
        try:
            r = self.context.request.get(url, headers={'Referer': self.page.url}, timeout=60000)
            pdf = r.body() if r.ok else None
        except Exception as e:
            print(f"   ⚠️ SIMETRIC: descarga directa falló ({e}); intento por la ventana emergente")

        if not es_pdf(pdf):                       # respaldo: abrir la ventana como un usuario
            def abrir():
                enlace = self.page.locator(f'[onclick*="{url}"]').first
                try:
                    with self.context.expect_page(timeout=10000) as info:
                        enlace.click()
                    return info.value
                except Exception:
                    p = self.context.new_page()
                    try:
                        p.goto(url, timeout=30000)
                    except Exception:
                        pass                      # una URL de PDF puede terminar en descarga
                    return p
            pdf = self._capturar_pdf(abrir)

        self.cerrar_visor_popup()
        if not es_pdf(pdf):
            raise RuntimeError("No se pudo obtener el PDF desde SIMETRIC")
        return self._guardar(pdf, cedula, url.rsplit('/', 1)[-1])
