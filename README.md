# Synergium · Servicio de sellado

Fecha un documento antes de compartirlo. Calcula su huella SHA-256 y la ancla en
la cadena de Bitcoin a través de [OpenTimestamps](https://opentimestamps.org).
El certificado resultante lo puede comprobar cualquiera **sin depender de este
servicio**, y sigue siendo válido aunque el servicio desaparezca.

## La decisión que gobierna todo el diseño

**El contenido nunca llega al servidor.** La huella se calcula en el navegador
con Web Crypto y solo viaja esa cadena de 64 caracteres. El servidor rechaza
explícitamente cualquier intento de enviarle contenido.

Consecuencias, y son la razón de hacerlo así:

- No se puede filtrar lo que nunca se ha recibido.
- No hay documentos ajenos que custodiar ni que borrar a petición.
- El coste de almacenamiento es de unos 700 bytes por sello.

Lo único que sí se guarda en claro es la **etiqueta** opcional. La interfaz
avisa de ello donde se escribe.

## Puesta en marcha

```bash
python3 -m venv ~/.venvs/synergium-seal
~/.venvs/synergium-seal/bin/pip install -r requirements.txt
~/.venvs/synergium-seal/bin/python app.py
```

Queda en <http://127.0.0.1:5055>.

## Operación

### La tarea que no puede olvidarse

Un sello recién creado queda **pendiente**: es válido desde ese momento por la
atestación del calendario, pero solo es incontestable cuando entra en un bloque
de Bitcoin, lo que tarda unas horas. Convertir pendientes en anclados es trabajo
de una tarea periódica:

```bash
~/.venvs/synergium-seal/bin/python upgrade_job.py
```

En producción, un cron cada dos horas. Es preferible a un proceso vivo: hay
menos que vigilar y si una pasada falla, la siguiente lo recoge.

```cron
0 */2 * * * cd /ruta/seal-service && /ruta/venv/bin/python upgrade_job.py >> upgrade.log 2>&1
```

**Si esta tarea deja de ejecutarse, los sellos no se pierden** — la prueba sigue
creciendo en los calendarios y se puede recuperar más tarde. Simplemente se
quedan marcados como pendientes más tiempo del debido.

### Base de datos

SQLite, por defecto en `~/.synergium-seal/seal.db`. Se cambia con `SEAL_DB`.

> **No la pongas dentro de iCloud Drive, Dropbox ni ninguna carpeta que
> sincronice.** La sincronización de un SQLite abierto lo puede corromper. Por
> eso el valor por defecto vive fuera de este proyecto, aunque el código esté
> en iCloud.

Copia de seguridad: es un fichero. Cópialo con el servicio parado, o usa
`sqlite3 seal.db ".backup copia.db"` en caliente.

### Despliegue en Fly.io

Lo que tienes que hacer tú (cuentas y pagos no los abre nadie por ti):

1. Crear cuenta en <https://fly.io> y añadir tarjeta. El gasto de esta máquina
   ronda los 2–3 €/mes.
2. Instalar el CLI: `brew install flyctl` y luego `fly auth login`.

Después, desde esta carpeta:

```bash
fly launch --no-deploy          # elige nombre; di NO a crear base de datos
fly volumes create seal_data --size 1 --region mad
fly deploy
```

> **El volumen no es opcional.** Sin él, el sistema de ficheros es efímero y
> el primer redespliegue borraría todos los sellos. Créalo antes del `deploy`.

HTTPS es automático y obligatorio: `crypto.subtle` no existe fuera de contexto
seguro, así que **sobre HTTP plano la página no funciona** salvo en localhost.

Una sola máquina, siempre. SQLite sobre un volumen no se puede compartir entre
máquinas; `fly.toml` ya lo fija así.

Para desarrollo local basta con `python app.py`. El servidor de Flask **no**
debe usarse en producción; el contenedor arranca gunicorn.

### Vigilar sin vigilar

`GET /health` dice cuándo corrió por última vez el anclaje:

```json
{ "upgrade_last_run": "...", "upgrade_stale": false }
```

Si `upgrade_stale` es `true`, la tarea de fondo se paró y los sellos se quedan
pendientes. Nada se pierde, pero hay que reiniciar: `fly apps restart`.

Merece la pena engancharlo a un vigilante externo gratuito (UptimeRobot o
similar) apuntando a `/health`: es la diferencia entre enterarte tú y que te lo
cuente un usuario.

## Pruebas

```bash
~/.venvs/synergium-seal/bin/python -m pytest -m "not network"   # sin red
~/.venvs/synergium-seal/bin/python -m pytest                     # todas
```

Las marcadas `network` sellan de verdad contra los calendarios públicos.

## Comprobación independiente

Esto es lo que hace que el sello valga algo. Con el `.ots` descargado:

```bash
pip install opentimestamps-client
ots verify SYN-2026-XXXX.ots -f tu-fichero.pdf
```

No pasa por este servidor en ningún momento. Mientras el fichero no cambie ni
un byte, la prueba se sostiene sola.

## API

| Método | Ruta | Qué hace |
|---|---|---|
| `POST` | `/api/seal` | `{hash, label?}` → crea el sello. Rechaza contenido. |
| `GET` | `/api/stamp/<id>` | Estado del sello. Nunca devuelve el blob. |
| `GET` | `/api/stamp/<id>/proof` | Descarga el `.ots`. |
| `POST` | `/api/verify` | `{hash}` → sellos que coinciden. |
| `GET` | `/health` | Vivo + recuento por estado. |

## Lo que este servicio no es

- **No sustituye a un registro de propiedad intelectual ni a una patente.**
  Prueba que un contenido existía en una fecha; no prueba autoría ni concede
  derechos.
- **No guarda tu documento.** Si lo pierdes, el sello no te lo devuelve: solo
  sirve para demostrar que el que tienes es el mismo.
- **No tiene cuentas de usuario.** Quien tenga el identificador puede consultar
  los metadatos del sello. Por eso la etiqueta no debe llevar nada sensible.
