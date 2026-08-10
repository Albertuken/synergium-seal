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

PAGINAS = {
    "index.html": "proyecto.html",   # la landing   → /proyecto
    "app.html": "app.html",          # la maqueta   → /app
}

# La maqueta ya lleva sus tres idiomas dentro; la landing se genera una vez
# por idioma, que es más simple y no deja texto sin traducir a medias.
IDIOMAS = {"es": None, "en": "proyecto.en.html", "fr": "proyecto.fr.html"}
NOMBRE_IDIOMA = {"es": "ES", "en": "EN", "fr": "FR"}
RUTA_IDIOMA = {"es": "/proyecto", "en": "/proyecto/en", "fr": "/proyecto/fr"}

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
            return "'" + dic[interior] + "'" if interior in dic else m.group(0)
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


def selector_idiomas(actual: str) -> str:
    piezas = []
    for c in IDIOMAS:
        clase = ' class="on"' if c == actual else ""
        piezas.append(f'<a href="{RUTA_IDIOMA[c]}"{clase}>{NOMBRE_IDIOMA[c]}</a>')
    return '<span class="langs" aria-label="Idioma">' + "".join(piezas) + "</span>"


def aviso_de_idioma(actual: str) -> str:
    """Una línea discreta si el navegador está en otro idioma.

    No redirige: quien comparte el enlace debe poder fiarse de que el otro ve
    lo mismo que él. Solo avisa de que existe su versión.
    """
    otros = {c: RUTA_IDIOMA[c] for c in IDIOMAS if c != actual}
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
        dic = json.loads((RAIZ / "web" / "i18n.json").read_text(encoding="utf-8"))[idioma]
        doc = traducir(doc, dic)

    if "</style>" not in doc:
        sys.exit(f"{nombre}: no encuentro dónde acaba la cabecera")
    corte = doc.index("</style>") + len("</style>")
    cabeza, cuerpo = doc[:corte], doc[corte:]

    if "<body" in cabeza or "<header" in cabeza:
        sys.exit(f"{nombre}: el corte de la cabecera se ha llevado contenido del cuerpo")

    # Selector de idioma y aviso, solo en las versiones servidas: el artefacto
    # de Claude no tiene las otras rutas y quedarían rotas.
    if nombre == "index.html":
        cuerpo = cuerpo.replace("</nav>", selector_idiomas(idioma) + "</nav>", 1)
        cuerpo = aviso_de_idioma(idioma) + cuerpo

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

    fuente = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")
    for idioma, destino in IDIOMAS.items():
        if destino is None:
            continue
        salida = construir(fuente, "index.html", idioma)
        (RAIZ / "static" / destino).write_text(salida, encoding="utf-8")
        restos = len(re.findall(r"[áéíóúñ¿¡]", re.sub(r"<style>.*?</style>", "", salida, flags=re.DOTALL)))
        print(f"web/index.html [{idioma}]  →  static/{destino}  ({len(salida):,} bytes)")
