"""Utilidades compartidas por los scrapers nuevos (ICSA, SIMETRIC) para obtener un PDF
desde un visor emergente: respuestas de red, iframes/embed (blob:, data:, URL) o descarga."""
import base64
import datetime
import re
import unicodedata

MESES_NUM = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4})')
ISO = re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})')


def sin_tildes(t):
    return unicodedata.normalize('NFD', str(t or '')).encode('ascii', 'ignore').decode()


def norm(t):
    return ' '.join(sin_tildes(t).upper().split())


def solo_digitos(t):
    return re.sub(r'\D', '', str(t or ''))


def parsear_fecha(texto):
    """'2026-11-05', '2026-11-05 10:20' o '05/11/2026' -> date. None si no se puede."""
    t = str(texto or '')
    m = ISO.search(t)
    try:
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = MESES_NUM.search(t)
        if m:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    return None


def es_pdf(data):
    return bool(data) and len(data) > 1000 and data[:5] == b'%PDF-'


# Lee el PDF que muestran los iframes/embed/object de una página (blob:, data: o URL normal)
JS_VISOR = """async () => {
  const out = [];
  const els = [...document.querySelectorAll('iframe, embed, object, a[href]')];
  for (const el of els) {
    const src = el.getAttribute('src') || el.getAttribute('data') ||
                (el.tagName === 'A' ? el.getAttribute('href') : '') || '';
    if (!src || src === 'about:blank' || src.startsWith('javascript')) continue;
    if (el.tagName === 'A' && !/\\.pdf|download|descarg|blob:|data:/i.test(src + ' ' + (el.textContent || ''))) continue;
    if (src.startsWith('blob:') || src.startsWith('data:')) {
      try {
        const b = new Uint8Array(await (await fetch(src)).arrayBuffer());
        let s = '';
        for (let i = 0; i < b.length; i += 0x8000)
          s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
        out.push({tipo: 'b64', valor: btoa(s)});
      } catch (e) {}
    } else {
      try { out.push({tipo: 'url', valor: new URL(src, location.href).href}); } catch (e) {}
    }
  }
  return out;
}"""


def pdf_de_respuestas(respuestas, context, referer=None):
    """Busca un PDF entre respuestas de red: directo, o en base64 dentro de JSON/texto."""
    for r in respuestas:
        tipo = (r.headers.get('content-type') or '').lower()
        if any(t in tipo for t in ('image', 'font', 'css', 'javascript')):
            continue
        try:
            body = r.body()
        except Exception:
            body = b''
        if not body.startswith(b'%PDF') and ('pdf' in tipo or r.url.lower().split('?')[0].endswith('.pdf')):
            try:
                rr = context.request.get(r.url, headers={'Referer': referer} if referer else None)
                body = rr.body() if rr.ok else b''
            except Exception:
                body = b''
        if es_pdf(body):
            return body
        i = body.find(b'JVBERi')                     # "%PDF" en base64
        if i >= 0:
            m = re.match(rb'[A-Za-z0-9+/=\\]+', body[i:])
            try:
                data = base64.b64decode(m.group(0).replace(b'\\', b''))
                if es_pdf(data):
                    return data
            except Exception:
                pass
    return None


def pdf_de_visor(pagina, context, probadas):
    """Lee el PDF desde los iframes/embed/enlaces de la página (y sus frames)."""
    items = []
    for fr in [pagina.main_frame] + [f for f in pagina.frames if f != pagina.main_frame]:
        try:
            items += fr.evaluate(JS_VISOR) or []
        except Exception:
            continue
    for it in items:
        try:
            if it['tipo'] == 'b64':
                data = base64.b64decode(it['valor'])
            else:
                if it['valor'] in probadas:
                    continue
                probadas.add(it['valor'])
                r = context.request.get(it['valor'], headers={'Referer': pagina.url})
                data = r.body() if r.ok else None
            if es_pdf(data):
                return data
        except Exception:
            continue
    return None
