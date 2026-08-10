"""
Servicio de sellado de Synergium.

El cliente calcula la huella en su propio navegador y solo envía eso.
El contenido nunca llega hasta aquí, ni siquiera de paso.
"""

import io
import os
from datetime import datetime, timezone

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
)

import db
import seal

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024  # nada grande debería llegar nunca


@app.before_request
def _ensure_db():
    if not getattr(app, "_db_ready", False):
        db.init()
        app._db_ready = True


def _public(row: dict) -> dict:
    """Proyección de un sello para el exterior. Nunca expone el blob binario."""
    heights = row.get("heights")
    return {
        "id": row["id"],
        "digest": row["digest"],
        "label": row.get("label"),
        "created_at": row["created_at"],
        "status": row["status"],
        "anchored_at": row.get("anchored_at"),
        "bitcoin_heights": [int(h) for h in heights.split(",")] if heights else [],
    }


@app.get("/")
def index():
    return render_template("index.html")


PAGINAS_IDIOMA = {"es": "proyecto.html", "en": "proyecto.en.html", "fr": "proyecto.fr.html"}


@app.get("/proyecto")
def proyecto():
    """La página del proyecto, en castellano."""
    return send_from_directory(app.static_folder, PAGINAS_IDIOMA["es"])


@app.get("/proyecto/<idioma>")
def proyecto_idioma(idioma: str):
    """La misma página en otro idioma.

    Una página por idioma en vez de un diccionario en el navegador: así no hay
    parpadeo de texto sin traducir y cada versión se puede compartir por su
    propia dirección.
    """
    fichero = PAGINAS_IDIOMA.get(idioma)
    if not fichero:
        return redirect("/proyecto")
    return send_from_directory(app.static_folder, fichero)


@app.get("/app")
def maqueta():
    """La maqueta navegable de la aplicación. Datos simulados, sin servidor."""
    return send_from_directory(app.static_folder, "app.html")


# Las dos salen de build_web.py a partir de web/*.html. Se sirven con
# send_from_directory y no con render_template a propósito: son HTML literal
# y no tienen por qué pasar por Jinja.


@app.get("/health")
def health():
    """Estado del servicio.

    Incluye cuándo corrió por última vez la tarea de anclaje: si esa marca se
    queda atrasada, es que la tarea se paró. Sin esto, pararse es invisible.
    """
    last_run = db.get_meta("last_upgrade_run")
    stale = True
    if last_run:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(last_run)).total_seconds()
            stale = age > 6 * 3600  # se espera cada 2 h; a las 6 h algo va mal
        except ValueError:
            pass
    return jsonify({
        "ok": True,
        "stamps": db.counts(),
        "upgrade_last_run": last_run,
        "upgrade_last_stats": db.get_meta("last_upgrade_stats"),
        "upgrade_stale": stale,
    })


@app.post("/api/seal")
def create_seal():
    payload = request.get_json(silent=True) or {}

    # Rechazo explícito: si alguien intenta mandarnos el contenido, no lo queremos.
    if "content" in payload or "text" in payload or "file" in payload:
        return jsonify({
            "error": "Este servicio no acepta contenido. Calcula la huella SHA-256 "
                     "en tu equipo y envía solo la huella."
        }), 400

    try:
        digest = seal.normalise_digest(payload.get("hash", ""))
    except seal.SealError as exc:
        return jsonify({"error": str(exc)}), 400

    label = (payload.get("label") or "").strip()[:200] or None

    try:
        ots = seal.stamp(digest)
    except seal.SealError as exc:
        # 503: el fallo es de los calendarios, no de la petición. Reintentar sirve.
        return jsonify({"error": str(exc)}), 503

    row = db.insert_stamp(digest.hex(), label, ots)
    row["bitcoin_heights"] = []
    row["anchored_at"] = None
    return jsonify(row), 201


@app.get("/api/stamp/<stamp_id>")
def read_stamp(stamp_id):
    row = db.get_stamp(stamp_id)
    if not row:
        return jsonify({"error": "No existe ningún sello con ese identificador."}), 404
    out = _public(row)
    # Una prueba ilegible (disco, migración mal hecha) no debe tumbar la ficha:
    # los metadatos siguen siendo útiles y el problema hay que poder verlo.
    try:
        out["proof_status"] = seal.inspect(row["ots"]).status
    except seal.SealError:
        out["proof_status"] = "unreadable"
    return jsonify(out)


@app.get("/api/stamp/<stamp_id>/proof")
def download_proof(stamp_id):
    """Descarga el .ots. Es lo que hace la prueba independiente de nosotros."""
    row = db.get_stamp(stamp_id)
    if not row:
        return jsonify({"error": "No existe ningún sello con ese identificador."}), 404
    return send_file(
        io.BytesIO(row["ots"]),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=f"{row['id']}.ots",
    )


@app.post("/api/verify")
def verify():
    """Comprueba si una huella tiene sello registrado aquí.

    No es la verificación fuerte: esa se hace con el fichero .ots contra la
    cadena de Bitcoin, sin pasar por este servidor. La respuesta lo recuerda.
    """
    payload = request.get_json(silent=True) or {}
    try:
        digest = seal.normalise_digest(payload.get("hash", ""))
    except seal.SealError as exc:
        return jsonify({"error": str(exc)}), 400

    matches = db.find_by_digest(digest.hex())
    return jsonify({
        "digest": digest.hex(),
        "found": len(matches),
        "stamps": [_public(m) for m in matches],
        "independent_check": "ots verify <fichero>.ots -f <tu-fichero>",
    })


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "La petición es demasiado grande. Envía solo la huella."}), 413


if __name__ == "__main__":
    db.init()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5055)), debug=False)
