# zf-vision

Agente local de **Zero Fila**. Corre en la computadora de la entidad, abre la cámara, deja al técnico dibujar la zona de la cola (ROI) y envía métricas al backend SaaS.

Este primer slice cubre **activación + configuración de cámara + ROI**. La parte de visión (YOLO, tracking, envío periódico de métricas) viene en el siguiente slice.

## Requisitos

- Python **3.11+** (probado en 3.14)
- Linux, macOS o Windows
- (Opcional) una cámara USB o una URL RTSP

## Instalación

```bash
# clonar
git clone <repo> zf-vision && cd zf-vision

# crear venv
python3 -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate

# instalar deps
pip install -e ".[dev]"
```

## Configuración

Copiá `.env.example` a `.env` y ajustá lo que necesites:

```bash
cp .env.example .env
```

| Variable | Default | Descripción |
|---|---|---|
| `BACKEND_URL` | `http://localhost:8000` | URL del backend SaaS. Vacía en MOCK. |
| `MOCK_BACKEND` | `true` | Si está en `true`, las llamadas al backend se interceptan localmente. |
| `HOST` | `127.0.0.1` | Host de la UI local. **No expongas a la red sin auth.** |
| `PORT` | `8765` | Puerto. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

> **Por qué `MOCK_BACKEND=true` por default**: este slice funciona end-to-end sin necesidad de tener el backend SaaS levantado. La activación genera un `api_key` local con `secrets.token_urlsafe(32)`. Cuando exista el backend, cambiá `MOCK_BACKEND=false` y `BACKEND_URL=https://api.zero-fila.com`.

## Uso

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8765
fastapi dev --port 8765
```

Abrí `http://127.0.0.1:8765/` en el navegador. Vas a ver el wizard de 3 pasos:

1. **Activar** — pegá el código de activación que te dio el administrador.
2. **Cámara** — elegí una cámara USB detectada o pegá una URL RTSP. Se valida la conexión durante 5s antes de continuar.
3. **ROI** — dibujá uno o más polígonos sobre el preview en vivo. Hacé clic para agregar puntos, doble clic para cerrar, arrastrá un vértice para moverlo.

Al terminar ves la pantalla **Listo** con el resumen. La config queda en:

- Linux/macOS: `~/.config/zf-vision/config.yaml`
- Windows: `%APPDATA%\zf-vision\config.yaml`

Para volver a configurar: `POST /reset` o el botón "↺ Volver a configurar" en la pantalla final.

## Endpoints locales

| Path | Método | Descripción |
|---|---|---|
| `/` | GET | redirect a `/status` |
| `/status` | GET | renderiza el paso actual según el estado |
| `/activation` | POST | envía el código, guarda el `api_key` |
| `/cameras` | POST | guarda la cámara (USB o RTSP) tras validar |
| `/cameras/preview` | GET | stream MJPEG de la cámara activa |
| `/roi` | POST | guarda los polígonos del ROI |
| `/reset` | POST | borra toda la config local |
| `/health` | GET | `{"status": "ok"}` |
| `/api/local/status` | GET | JSON con el estado completo de la config |

## Contrato con el backend SaaS (push)

El agente **siempre** habla con el backend vía HTTP push. Los 4 endpoints (ya implementados en `app/backend_client.py` con la firma final):

| Método | Path | Uso |
|---|---|---|
| `POST` | `/v1/agents/activate` | canjea el código por un `api_key` |
| `POST` | `/v1/agents/me/heartbeat` | latido cada 30s — *próximo slice* |
| `POST` | `/v1/agents/me/metrics` | métrica de cola cada 5–10s — *próximo slice* |
| `GET` | `/v1/agents/me/commands?wait=30` | long-poll de comandos del backend — *próximo slice* |

Los tres últimos se llaman con `X-Agent-Key: <api_key>` y devuelven `401` si la key es inválida.

## Tests

```bash
pytest -v
```

- `tests/test_local_store.py` — carga, persistencia y progresión de pasos.
- `tests/test_activation.py` — flujo HTTP end-to-end con `TestClient`.
- `tests/test_backend_client.py` — los 4 métodos push contra un `MockTransport` (verifica path, método, headers, body, 401, 429).

## Estructura

```
zf-vision/
├── app/
│   ├── main.py              # FastAPI + lifespan
│   ├── config.py            # Settings (.env)
│   ├── paths.py             # config_dir cross-platform
│   ├── local_store.py       # config.yaml en disco
│   ├── backend_client.py    # cliente HTTP (4 métodos push)
│   ├── camera.py            # OpenCV: list_usb + mjpeg
│   ├── schemas.py           # Pydantic
│   └── routers/
│       ├── pages.py         # /, /status, /reset
│       ├── activation.py    # POST /activation
│       ├── cameras.py       # POST /cameras, GET /cameras/preview
│       ├── roi.py           # POST /roi
│       └── api.py           # /health, /api/local/status
├── web/
│   ├── templates/           # base.html + 4 _step_*.html
│   └── static/              # app.css + roi.js
├── tests/
├── pyproject.toml
├── .env.example
└── README.md
```

## Troubleshooting

- **Puerto ocupado**: cambiá `PORT` en `.env` o usá `--port 9000` en uvicorn.
- **No detecta la cámara USB en Linux**: revisá que tu usuario esté en el grupo `video` (`sudo usermod -aG video $USER`, luego cerrá sesión).
- **RTSP no conecta**: probá primero con `ffplay rtsp://...` o VLC para descartar problemas de red/credenciales.
- **El preview queda en gris**: la cámara no está accesible. Andá a `/reset` y reconfigurá.
- **Quiero reinstalar**: `rm -rf ~/.config/zf-vision/` y volvé a empezar.

## Próximo slice

- Pipeline de visión: YOLOv8n + ByteTrack + filtro ROI → conteo.
- Loop de envío: `send_heartbeat` cada 30s, `send_metric` cada 5s, `poll_commands` cada 60s.
- Panel "Estado del agente" en la UI local con métricas en vivo (`/api/local/agent-status`).
- Cuando exista el backend SaaS real: `MOCK_BACKEND=false` y verificar que las métricas aparecen en el dashboard web.
