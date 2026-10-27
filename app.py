import hmac
import threading
import time
import traceback
import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import config
from procesador import ejecutar

app = FastAPI()
_lock = threading.Lock()


async def _token(request: Request):
    token = request.headers.get('X-Token', '')
    if not token:
        try:
            token = (await request.json()).get('token', '')
        except Exception:
            token = ''
    return token or ''


@app.get('/health')
def health():
    return {'ok': True, 'ocupado': _lock.locked()}


@app.post('/procesar')
async def procesar(request: Request):
    token = await _token(request)
    if not config.TOKEN_PROCESO_PYTHON or not hmac.compare_digest(token, config.TOKEN_PROCESO_PYTHON):
        return JSONResponse({'ok': False, 'error': 'No autorizado'}, status_code=401)
    if not config.validar_config():
        return JSONResponse({'ok': False, 'error': 'Configuración incompleta'}, status_code=500)
    if not _lock.acquire(blocking=False):
        return JSONResponse({'ok': False, 'error': 'Ya hay una revisión en curso'}, status_code=409)
    threading.Thread(target=_trabajo, daemon=True).start()
    return JSONResponse({'ok': True, 'mensaje': 'Revisión iniciada'}, status_code=202)

def _keepalive(stop):
    """Evita que Render (plan free) apague el servicio a mitad de la revisión."""
    url = os.getenv('RENDER_EXTERNAL_URL')
    while url and not stop.wait(240):
        try:
            requests.get(f'{url}/health', timeout=10)
        except Exception:
            pass


def _trabajo():
    stop = threading.Event()
    threading.Thread(target=_keepalive, args=(stop,), daemon=True).start()
    resumen = {'cargados': []}
    try:
        ejecutar(resumen)
        payload = {'ok': True, **resumen}
    except Exception as e:
        traceback.print_exc()
        payload = {'ok': False, 'error': str(e), **resumen}
    finally:
        stop.set()
        _lock.release()
    _notificar_apps_script(payload)


def _notificar_apps_script(payload):
    body = {'token': config.TOKEN_PROCESO_PYTHON, 'accion': 'resultado_cargue_examenes',
            'usuario': config.USUARIO_CARGA, **payload}
    for intento in range(3):
        try:
            r = requests.post(config.URL_WEBAPP, json=body, timeout=330)
            if r.ok:
                print(f"📨 Resultado enviado a Apps Script ({len(payload.get('cargados', []))} cargados)")
                return
            print(f"⚠️ Apps Script respondió {r.status_code}")
        except Exception as e:
            print(f"⚠️ Error enviando a Apps Script: {e}")
        time.sleep(15)