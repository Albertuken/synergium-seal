"""Convierte las páginas de web/ en documentos autónomos que sirve este servidor.

Las fuentes están escritas para publicarse como artefactos de Claude, que
envuelven el fichero en su propio esqueleto: por eso no llevan <!doctype>,
<html>, <head> ni <body>. Aquí se sirven solas, así que hay que ponérselos.

Y los enlaces entre páginas se escriben absolutos en la fuente —apuntando al
despliegue actual— para que funcionen también dentro del artefacto. Aquí se
convierten en relativos. Cuando haya dominio propio basta cambiar HOST.

    python3 build_web.py
"""

from pathlib import Path
import re
import sys

RAIZ = Path(__file__).parent
HOST = "https://synergium-seal.fly.dev"

PAGINAS = {
    "index.html": "proyecto.html",   # la landing   → /proyecto
    "app.html": "app.html",          # la maqueta   → /app
}

# El artefacto necesita este apaño porque no controla su <head>. Aquí sí.
# Se busca por lo que hace el bloque, no por cómo esté comentado: las dos
# fuentes lo escriben distinto y buscar la forma dejó una sin limpiar.
APANO_VIEWPORT = re.compile(
    r'<script>(?:(?!</script>).)*?meta\[name="viewport"\](?:(?!</script>).)*?</script>\s*\n',
    re.DOTALL,
)


def construir(fuente: str, nombre: str) -> str:
    doc = APANO_VIEWPORT.sub("", fuente)

    # Servidas desde el mismo host, los enlaces entre páginas son internos.
    doc = re.sub(rf'href="{re.escape(HOST)}(/[^"]*)?"', lambda m: f'href="{m.group(1) or "/"}"', doc)
    # …y sin target="_blank", que dentro del propio sitio solo estorba.
    doc = re.sub(r'(href="/[^"]*")\s+target="_blank"\s+rel="noopener"', r"\1", doc)

    sueltos = re.findall(rf'href="https?://{re.escape(HOST.split("//")[1])}[^"]*"', doc)
    if sueltos:
        sys.exit(f"{nombre}: quedan {len(sueltos)} enlaces absolutos sin convertir: {sueltos}")

    if "</style>" not in doc:
        sys.exit(f"{nombre}: no encuentro dónde acaba la cabecera")
    corte = doc.index("</style>") + len("</style>")
    cabeza, cuerpo = doc[:corte], doc[corte:]

    if "<body" in cabeza or "<header" in cabeza:
        sys.exit(f"{nombre}: el corte de la cabecera se ha llevado contenido del cuerpo")

    return (
        '<!doctype html>\n<html lang="es">\n<head>\n'
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
