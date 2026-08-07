"""
Sellado de anterioridad sobre OpenTimestamps.

Principio de diseño que atraviesa todo el módulo: aquí nunca entra contenido.
Solo entran huellas SHA-256 ya calculadas por el cliente. El servicio no puede
filtrar lo que nunca ha recibido, y esa es justamente la promesa que vende.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Iterator, Optional

from opentimestamps.calendar import RemoteCalendar
from opentimestamps.core.notary import (
    BitcoinBlockHeaderAttestation,
    PendingAttestation,
)
from opentimestamps.core.op import OpSHA256
from opentimestamps.core.serialize import (
    BytesDeserializationContext,
    BytesSerializationContext,
)
from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

# Calendarios públicos. Se envía a varios a propósito: si uno desaparece,
# la prueba sigue siendo válida por los otros.
CALENDARS = (
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
)

HEX64 = re.compile(r"^[0-9a-f]{64}$")


class SealError(Exception):
    """Error recuperable: el llamante puede reintentar o corregir la entrada."""


def normalise_digest(value: str) -> bytes:
    """Acepta una huella SHA-256 en hexadecimal y devuelve sus 32 bytes.

    Rechaza cualquier otra cosa. Es la única puerta de entrada de datos.
    """
    if not isinstance(value, str):
        raise SealError("La huella debe ser una cadena hexadecimal.")
    cleaned = value.strip().lower()
    if not HEX64.match(cleaned):
        raise SealError("La huella debe ser SHA-256: 64 caracteres hexadecimales.")
    return bytes.fromhex(cleaned)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Creación del sello
# --------------------------------------------------------------------------

def stamp(digest: bytes, calendars: tuple = CALENDARS) -> bytes:
    """Sella una huella contra los calendarios y devuelve la prueba .ots serializada.

    Basta con que un calendario responda. Si ninguno responde, es un fallo
    temporal y se propaga para que el llamante reintente: no se guarda un
    sello a medias que luego no se pueda verificar.
    """
    ts = Timestamp(digest)
    reached = []
    errors = []

    for url in calendars:
        try:
            result = RemoteCalendar(url).submit(digest)
            ts.merge(result)
            reached.append(url)
        except Exception as exc:  # red caída, calendario retirado, timeout
            errors.append(f"{url}: {type(exc).__name__}")

    if not reached:
        raise SealError(
            "Ningún calendario de OpenTimestamps respondió. "
            "Es un fallo temporal, vuelve a intentarlo. Detalle: " + "; ".join(errors)
        )

    return serialise(digest, ts)


def serialise(digest: bytes, ts: Timestamp) -> bytes:
    dtf = DetachedTimestampFile(OpSHA256(), ts)
    ctx = BytesSerializationContext()
    dtf.serialize(ctx)
    return ctx.getbytes()


def deserialise(blob: bytes) -> DetachedTimestampFile:
    try:
        return DetachedTimestampFile.deserialize(BytesDeserializationContext(blob))
    except Exception as exc:
        raise SealError(f"La prueba .ots está corrupta o no es válida: {exc}")


# --------------------------------------------------------------------------
# Actualización: de "pendiente" a "anclado en Bitcoin"
# --------------------------------------------------------------------------

def _walk(ts: Timestamp) -> Iterator[Timestamp]:
    """Recorre el árbol de timestamps, incluido el nodo raíz."""
    yield ts
    for sub in ts.ops.values():
        yield from _walk(sub)


def upgrade(blob: bytes) -> tuple[bytes, bool]:
    """Intenta convertir las atestaciones pendientes en anclajes de Bitcoin.

    Devuelve (prueba, cambió). Que no cambie no es un error: los calendarios
    tardan horas en incluir la huella en un bloque, así que lo normal es que
    las primeras llamadas no traigan nada.
    """
    dtf = deserialise(blob)
    changed = False

    for node in list(_walk(dtf.timestamp)):
        if any(isinstance(a, BitcoinBlockHeaderAttestation) for a in node.attestations):
            continue  # este nodo ya está anclado
        for att in list(node.attestations):
            if not isinstance(att, PendingAttestation):
                continue
            uri = att.uri.decode() if isinstance(att.uri, bytes) else att.uri
            try:
                upgraded = RemoteCalendar(uri).get_timestamp(node.msg)
            except Exception:
                # 404 mientras no esté confirmado: es el caso normal, no un fallo
                continue
            if upgraded is not None:
                node.merge(upgraded)
                changed = True

    if not changed:
        return blob, False
    return serialise(dtf.file_digest, dtf.timestamp), True


# --------------------------------------------------------------------------
# Lectura del estado de una prueba
# --------------------------------------------------------------------------

@dataclass
class ProofStatus:
    digest: str
    anchored: bool
    bitcoin_heights: list
    pending_calendars: list

    @property
    def status(self) -> str:
        return "anchored" if self.anchored else "pending"


def inspect(blob: bytes) -> ProofStatus:
    """Lee una prueba .ots y describe en qué punto está, sin tocar la red."""
    dtf = deserialise(blob)
    heights, pending = [], []

    for _msg, att in dtf.timestamp.all_attestations():
        if isinstance(att, BitcoinBlockHeaderAttestation):
            heights.append(att.height)
        elif isinstance(att, PendingAttestation):
            uri = att.uri.decode() if isinstance(att.uri, bytes) else att.uri
            pending.append(uri)

    return ProofStatus(
        digest=dtf.file_digest.hex(),
        anchored=bool(heights),
        bitcoin_heights=sorted(heights),
        pending_calendars=sorted(set(pending)),
    )


def proof_covers(blob: bytes, digest: bytes) -> bool:
    """¿Esta prueba corresponde a esta huella exacta?"""
    return deserialise(blob).file_digest == digest
