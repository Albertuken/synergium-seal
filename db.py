"""
Almacenamiento. SQLite a propósito: un solo fichero, copia de seguridad
trivial, cero servicios que mantener.

Aviso importante sobre la ruta: NO pongas la base de datos dentro de iCloud
Drive ni de ninguna carpeta que sincronice. La sincronización puede corromper
un SQLite abierto. Por eso el valor por defecto vive fuera del proyecto.
"""

import os
import sqlite3
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".synergium-seal" / "seal.db"
DB_PATH = Path(os.environ.get("SEAL_DB", DEFAULT_DB))

SCHEMA = """
CREATE TABLE IF NOT EXISTS stamps (
    id          TEXT PRIMARY KEY,
    digest      TEXT NOT NULL,
    label       TEXT,
    created_at  TEXT NOT NULL,
    ots         BLOB NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    anchored_at TEXT,
    heights     TEXT
);
-- Varias personas pueden sellar el mismo contenido de forma legítima;
-- lo que interesa consultar es la huella, no que sea única.
CREATE INDEX IF NOT EXISTS idx_stamps_digest ON stamps(digest);
CREATE INDEX IF NOT EXISTS idx_stamps_status ON stamps(status);

-- Para que una tarea de fondo que se para pueda notarse desde fuera.
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Opiniones de quien prueba esto. Aquí el contenido SÍ se guarda —al revés
-- que en los sellos—, así que el formulario lo dice antes de enviarse.
-- No se guarda IP ni nada que identifique a nadie que no quiera: el correo
-- es opcional y solo sirve para poder repreguntar.
CREATE TABLE IF NOT EXISTS feedback (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    respuesta   TEXT,            -- si | no | duda
    texto       TEXT,
    correo      TEXT,
    llamada     INTEGER NOT NULL DEFAULT 0,   -- se ofrece a la videollamada
    pagina      TEXT,
    idioma      TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    """Identificador legible y no adivinable: SYN-<año>-<8 hex>."""
    return f"SYN-{datetime.now(timezone.utc).year}-{secrets.token_hex(4).upper()}"


@contextmanager
def connect(path: Path = None):
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init(path: Path = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


def insert_stamp(digest: str, label: str, ots: bytes, path: Path = None) -> dict:
    stamp_id = new_id()
    created = now_iso()
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO stamps (id, digest, label, created_at, ots, status) "
            "VALUES (?, ?, ?, ?, ?, 'pending')",
            (stamp_id, digest, label or None, created, ots),
        )
    return {"id": stamp_id, "digest": digest, "label": label or None,
            "created_at": created, "status": "pending"}


def get_stamp(stamp_id: str, path: Path = None):
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM stamps WHERE id = ?", (stamp_id,)).fetchone()
    return dict(row) if row else None


def find_by_digest(digest: str, path: Path = None) -> list:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT id, digest, label, created_at, status, anchored_at, heights "
            "FROM stamps WHERE digest = ? ORDER BY created_at",
            (digest,),
        ).fetchall()
    return [dict(r) for r in rows]


def pending_stamps(limit: int = 500, path: Path = None) -> list:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT id, ots FROM stamps WHERE status = 'pending' "
            "ORDER BY created_at LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_anchored(stamp_id: str, ots: bytes, heights: list, path: Path = None) -> None:
    with connect(path) as conn:
        conn.execute(
            "UPDATE stamps SET ots = ?, status = 'anchored', anchored_at = ?, heights = ? "
            "WHERE id = ?",
            (ots, now_iso(), ",".join(str(h) for h in heights), stamp_id),
        )


def update_proof(stamp_id: str, ots: bytes, path: Path = None) -> None:
    """La prueba creció pero todavía no llega a Bitcoin: se guarda igualmente."""
    with connect(path) as conn:
        conn.execute("UPDATE stamps SET ots = ? WHERE id = ?", (ots, stamp_id))


def insert_feedback(respuesta, texto, correo, llamada, pagina, idioma, path=None) -> dict:
    """Guarda una opinión. Todo es opcional menos que haya algo que guardar."""
    fid = "OP-" + secrets.token_hex(4).upper()
    fila = {
        "id": fid, "created_at": now_iso(),
        "respuesta": respuesta or None, "texto": texto or None, "correo": correo or None,
        "llamada": 1 if llamada else 0, "pagina": pagina or None, "idioma": idioma or None,
    }
    with connect(path) as cx:
        cx.execute(
            "INSERT INTO feedback (id, created_at, respuesta, texto, correo, llamada, pagina, idioma)"
            " VALUES (:id, :created_at, :respuesta, :texto, :correo, :llamada, :pagina, :idioma)",
            fila)
    return fila


def list_feedback(path: Path = None) -> list:
    with connect(path) as cx:
        return [dict(r) for r in cx.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC")]


def feedback_counts(path: Path = None) -> dict:
    with connect(path) as cx:
        filas = cx.execute(
            "SELECT respuesta, COUNT(*) n FROM feedback GROUP BY respuesta").fetchall()
        total = cx.execute("SELECT COUNT(*) n FROM feedback").fetchone()["n"]
        llamada = cx.execute(
            "SELECT COUNT(*) n FROM feedback WHERE llamada = 1").fetchone()["n"]
    return {"total": total, "llamada": llamada,
            **{(r["respuesta"] or "sin responder"): r["n"] for r in filas}}


def set_meta(key: str, value: str, path: Path = None) -> None:
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_meta(key: str, path: Path = None):
    with connect(path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def counts(path: Path = None) -> dict:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM stamps GROUP BY status"
        ).fetchall()
    return {r["status"]: r["n"] for r in rows}
