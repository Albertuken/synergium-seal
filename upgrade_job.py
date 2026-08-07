"""
Tarea periódica: convierte los sellos pendientes en anclajes de Bitcoin.

Los calendarios agregan las huellas y las publican en un bloque cada pocas
horas. Hasta entonces el sello ya es válido (hay atestación de calendario),
pero solo queda a prueba de todo cuando entra en la cadena.

Uso:
    python upgrade_job.py           # una pasada
    python upgrade_job.py --loop 3600   # cada hora

En producción, mejor un cron cada 2 h que un proceso vivo: menos que vigilar.
"""

import argparse
import sys
import time

import db
import seal


def run_once(verbose: bool = True) -> dict:
    db.init()
    pending = db.pending_stamps()
    stats = {"checked": len(pending), "anchored": 0, "grown": 0, "errors": 0}

    for row in pending:
        try:
            new_blob, changed = seal.upgrade(row["ots"])
        except Exception as exc:
            stats["errors"] += 1
            if verbose:
                print(f"  {row['id']}: error {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        if not changed:
            continue

        status = seal.inspect(new_blob)
        if status.anchored:
            db.mark_anchored(row["id"], new_blob, status.bitcoin_heights)
            stats["anchored"] += 1
            if verbose:
                print(f"  {row['id']}: anclado en bloque {status.bitcoin_heights}")
        else:
            db.update_proof(row["id"], new_blob)
            stats["grown"] += 1

    # Se deja constancia de la pasada aunque no haya cambiado nada: si esta
    # marca se queda vieja, es que la tarea dejó de correr y nadie lo vio.
    db.set_meta("last_upgrade_run", db.now_iso())
    db.set_meta("last_upgrade_stats",
                f"revisados={stats['checked']} anclados={stats['anchored']} "
                f"ampliados={stats['grown']} errores={stats['errors']}")

    if verbose:
        print(f"revisados {stats['checked']} · anclados {stats['anchored']} "
              f"· ampliados {stats['grown']} · errores {stats['errors']}", flush=True)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Actualiza sellos pendientes.")
    parser.add_argument("--loop", type=int, metavar="SEGUNDOS",
                        help="repetir indefinidamente cada N segundos")
    args = parser.parse_args()

    if not args.loop:
        run_once()
        return

    while True:
        try:
            run_once()
        except Exception as exc:
            print(f"pasada fallida: {type(exc).__name__}: {exc}", file=sys.stderr)
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
