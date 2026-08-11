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

    # Lo que el usuario lee también vive en atributos: el marcador de posición
    # de un campo se le queda en castellano si solo se tocan los nodos de texto.
    ATRIBUTOS = re.compile(r'\b(placeholder|aria-label|title|alt)="([^"]+)"')

    def nodos(html: str) -> str:
        partes = re.split(r"(<[^>]+>)", html)
        for i, p in enumerate(partes):
            if p.startswith("<"):
                partes[i] = ATRIBUTOS.sub(
                    lambda m: f'{m.group(1)}="{dic[m.group(2)]}"' if m.group(2) in dic else m.group(0),
                    p)
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


# ── Panel de opiniones ───────────────────────────────────────────────────────
# Se inyecta en las nueve páginas al construirlas: un solo sitio donde
# mantenerlo. Trae sus propios estilos con nombres prefijados para no depender
# del CSS de cada página, que es distinto en las tres.
OPINA = {
    "es": {
        "abrir": "¿Qué te ha parecido?", "cerrar": "Cerrar",
        "q": "¿Registrarías una idea tuya antes de ejecutarla?",
        "si": "Sí", "no": "No", "duda": "No lo tengo claro",
        "texto": "¿Qué te ha chirriado? Lo que sea, aunque sea que no le ves sentido.",
        "correo": "Correo (opcional, por si quiero repreguntar)",
        "enviar": "Enviar",
        "aviso": "Esto sí se envía y se guarda, al revés que lo que sellas. No se guarda tu IP.",
        "gracias": "Anotado. Gracias de verdad.",
        "llamada": "¿Te vienes 20 minutos por videollamada a usarlo mientras miro? Es lo que más me sirve con diferencia.",
        "apunto": "Me apunto", "noGracias": "Ahora no",
        "pideCorreo": "Déjame un correo y te escribo.",
        "hecho": "Hecho. Te escribo yo.",
        "fallo": "No se ha podido enviar. ¿Lo intentas otra vez?",
        "vacio": "Marca una opción o escribe algo, lo que prefieras.",
    },
    "en": {
        "abrir": "What did you make of it?", "cerrar": "Close",
        "q": "Would you register an idea of your own before carrying it out?",
        "si": "Yes", "no": "No", "duda": "Not sure",
        "texto": "What jarred? Anything at all, including that you don't see the point.",
        "correo": "Email (optional, in case I want to follow up)",
        "enviar": "Send",
        "aviso": "This is sent and stored, unlike anything you seal. Your IP is not kept.",
        "gracias": "Noted. Genuinely, thank you.",
        "llamada": "Fancy 20 minutes on a call using it while I watch? That is by far the most useful thing.",
        "apunto": "I'm in", "noGracias": "Not now",
        "pideCorreo": "Leave me an email and I'll write.",
        "hecho": "Done. I'll be in touch.",
        "fallo": "It could not be sent. Try again?",
        "vacio": "Pick an option or write something, whichever you prefer.",
    },
    "fr": {
        "abrir": "Qu’en avez-vous pensé ?", "cerrar": "Fermer",
        "q": "Enregistreriez-vous une de vos idées avant de la mener ?",
        "si": "Oui", "no": "Non", "duda": "Je ne sais pas",
        "texto": "Qu’est-ce qui a coincé ? N’importe quoi, y compris que vous n’en voyez pas l’intérêt.",
        "correo": "Courriel (facultatif, au cas où je voudrais relancer)",
        "enviar": "Envoyer",
        "aviso": "Ceci est envoyé et conservé, contrairement à ce que vous scellez. Votre IP n’est pas gardée.",
        "gracias": "Noté. Merci sincèrement.",
        "llamada": "20 minutes en visio pour l’utiliser pendant que je regarde ? C’est de loin ce qui m’aide le plus.",
        "apunto": "Je suis partant", "noGracias": "Pas maintenant",
        "pideCorreo": "Laissez-moi un courriel et je vous écris.",
        "hecho": "C’est fait. Je vous écris.",
        "fallo": "L’envoi a échoué. Vous réessayez ?",
        "vacio": "Cochez une option ou écrivez quelque chose, comme vous préférez.",
    },
}


def panel_opiniones(idioma: str) -> str:
    t = OPINA[idioma]
    return f"""
<div class="op-wrap">
  <button class="op-abrir" type="button" id="op-abrir" aria-expanded="false" aria-controls="op-caja">{t['abrir']}</button>
  <div class="op-caja" id="op-caja" hidden>
    <p class="op-q">{t['q']}</p>
    <div class="op-ops">
      <button class="op-r" type="button" data-r="si">{t['si']}</button>
      <button class="op-r" type="button" data-r="no">{t['no']}</button>
      <button class="op-r" type="button" data-r="duda">{t['duda']}</button>
    </div>
    <label class="op-sr" for="op-texto">{t['texto']}</label>
    <textarea id="op-texto" rows="3" placeholder="{t['texto']}"></textarea>
    <label class="op-sr" for="op-correo">{t['correo']}</label>
    <input type="email" id="op-correo" placeholder="{t['correo']}">
    <p class="op-aviso">{t['aviso']}</p>
    <div class="op-pie">
      <button class="op-enviar" type="button" id="op-enviar">{t['enviar']}</button>
      <span class="op-msg" id="op-msg"></span>
    </div>
  </div>
</div>
<script>
(function () {{
  var T = {json.dumps(t, ensure_ascii=False)};
  var $ = function (i) {{ return document.getElementById(i); }};
  var abrir = $('op-abrir'), caja = $('op-caja'), msg = $('op-msg');
  var elegido = null;

  abrir.addEventListener('click', function () {{
    caja.hidden = !caja.hidden;
    abrir.setAttribute('aria-expanded', caja.hidden ? 'false' : 'true');
    abrir.textContent = caja.hidden ? T.abrir : T.cerrar;
  }});

  [].forEach.call(document.querySelectorAll('.op-r'), function (b) {{
    b.addEventListener('click', function () {{
      elegido = b.getAttribute('data-r');
      [].forEach.call(document.querySelectorAll('.op-r'), function (o) {{
        o.setAttribute('aria-pressed', o === b ? 'true' : 'false');
      }});
    }});
  }});

  function enviar(datos, alTerminar) {{
    fetch('/api/feedback', {{
      method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(datos)
    }}).then(function (r) {{ return r.ok ? r.json() : Promise.reject(); }})
      .then(alTerminar)
      .catch(function () {{ msg.textContent = T.fallo; }});
  }}

  $('op-enviar').addEventListener('click', function () {{
    var texto = $('op-texto').value.trim(), correo = $('op-correo').value.trim();
    if (!elegido && !texto && !correo) {{ msg.textContent = T.vacio; return; }}
    msg.textContent = '…';
    enviar({{ respuesta: elegido, texto: texto, correo: correo, llamada: false,
             pagina: location.pathname, idioma: document.documentElement.lang }},
      function () {{
        // Primero la opinión; la videollamada se propone después, no antes:
        // pedirla de entrada convierte el formulario en una encerrona.
        caja.innerHTML = '';
        var g = document.createElement('p'); g.className = 'op-q'; g.textContent = T.gracias;
        var l = document.createElement('p'); l.className = 'op-llamada'; l.textContent = T.llamada;
        caja.appendChild(g); caja.appendChild(l);

        var fila = document.createElement('div'); fila.className = 'op-pie';
        var si = document.createElement('button'); si.type = 'button';
        si.className = 'op-enviar'; si.textContent = T.apunto;
        var no = document.createElement('button'); no.type = 'button';
        no.className = 'op-abrir'; no.textContent = T.noGracias;
        var aviso = document.createElement('span'); aviso.className = 'op-msg';
        fila.appendChild(si); fila.appendChild(no); fila.appendChild(aviso);
        caja.appendChild(fila);

        no.addEventListener('click', function () {{
          caja.hidden = true; abrir.textContent = T.abrir; abrir.disabled = true;
        }});
        si.addEventListener('click', function () {{
          if (!correo) {{
            var c = document.createElement('input');
            c.type = 'email'; c.placeholder = T.correo; c.id = 'op-correo2';
            caja.insertBefore(c, fila);
            aviso.textContent = T.pideCorreo;
            correo = null;
            si.onclick = function () {{
              var v = c.value.trim();
              if (!v || v.indexOf('@') === -1) {{ aviso.textContent = T.pideCorreo; return; }}
              apuntar(v, aviso);
            }};
            return;
          }}
          apuntar(correo, aviso);
        }});

        function apuntar(dir, donde) {{
          enviar({{ respuesta: elegido, texto: '', correo: dir, llamada: true,
                   pagina: location.pathname, idioma: document.documentElement.lang }},
            function () {{ caja.innerHTML = ''; var h = document.createElement('p');
              h.className = 'op-q'; h.textContent = T.hecho; caja.appendChild(h); }});
        }}
      }});
  }});
}})();
</script>
"""


ESTILO_OPINA = """
<style>
/* Panel de opiniones. Prefijo op- y estilos propios: las tres páginas tienen
   CSS distinto y esto tiene que verse igual en las nueve. */
.op-wrap { border-top: 1px solid #cdcecb; padding: 14px clamp(18px, 6vw, 84px) 34px;
  background: #f0f0ee; font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; }
.op-abrir { background: transparent; border: none; padding: 0; cursor: pointer;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 10px;
  letter-spacing: .12em; text-transform: uppercase; color: #b3202f;
  border-bottom: 1px solid #b3202f; }
.op-abrir:hover { color: #0c1116; border-bottom-color: #0c1116; }
.op-abrir:disabled { color: #8a939b; border-bottom-color: transparent; cursor: default; }
.op-caja { max-width: 620px; margin-top: 16px; }
.op-q { margin: 0 0 10px; font-size: .95rem; font-weight: 700; color: #0c1116; }
.op-llamada { margin: 0 0 12px; font-size: .9rem; color: #4a545d; max-width: 56ch; }
.op-ops { display: flex; flex-wrap: wrap; gap: 0; margin-bottom: 14px; }
.op-r { background: transparent; border: 1px solid #cdcecb; margin-left: -1px;
  padding: 7px 14px; cursor: pointer; font: inherit; font-size: .86rem; color: #4a545d; }
.op-r:first-child { margin-left: 0; }
.op-r:hover { border-color: #b3202f; color: #b3202f; position: relative; z-index: 1; }
.op-r[aria-pressed="true"] { background: #0c1116; border-color: #0c1116; color: #fbfbfa;
  position: relative; z-index: 2; }
.op-caja textarea, .op-caja input { display: block; width: 100%; box-sizing: border-box;
  background: transparent; border: none; border-bottom: 1px solid #d8d9d6; outline: none;
  font: inherit; font-size: .95rem; color: #0c1116; padding: 10px 0; margin-bottom: 4px; }
.op-caja textarea { resize: vertical; }
.op-caja textarea:focus, .op-caja input:focus { border-bottom: 2px solid #b3202f; }
.op-caja ::placeholder { color: #8a939b; }
.op-aviso { margin: 12px 0 0; font-size: .8rem; color: #8a939b; max-width: 56ch; }
.op-pie { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-top: 14px; }
.op-enviar { background: #0c1116; border: 1px solid #0c1116; color: #fbfbfa; cursor: pointer;
  font: inherit; font-size: .82rem; font-weight: 700; padding: 10px 20px; }
.op-enviar:hover { background: #b3202f; border-color: #b3202f; }
.op-msg { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 11px;
  letter-spacing: .08em; color: #4a545d; }
.op-sr { position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip: rect(0 0 0 0); white-space: nowrap; }
*, *::before, *::after { }
</style>
"""


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

    cuerpo = cuerpo.rstrip() + "\n" + panel_opiniones(idioma)

    return (
        f'<!doctype html>\n<html lang="{idioma}">\n<head>\n'
        + cabeza.strip() + ESTILO_OPINA
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
