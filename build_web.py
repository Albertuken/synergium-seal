"""Convierte las páginas de web/ en documentos autónomos que sirve este servidor,
y genera la landing en los tres idiomas.

Las fuentes están escritas para publicarse como artefactos de Claude, que
envuelven el fichero en su propio esqueleto: por eso no llevan <!doctype>,
<html>, <head> ni <body>. Aquí se sirven solas, así que hay que ponérselos.

Los enlaces entre páginas se escriben absolutos en la fuente —apuntando al
despliegue actual— para que funcionen también dentro del artefacto. Aquí se
convierten en relativos. Cuando haya dominio propio basta cambiar HOST.

    python3 build_web.py
"""

from pathlib import Path
import json
import re
import sys

RAIZ = Path(__file__).parent
HOST = "https://synergium-seal.fly.dev"

PAGINAS = {}

# La maqueta ya lleva sus tres idiomas dentro; la landing se genera una vez
# por idioma, que es más simple y no deja texto sin traducir a medias.
IDIOMAS = ["es", "en", "fr"]
NOMBRE_IDIOMA = {"es": "ES", "en": "EN", "fr": "FR"}

# Cada página conoce sus propias rutas por idioma: el selector tiene que
# llevarte a la misma página en otro idioma, no siempre a la landing.
RUTAS = {
    "index.html":       {"es": "/proyecto", "en": "/proyecto/en", "fr": "/proyecto/fr"},
    "herramienta.html": {"es": "/", "en": "/en", "fr": "/fr"},
    "app.html":         {"es": "/app", "en": "/app/en", "fr": "/app/fr"},
}
SALIDAS = {
    "index.html":       {"es": "proyecto.html", "en": "proyecto.en.html", "fr": "proyecto.fr.html"},
    "herramienta.html": {"es": "herramienta.html", "en": "herramienta.en.html", "fr": "herramienta.fr.html"},
    "app.html":         {"es": "app.html", "en": "app.en.html", "fr": "app.fr.html"},
}

# El artefacto necesita este apaño porque no controla su <head>. Aquí sí.
# Se busca por lo que hace el bloque, no por cómo esté comentado: las dos
# fuentes lo escriben distinto y buscar la forma dejó una sin limpiar.
APANO_VIEWPORT = re.compile(
    r'<script>(?:(?!</script>).)*?meta\[name="viewport"\](?:(?!</script>).)*?</script>\s*\n',
    re.DOTALL,
)


def traducir(doc: str, dic: dict) -> str:
    """Sustituye texto por texto, nunca por coincidencia parcial.

    Reemplazar cadenas sueltas sería un error: la clave «Estado» aparece dentro
    de «tres Estados» y de media docena de frases más. Se recorre el documento
    separando etiquetas de texto y solo se cambia un nodo cuando coincide
    entero. Dentro del <script> se cambian los literales entrecomillados, que
    tampoco pueden confundirse con otra cosa.
    """
    def literales(js: str) -> str:
        def cambia(m):
            interior = m.group(1)
            if interior not in dic:
                return m.group(0)
            # Escapar es obligatorio: «observers' calibration notebook» cierra
            # el literal antes de tiempo y el script entero deja de cargar.
            return "'" + dic[interior].replace("\\", "\\\\").replace("'", "\\'") + "'"
        return re.sub(r"'((?:[^'\\]|\\.)*)'", cambia, js)

    def nodos(html: str) -> str:
        partes = re.split(r"(<[^>]+>)", html)
        for i, p in enumerate(partes):
            if p.startswith("<"):
                continue
            nucleo = p.strip()
            if nucleo in dic:
                partes[i] = p.replace(nucleo, dic[nucleo])
        return "".join(partes)

    # Los <script> se apartan ANTES de trocear por etiquetas. Si no, un
    # `i < 64` del propio código parece una etiqueta abierta, el troceado se
    # descuadra y el script se queda entero sin traducir —que es justo lo que
    # pasó la primera vez—.
    salida, resto = [], doc
    patron = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)", re.DOTALL | re.IGNORECASE)
    pos = 0
    for m in patron.finditer(doc):
        salida.append(nodos(doc[pos:m.start()]))
        salida.append(m.group(1) + literales(m.group(2)) + m.group(3))
        pos = m.end()
    salida.append(nodos(doc[pos:]))
    return "".join(salida)


def selector_idiomas(pagina: str, actual: str) -> str:
    piezas = []
    for c in IDIOMAS:
        clase = ' class="on"' if c == actual else ""
        piezas.append(f'<a href="{RUTAS[pagina][c]}"{clase}>{NOMBRE_IDIOMA[c]}</a>')
    return '<span class="langs" aria-label="Idioma">' + "".join(piezas) + "</span>"


def aviso_de_idioma(pagina: str, actual: str) -> str:
    """Una línea discreta si el navegador está en otro idioma.

    No redirige: quien comparte el enlace debe poder fiarse de que el otro ve
    lo mismo que él. Solo avisa de que existe su versión.
    """
    otros = {c: RUTAS[pagina][c] for c in IDIOMAS if c != actual}
    textos = {"es": "Esta página también está en español",
              "en": "This page is also available in English",
              "fr": "Cette page existe aussi en français"}
    return (
        '<div class="lang-hint" id="lang-hint" hidden><a id="lang-hint-a" href="#"></a></div>\n'
        "<script>(function(){"
        f"var otros={json.dumps(otros)},textos={json.dumps(textos)};"
        "var n=(navigator.language||'').slice(0,2).toLowerCase();"
        "if(!otros[n])return;"
        "var a=document.getElementById('lang-hint-a');"
        "a.href=otros[n];a.textContent=textos[n]+' →';"
        "document.getElementById('lang-hint').hidden=false;"
        "})();</script>\n"
    )


def construir(fuente: str, nombre: str, idioma: str = "es") -> str:
    doc = APANO_VIEWPORT.sub("", fuente)

    # Servidas desde el mismo host, los enlaces entre páginas son internos.
    doc = re.sub(rf'href="{re.escape(HOST)}(/[^"]*)?"',
                 lambda m: f'href="{m.group(1) or "/"}"', doc)
    # …y sin target="_blank", que dentro del propio sitio solo estorba.
    doc = re.sub(r'(href="/[^"]*")\s+target="_blank"\s+rel="noopener"', r"\1", doc)

    sueltos = re.findall(rf'href="https?://{re.escape(HOST.split("//")[1])}[^"]*"', doc)
    if sueltos:
        sys.exit(f"{nombre}: quedan {len(sueltos)} enlaces absolutos sin convertir: {sueltos}")

    if idioma != "es":
        if nombre == "app.html":
            # La maqueta ya trae su interfaz en los tres idiomas: aquí solo se
            # traducen los DATOS de ejemplo, y solo dentro de su zona. Tocar el
            # fichero entero reescribiría los diccionarios de la interfaz.
            dic = json.loads((RAIZ / "web" / "i18n-app.json").read_text(encoding="utf-8"))[idioma]
            ini = doc.index("var ideas = [")
            fin = doc.index("  /* ---------- Helpers", ini)
            # El fragmento es JavaScript puro: se envuelve para que traducir()
            # lo trate como literales y no como nodos de texto HTML.
            trozo = traducir("<script>" + doc[ini:fin] + "</script>", dic)
            trozo = trozo[len("<script>"):-len("</script>")]
            doc = doc[:ini] + trozo + doc[fin:]
            doc = doc.replace("var uiLang = 'es';", f"var uiLang = '{idioma}';", 1)
        else:
            dic = json.loads((RAIZ / "web" / "i18n.json").read_text(encoding="utf-8"))[idioma]
            doc = traducir(doc, dic)

    # La cabecera acaba donde empieza el cuerpo, y el cuerpo de las tres
    # fuentes empieza por <header>. Cortar por </style> fallaba con la
    # herramienta, que lleva el CSS en un fichero aparte y no tiene <style>.
    if "<header" not in doc:
        sys.exit(f"{nombre}: no encuentro dónde empieza el cuerpo")
    corte = doc.index("<header")
    cabeza, cuerpo = doc[:corte], doc[corte:]

    if "<body" in cabeza:
        sys.exit(f"{nombre}: el corte de la cabecera se ha llevado contenido del cuerpo")
    if "<style" in cuerpo:
        sys.exit(f"{nombre}: ha quedado CSS fuera de la cabecera")

    # Selector de idioma y aviso, solo en las versiones servidas: el artefacto
    # de Claude no tiene las otras rutas y quedarían rotas.
    if nombre in RUTAS and nombre != "app.html":
        cierre = "</nav>" if "</nav>" in cuerpo else "</div>"
        cuerpo = cuerpo.replace(cierre, selector_idiomas(nombre, idioma) + cierre, 1)
        cuerpo = aviso_de_idioma(nombre, idioma) + cuerpo
        if nombre == "herramienta.html" and idioma != "es":
            cuerpo = cuerpo.replace("/static/app.js", f"/static/app.{idioma}.js")

    return (
        f'<!doctype html>\n<html lang="{idioma}">\n<head>\n'
        + cabeza.strip()
        + "\n</head>\n<body>\n"
        + cuerpo.strip()
        + "\n</body>\n</html>\n"
    )


if __name__ == "__main__":
    for origen, destino in PAGINAS.items():
        fuente = (RAIZ / "web" / origen).read_text(encoding="utf-8")
        salida = construir(fuente, origen)
        (RAIZ / "static" / destino).write_text(salida, encoding="utf-8")
        print(f"web/{origen}  →  static/{destino}  ({len(salida):,} bytes)")

    for pagina in RUTAS:
        fuente = (RAIZ / "web" / pagina).read_text(encoding="utf-8")
        for idioma in IDIOMAS:
            destino = SALIDAS[pagina][idioma]
            salida = construir(fuente, pagina, idioma)
            (RAIZ / "static" / destino).write_text(salida, encoding="utf-8")
            print(f"web/{pagina} [{idioma}]  →  static/{destino}  ({len(salida):,} bytes)")

    # El JavaScript de la herramienta lleva los mensajes dentro, así que se
    # genera una copia por idioma. Es la misma sustitución de literales.
    js = (RAIZ / "static" / "app.js").read_text(encoding="utf-8")
    for idioma in IDIOMAS:
        if idioma == "es":
            continue
        dic = json.loads((RAIZ / "web" / "i18n.json").read_text(encoding="utf-8"))[idioma]
        salida = traducir("<script>" + js + "</script>", dic)[len("<script>"):-len("</script>")]
        (RAIZ / "static" / f"app.{idioma}.js").write_text(salida, encoding="utf-8")
        print(f"static/app.js [{idioma}]  →  static/app.{idioma}.js  ({len(salida):,} bytes)")
