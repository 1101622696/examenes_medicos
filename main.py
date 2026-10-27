import json
import config
from procesador import ejecutar

if __name__ == '__main__':
    if not config.validar_config():
        raise SystemExit(1)
    resumen = ejecutar()
    print("\n===== RESUMEN =====")
    print(json.dumps(resumen, indent=2, ensure_ascii=False, default=str))