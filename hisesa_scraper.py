import os
import re
import datetime
import unicodedata
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import config
import base64

LABEL = 'Fecha y hora de llegada'
MESES = {'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4, 'MAYO': 5, 'JUNIO': 6,
         'JULIO': 7, 'AGOSTO': 8, 'SEPTIEMBRE': 9, 'SETIEMBRE': 9, 'OCTUBRE': 10,
         'NOVIEMBRE': 11, 'DICIEMBRE': 12}

# Marca las etiquetas actuales para descartar resultados de la búsqueda anterior
JS_MARCAR_VIEJOS = """(label) => {
  [...document.querySelectorAll('body *')].filter(el =>
     el.textContent.includes(label) && ![...el.children].some(c => c.textContent.includes(label))
  ).forEach(el => el.setAttribute('data-hisesa-viejo', '1'));
}"""

# Por cada etiqueta "Fecha y hora de llegada" sube hasta su card y devuelve texto + botones
JS_CARDS = """(label) => {
  const etiquetas = [...document.querySelectorAll('body *')].filter(el =>
     !el.hasAttribute('data-hisesa-viejo') &&
     el.textContent.includes(label) &&
     ![...el.children].some(c => c.textContent.includes(label)));
  return etiquetas.map(lab => {
    let card = lab;
    while (card.parentElement && card.parentElement !== document.body) {
      const p = card.parentElement;
      if (p.textContent.split(label).length - 1 > 1) break;   // ya abarcaría otra card
      card = p;
    }
    const txt = card.innerText || '';
    const i = txt.indexOf(label);
    return {
      fragmento: i >= 0 ? txt.substring(i, i + 160) : '',
      botones: [...card.querySelectorAll('button[onclick*="MostrarDocumento"]')]
                 .map(b => b.getAttribute('onclick'))
    };
  });
}"""

RE_BOTON = re.compile(r"""MostrarDocumento\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]*)['"]""")

# Lee el PDF que muestran los iframes/embed del visor (blob:, data: o URL normal)
JS_VISOR = """async () => {
  const out = [];
  for (const el of document.querySelectorAll('iframe, embed, object')) {
    const src = el.getAttribute('src') || el.getAttribute('data') || '';
    if (!src || src === 'about:blank') continue;
    if (src.startsWith('blob:') || src.startsWith('data:')) {
      try {
        const b = new Uint8Array(await (await fetch(src)).arrayBuffer());
        let s = '';
        for (let i = 0; i < b.length; i += 0x8000)
          s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
        out.push({tipo: 'b64', valor: btoa(s)});
      } catch (e) {}
    } else if (el.src && el.src.startsWith('http')) {
      out.push({tipo: 'url', valor: el.src});
    }
  }
  return out;
}"""

def _sin_tildes(t):
    return unicodedata.normalize('NFD', t).encode('ascii', 'ignore').decode()


def _parsear_fecha_hisesa(texto):
    """'VIERNES, 1 DE DICIEMBRE DE 2023 A LAS 09:48 A. M.' -> date(2023, 12, 1)"""
    t = _sin_tildes(texto or '').upper()
    m = re.search(r'(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+(\d{4})', t)
    if not m or m.group(2) not in MESES:
        return None
    try:
        return datetime.date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
    except ValueError:
        return None


def _es_pdf(data):
    return bool(data) and len(data) > 1000 and data.startswith(b'%PDF')


class HisesaScraper:
    def __init__(self, usuario, password, etiqueta='HISESA'):
        self.usuario, self.password, self.etiqueta = usuario, password, etiqueta
        self._pw = self.browser = self.context = self.page = None
        self._descargas = []
        self._respuestas = []
        self._urls_probadas = set()
        os.makedirs(config.CARPETA_TEMP, exist_ok=True)

    def _on_download(self, descarga):
        self._descargas.append(descarga)

    def iniciar(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=config.HEADLESS, args=['--no-sandbox', '--disable-dev-shm-usage'])
        self.context = self.browser.new_context(accept_downloads=True)
        self.context.on('page', lambda p: p.on('download', self._on_download))
        self.page = self.context.new_page()
        self.page.set_default_timeout(config.TIMEOUT_MS)

    def cerrar(self):
        for obj in (self.context, self.browser):
            try:
                obj and obj.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()

    def login(self):
        print(f"🔐 Iniciando sesión en HISESA ({self.etiqueta})...")
        self.page.goto(config.HISESA_URL, wait_until='domcontentloaded')

        # La app real vive en un iframe de biofile y solo acepta visitas que vienen de hisesa.com:
        # abrimos su URL directamente, indicando que venimos del portal.
        if not self.page.locator('#TxtUsuario').count():
            # Busca el frame de biofile en cualquier nivel (también frames anidados)
            src = None
            for _ in range(30):
                fr = next((f for f in self.page.frames if 'biofile' in f.url), None)
                if fr:
                    src = fr.url
                    break
                self.page.wait_for_timeout(500)
            if not src:
                print("   URL actual:", self.page.url)
                print("   Frames:", [f.url for f in self.page.frames])
                raise RuntimeError("No apareció el iframe de biofile en el portal")
            self.page.goto(src, wait_until='domcontentloaded', referer=self.page.url)

        self.page.locator('#TxtUsuario').wait_for(timeout=20000)
        self.page.fill('#TxtUsuario', self.usuario)
        self.page.fill('#TxtContrasena', self.password)
        self.page.click('button[onclick*="Loguin"]')
        try:
            self.page.locator("a[onclick*=\"CargarHTML('Examenes')\"]").wait_for(timeout=20000)
        except PWTimeout:
            raise RuntimeError(f"Login HISESA falló ({self.etiqueta})")
        print(f"✅ Sesión iniciada en HISESA ({self.etiqueta})")

    def ir_a_certificados(self):
        self.page.click("a[onclick*=\"CargarHTML('Examenes')\"]")
        self.page.locator('#TxtNumeroIdentificacion').wait_for(timeout=20000)

    def buscar_cedula(self, cedula):
        self.page.evaluate(JS_MARCAR_VIEJOS, LABEL)

        # Borrar la fecha "hasta" (por defecto trae la de hoy)
        self.page.evaluate("""() => {
            const el = document.querySelector('#TxtFechaHasta');
            if (el) { el.value = ''; el.dispatchEvent(new Event('change', {bubbles: true})); }
        }""")
        campo = self.page.locator('#TxtNumeroIdentificacion')
        campo.fill('')
        campo.fill(cedula)
        self.page.click('button[onclick*="CargarExamenes"]')

        try:
            self.page.wait_for_load_state('networkidle', timeout=10000)
        except PWTimeout:
            pass
        self.page.wait_for_timeout(config.HISESA_ESPERA_MS)

        cards = self.page.evaluate(JS_CARDS, LABEL)
        resultados = []
        for card in cards:
            fecha = _parsear_fecha_hisesa(card['fragmento'])
            botones = [m.groups() for m in (RE_BOTON.search(b or '') for b in card['botones']) if m]
            # Descarta botones que no son de esta cédula (resultados viejos)
            botones = [b for b in botones if b[1].startswith(f'{cedula}_')] or (
                [] if card['botones'] else botones)
            if card['botones'] and not botones:
                continue
            preferidos = [b for b in botones if 'CONCEPTO' in _sin_tildes(b[1]).upper()]
            elegido = (preferidos or botones or [None])[0]
            resultados.append({
                'identificador': elegido[0] if elegido else None,   # None = aún sin certificado
                'nombre_doc': elegido[1] if elegido else '',
                'fecha': fecha,
                'texto_fecha': card['fragmento'].replace(LABEL, '').strip(' :\n')[:60],
            })
        return resultados

    def _on_response(self, resp):
        self._respuestas.append(resp)

    def descargar_certificado(self, identificador, cedula):
        boton = self.page.locator(f'button[onclick*="{identificador}"]').first
        self._descargas.clear()
        self._respuestas = []
        self.context.on('response', self._on_response)
        pdf, revisadas = None, 0
        try:
            boton.click()
            for _ in range(40):                                   # hasta ~20 s
                self.page.wait_for_timeout(500)
                pdf, revisadas = self._pdf_de_respuestas(revisadas)
                if not _es_pdf(pdf):
                    pdf = self._pdf_de_visor()
                if not _es_pdf(pdf) and self._descargas:
                    with open(self._descargas[-1].path(), 'rb') as fh:
                        pdf = fh.read()
                if _es_pdf(pdf):
                    break
        finally:
            self.context.remove_listener('response', self._on_response)

        if not _es_pdf(pdf):
            self._diagnostico()
            self.cerrar_visor_popup()
            raise RuntimeError("No se pudo obtener el PDF desde HISESA")

        nombre = re.sub(r'[^0-9A-Za-z_-]', '_', f'{cedula}_{identificador[:12]}')
        ruta = os.path.join(config.CARPETA_TEMP, f'{nombre}.pdf')
        with open(ruta, 'wb') as fh:
            fh.write(pdf)
        self.cerrar_visor_popup()
        return ruta

    def _pdf_de_respuestas(self, desde):
        """Revisa las respuestas de red: PDF directo o PDF en base64 dentro de JSON/texto."""
        nuevas = self._respuestas[desde:]
        for r in nuevas:
            tipo = (r.headers.get('content-type') or '').lower()
            if any(t in tipo for t in ('image', 'font', 'css', 'javascript')):
                continue
            try:
                body = r.body()
            except Exception:
                body = b''
            if not body.startswith(b'%PDF') and 'pdf' in tipo:
                # El visor no deja leer el contenido: pedimos la misma URL con la sesión activa
                try:
                    rr = self.context.request.get(r.url, headers={'Referer': self.page.url})
                    body = rr.body() if rr.ok else b''
                except Exception:
                    body = b''
            if body.startswith(b'%PDF'):
                return body, desde + len(nuevas)
            i = body.find(b'JVBERi')                     # "%PDF" en base64
            if i >= 0:
                m = re.match(rb'[A-Za-z0-9+/=\\]+', body[i:])
                try:
                    data = base64.b64decode(m.group(0).replace(b'\\', b''))
                    if data.startswith(b'%PDF'):
                        return data, desde + len(nuevas)
                except Exception:
                    pass
        return None, desde + len(nuevas)

    def _pdf_de_visor(self):
        """Lee el PDF directamente del iframe del visor."""
        try:
            items = self.page.evaluate(JS_VISOR) or []
        except Exception:
            return None
        for it in items:
            try:
                if it['tipo'] == 'b64':
                    data = base64.b64decode(it['valor'])
                else:
                    if it['valor'] in self._urls_probadas:
                        continue
                    self._urls_probadas.add(it['valor'])
                    r = self.context.request.get(it['valor'])
                    data = r.body() if r.ok else None
                if _es_pdf(data):
                    return data
            except Exception:
                continue
        return None

    def _diagnostico(self):
        print("   [diag] respuestas:",
              [(r.url[:90], r.headers.get('content-type')) for r in self._respuestas][-15:])
        print("   [diag] frames:", [f.url[:90] for f in self.page.frames])
        try:
            print("   [diag] visores:", self.page.evaluate(
                "() => [...document.querySelectorAll('iframe,embed,object')]"
                ".map(e => (e.getAttribute('src') || e.getAttribute('data') || '').slice(0, 90))"))
        except Exception:
            pass

    def cerrar_visor_popup(self):
        for p in self.context.pages[1:]:
            try:
                p.close()
            except Exception:
                pass
        for sel in ('.modal.in .close', '.modal.in [data-dismiss="modal"]',
                    '.ui-dialog-titlebar-close', 'button.close'):
            loc = self.page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.click()
                self.page.wait_for_timeout(500)
                return
        self.page.keyboard.press('Escape')