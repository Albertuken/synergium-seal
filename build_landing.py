"""Convierte la landing en una página autónoma servible por este mismo servidor.

La fuente (`landing/index.html`) está escrita para publicarse como artefacto de
Claude, que envuelve el fichero en su propio esqueleto: por eso no lleva
<!doctype>, <html>, <head> ni <body>. Aquí se sirve sola, así que hay que
ponérselos.

Y los enlaces a la herramienta pasan de absolutos a relativos: cuando el dominio
propio esté puesto, la página seguirá funcionando sin tocar una línea.

    python3 build_landing.py
"""

from pathlib import Path
import re
import sys

RAIZ = Path(__file__).parent
FUENTE = RAIZ / "landing" / "index.html"
DESTINO = RAIZ / "static" / "proyecto.html"

# El artefacto necesita este apaño porque no controla su <head>. Aquí sí.
APANO_VIEWPORT = re.compile(
    r"<script>\s*\n\s*/\* Sin viewport.*?</script>\s*\n", re.DOTALL
)


def construir(fuente: str) -> str:
    doc = APANO_VIEWPORT.sub("", fuente)

    # Servida desde el mismo host que la herramienta, el enlace es interno:
    # ni salto de dominio ni pestaña nueva.
    doc = doc.replace(
        ' href="https://synergium-seal.fly.dev" target="_blank" rel="noopener"',
        ' href="/"',
    )
    # Solo enlaces: el nombre también aparece en un comentario del CSS.
    sueltos = re.findall(r'href="https?://synergium-seal\.fly\.dev[^"]*"', doc)
    if sueltos:
        sys.exit(f"quedan {len(sueltos)} enlaces absolutos a fly.dev: {sueltos}")

    corte = doc.index("</style>") + len("</style>")
    cabeza, cuerpo = doc[:corte], doc[corte:]

    return (
        "<!doctype html>\n<html lang=\"es\">\n<head>\n"
        + cabeza.strip()
        + "\n</head>\n<body>\n"
        + cuerpo.strip()
        + "\n</body>\n</html>\n"
    )


if __name__ == "__main__":
    salida = construir(FUENTE.read_text(encoding="utf-8"))
    DESTINO.write_text(salida, encoding="utf-8")
    print(f"{DESTINO.relative_to(RAIZ)} — {len(salida)} bytes")
