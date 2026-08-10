"""
Comprobación de que ninguna página se sale por el lado.

El desbordamiento lateral se ha colado dos veces por el mismo motivo: una
pista de rejilla declarada `1fr` toma como mínimo el min-content de lo que
contiene, así que un <pre> que no parte línea, o unos segmentos que no
envuelven, estiran la columna y arrastran la página entera. En un móvil eso
se nota enseguida y leyendo el CSS no se ve.

Se mide sobre el render real, no sobre el código. Cada página se carga en un
iframe de ancho fijo —un iframe ignora el meta viewport, así que maqueta
exactamente a los píxeles que le des— y se compara scrollWidth con
clientWidth. Un solo arranque de Chrome mide todas las combinaciones.

La prueba comprueba además su propia sensibilidad: incluye una página que
desborda a propósito y exige verla desbordar. Sin eso, una sonda rota daría
todo correcto y no nos enteraríamos.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ANCHOS = [375, 768, 1280]      # móvil, tableta, escritorio

CHROME_CANDIDATOS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
]


def buscar_chrome():
    for c in CHROME_CANDIDATOS:
        if Path(c).exists():
            return c
        hallado = shutil.which(c)
        if hallado:
            return hallado
    return None


def url_de(ruta: Path) -> str:
    return "file://" + urllib.parse.quote(str(ruta))


def paginas_a_medir(tmp: Path):
    """Las tres páginas tal como se sirven, en ficheros autónomos.

    Las dos estáticas salen de build_web.py. La herramienta la renderiza
    Flask, así que se pide por el cliente de pruebas y se le reescriben las
    rutas /static/ para que funcionen desde file://.
    """
    subprocess.run([sys.executable, str(RAIZ / "build_web.py")], cwd=RAIZ, check=True,
                   capture_output=True)

    paginas = {
        "proyecto": RAIZ / "static" / "proyecto.html",
        "proyecto-en": RAIZ / "static" / "proyecto.en.html",
        "proyecto-fr": RAIZ / "static" / "proyecto.fr.html",
        "maqueta": RAIZ / "static" / "app.html",
    }

    # La herramienta también es estática ya; solo hay que darle rutas
    # absolutas al CSS y al JS para que carguen desde file://.
    estatico = url_de(RAIZ / "static")
    for idi, fichero in (("es", "herramienta.html"), ("en", "herramienta.en.html"),
                         ("fr", "herramienta.fr.html")):
        html = (RAIZ / "static" / fichero).read_text(encoding="utf-8")
        html = html.replace('href="/static/', f'href="{estatico}/').replace(
            'src="/static/', f'src="{estatico}/')
        copia = tmp / fichero
        copia.write_text(html, encoding="utf-8")
        paginas["herramienta" if idi == "es" else f"herramienta-{idi}"] = copia

    # El canario: desborda a propósito, y la sonda tiene que verlo.
    canario = tmp / "canario.html"
    canario.write_text(
        '<meta charset="utf-8"><style>body{margin:0}'
        '.x{display:grid;grid-template-columns:1fr}'
        'pre{margin:0}</style><div class="x"><pre>'
        + "x" * 400 + "</pre></div>",
        encoding="utf-8")
    paginas["canario"] = canario
    return paginas


PLANTILLA = """<meta charset="utf-8">
<style>body{margin:0}iframe{border:0;display:block;height:1400px}</style>
<div id="out">pendiente</div>
<script>
var CASOS = __CASOS__;
var hechos = [], salida = {};
CASOS.forEach(function (c) {
  var f = document.createElement('iframe');
  f.style.width = c.ancho + 'px';
  f.src = c.url;
  f.addEventListener('load', function () {
    hechos.push(c);
    if (hechos.length === CASOS.length) setTimeout(medir, 3000);
  });
  document.body.appendChild(f);
  c.nodo = f;
});
function medir() {
  CASOS.forEach(function (c) {
    var d = c.nodo.contentDocument.documentElement;
    salida[c.nombre + '@' + c.ancho] = {
      viewport: d.clientWidth,
      desborde: d.scrollWidth - d.clientWidth
    };
  });
  // El marcador se compone para que no aparezca literal en este script y
  // --dump-dom no lo devuelva dos veces.
  document.getElementById('out').textContent =
    'MED' + 'IDA' + JSON.stringify(salida) + 'F' + 'IN';
}
</script>
"""


@pytest.fixture(scope="module")
def medidas():
    chrome = buscar_chrome()
    if not chrome:
        pytest.skip("no hay Chrome ni Chromium para medir el render")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        paginas = paginas_a_medir(tmp)
        casos = [{"nombre": n, "ancho": a, "url": url_de(Path(p))}
                 for n, p in paginas.items() for a in ANCHOS]

        envoltorio = tmp / "sonda.html"
        envoltorio.write_text(PLANTILLA.replace("__CASOS__", json.dumps(casos)),
                              encoding="utf-8")

        res = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--allow-file-access-from-files", "--virtual-time-budget=30000",
             "--dump-dom", url_de(envoltorio)],
            capture_output=True, text=True, timeout=180)

        m = re.search(r"MEDIDA(\{.*?\})FIN", res.stdout, re.DOTALL)
        assert m, "la sonda no devolvió medidas; salida de Chrome:\n" + res.stdout[:800]
        return json.loads(m.group(1))


def test_la_sonda_detecta_desbordamiento(medidas):
    """Si el canario no desborda, la sonda no vale y el resto es humo."""
    for ancho in ANCHOS:
        clave = f"canario@{ancho}"
        assert medidas[clave]["desborde"] > 0, (
            f"la sonda no ve desbordar al canario en {ancho}px: no es de fiar")


@pytest.mark.parametrize("pagina", ["proyecto", "proyecto-en", "proyecto-fr",
                                    "herramienta", "herramienta-en", "herramienta-fr",
                                    "maqueta"])
@pytest.mark.parametrize("ancho", ANCHOS)
def test_sin_desbordamiento_lateral(medidas, pagina, ancho):
    m = medidas[f"{pagina}@{ancho}"]
    assert m["viewport"] == ancho, f"el iframe no maquetó a {ancho}px sino a {m['viewport']}"
    assert m["desborde"] == 0, (
        f"{pagina} se sale {m['desborde']}px por el lado a {ancho}px de ancho. "
        "Suele ser una pista de rejilla `1fr` que debería ser `minmax(0, 1fr)`, "
        "o un hijo sin min-width: 0.")
