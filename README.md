# 🔐 E2EE-CLI Secure Messenger

![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)
![uv](https://img.shields.io/badge/uv-package%20manager-6E56CF?logo=uv&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![CI](https://github.com/Angel-crypt/E2EE-CLI-Secure-Messenger/actions/workflows/ci.yml/badge.svg?branch=main)

CLI educativa con mensajería E2EE sobre WebSocket (relay + clientes).

## Estado

Operativo para uso académico.

## Requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
```

## `.env`

Crear un archivo `.env` en la raíz:

```env
E2EE_RELAY_HOST=127.0.0.1
E2EE_RELAY_PORT=8765
E2EE_RELAY_URL=ws://127.0.0.1:8765
```

## Ejecución

### 1) Relay (Terminal 1)

```bash
uv run main.py --server
```

### 2) Cliente A (Terminal 2)

```bash
uv run main.py --client
```

### 3) Cliente B (Terminal 3)

```bash
uv run main.py --client
```

## Comandos CLI útiles

```text
/user <name>
/users
/chat <user>
/msg <user> <msg>
/status
/help
/exit
```

## Tests

```bash
uv run pytest
```

## Licencia

MIT — ver [LICENSE](./LICENSE)
