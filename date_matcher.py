"""
Lógica compartida para elegir, entre varios certificados encontrados en una
plataforma de IPS, el que mejor corresponde a la fecha de examen registrada
en la hoja de cálculo (columna E de Pendientes_Clasificar).

Se usa igual en atis_scraper.py, zonamedica_scraper.py y cualquier scraper
de una IPS nueva que se agregue después.
"""


def elegir_mejor_resultado(resultados, fecha_examen_sheet):
    """
    resultados: lista de dicts, cada uno debe tener al menos la clave 'fecha'
                (objeto datetime.date) con el resto de claves libres
                (sufijo, texto_fecha, numero_certificado, url_descarga, etc.)
    fecha_examen_sheet: datetime.date de la columna E del sheet

    Elige el resultado cuya 'fecha' esté más cerca de fecha_examen_sheet.
    En caso de empate, se toma el más reciente.

    Devuelve (resultado_elegido, diferencia_dias) o (None, None) si no hay
    candidatos con fecha válida.
    """
    candidatos = [r for r in resultados if r.get('fecha') is not None]
    if not candidatos:
        return None, None

    def clave(r):
        diff = abs((r['fecha'] - fecha_examen_sheet).days)
        return (diff, -r['fecha'].toordinal())

    candidatos.sort(key=clave)
    mejor = candidatos[0]
    diferencia = abs((mejor['fecha'] - fecha_examen_sheet).days)
    return mejor, diferencia