"""
Pruebas del servicio de sellado.

Las que tocan red están marcadas: se pueden saltar con -m "not network".
El resto no sale a internet y debe pasar siempre.
"""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import seal  # noqa: E402


# --------------------------------------------------------------------------
# Validación de entrada: la única puerta por la que entran datos
# --------------------------------------------------------------------------

def test_normalise_accepts_valid_digest():
    hex_digest = hashlib.sha256(b"hola").hexdigest()
    assert seal.normalise_digest(hex_digest) == hashlib.sha256(b"hola").digest()


def test_normalise_is_case_insensitive_and_trims():
    hex_digest = hashlib.sha256(b"hola").hexdigest()
    assert seal.normalise_digest("  " + hex_digest.upper() + "  ") == bytes.fromhex(hex_digest)


@pytest.mark.parametrize("bad", [
    "", "abc", "z" * 64, hashlib.sha256(b"x").hexdigest()[:63],
    hashlib.sha256(b"x").hexdigest() + "0", None, 12345, b"bytes",
])
def test_normalise_rejects_everything_else(bad):
    with pytest.raises(seal.SealError):
        seal.normalise_digest(bad)


# --------------------------------------------------------------------------
# Almacenamiento
# --------------------------------------------------------------------------

@pytest.fixture
def tmpdb():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "test.db"
        db.init(path)
        yield path


def test_insert_and_read(tmpdb):
    digest = hashlib.sha256(b"contenido").hexdigest()
    row = db.insert_stamp(digest, "etiqueta", b"\x00proof", tmpdb)
    assert row["status"] == "pending"

    stored = db.get_stamp(row["id"], tmpdb)
    assert stored["digest"] == digest
    assert stored["ots"] == b"\x00proof"


def test_same_digest_can_be_sealed_twice(tmpdb):
    """Dos personas pueden sellar el mismo contenido: no es un error."""
    digest = hashlib.sha256(b"igual").hexdigest()
    a = db.insert_stamp(digest, None, b"a", tmpdb)
    b = db.insert_stamp(digest, None, b"b", tmpdb)
    assert a["id"] != b["id"]
    assert len(db.find_by_digest(digest, tmpdb)) == 2


def test_pending_then_anchored(tmpdb):
    digest = hashlib.sha256(b"x").hexdigest()
    row = db.insert_stamp(digest, None, b"proof", tmpdb)
    assert len(db.pending_stamps(path=tmpdb)) == 1

    db.mark_anchored(row["id"], b"proof2", [812345], tmpdb)
    assert db.pending_stamps(path=tmpdb) == []
    stored = db.get_stamp(row["id"], tmpdb)
    assert stored["status"] == "anchored"
    assert stored["heights"] == "812345"


def test_ids_are_unique_and_unguessable(tmpdb):
    ids = {db.insert_stamp(hashlib.sha256(str(i).encode()).hexdigest(), None, b"p", tmpdb)["id"]
           for i in range(50)}
    assert len(ids) == 50


# --------------------------------------------------------------------------
# API HTTP
# --------------------------------------------------------------------------

@pytest.fixture
def client(tmpdb, monkeypatch):
    monkeypatch.setenv("SEAL_DB", str(tmpdb))
    monkeypatch.setattr(db, "DB_PATH", tmpdb)
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app._db_ready = True
    with app_module.app.test_client() as c:
        yield c


def test_rejects_content_outright(client):
    """La promesa del servicio es que el contenido no llega. Debe rechazarlo."""
    for field in ("content", "text", "file"):
        res = client.post("/api/seal", json={field: "mi protocolo secreto"})
        assert res.status_code == 400
        assert "no acepta contenido" in res.get_json()["error"]


def test_rejects_bad_hash(client):
    res = client.post("/api/seal", json={"hash": "no-es-una-huella"})
    assert res.status_code == 400


def test_verify_unknown_digest_returns_zero(client):
    digest = hashlib.sha256(b"nunca sellado").hexdigest()
    res = client.post("/api/verify", json={"hash": digest})
    assert res.status_code == 200
    assert res.get_json()["found"] == 0


def test_verify_finds_inserted_stamp(client, tmpdb):
    digest = hashlib.sha256(b"sellado").hexdigest()
    db.insert_stamp(digest, "mi etiqueta", b"proof", tmpdb)
    res = client.post("/api/verify", json={"hash": digest})
    body = res.get_json()
    assert body["found"] == 1
    assert body["stamps"][0]["label"] == "mi etiqueta"


def test_stamp_response_never_leaks_the_blob(client, tmpdb):
    digest = hashlib.sha256(b"blob").hexdigest()
    row = db.insert_stamp(digest, None, b"\xde\xad\xbe\xef", tmpdb)
    body = client.get(f"/api/stamp/{row['id']}").get_json()
    assert "ots" not in body
    assert "deadbeef" not in json.dumps(body)


def test_corrupt_proof_degrades_instead_of_500(client, tmpdb):
    """Una prueba ilegible no debe tumbar la ficha entera."""
    digest = hashlib.sha256(b"corrupto").hexdigest()
    row = db.insert_stamp(digest, "sigo siendo legible", b"no soy un ots", tmpdb)
    res = client.get(f"/api/stamp/{row['id']}")
    assert res.status_code == 200
    body = res.get_json()
    assert body["proof_status"] == "unreadable"
    assert body["label"] == "sigo siendo legible"


def test_unknown_stamp_is_404(client):
    assert client.get("/api/stamp/SYN-2026-NOPE").status_code == 404


def test_oversized_request_is_rejected(client):
    huge = "a" * (300 * 1024)
    res = client.post("/api/seal", json={"hash": huge})
    assert res.status_code in (400, 413)


# --------------------------------------------------------------------------
# Red: sellado real contra los calendarios públicos
# --------------------------------------------------------------------------

@pytest.mark.network
def test_real_stamp_roundtrip():
    digest = hashlib.sha256(os.urandom(32)).digest()
    blob = seal.stamp(digest)
    assert seal.proof_covers(blob, digest)

    status = seal.inspect(blob)
    assert status.digest == digest.hex()
    # recién creado siempre está pendiente: Bitcoin tarda horas
    assert status.status == "pending"
    assert status.pending_calendars


@pytest.mark.network
def test_upgrade_of_fresh_stamp_is_a_noop_not_an_error():
    """Un sello recién creado no puede anclarse todavía; no debe fallar por ello."""
    digest = hashlib.sha256(os.urandom(32)).digest()
    blob = seal.stamp(digest)
    new_blob, changed = seal.upgrade(blob)
    assert changed is False
    assert new_blob == blob


def test_inspect_rejects_garbage():
    with pytest.raises(seal.SealError):
        seal.inspect(b"esto no es una prueba ots")
