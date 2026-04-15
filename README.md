# 🔐 E2EE-CLI Secure Messenger

![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![CI](https://github.com/Angel-crypt/E2EE-CLI-Secure-Messenger/actions/workflows/ci.yml/badge.svg?branch=main)

---

## ⚠️ Disclaimer

> Este proyecto es un ejercicio educativo de criptografía aplicada.
> No ha sido auditado ni diseñado para resistir adversarios reales.
>
> **No debe utilizarse para proteger información sensible.**

---

## 🎯 Objetivo

Demostrar cómo construir un sistema de mensajería con cifrado de extremo a extremo (E2EE) en un entorno controlado, priorizando:

* Claridad del diseño
* Correctitud criptográfica
* Separación de responsabilidades

El sistema **reduce la confianza en el servidor**, pero **no la elimina completamente**.

### Estado actual de alcance (scope lock)

Esta versión está enfocada en **Fase 1: base funcional local (pre-implementación completa)**:

* ✅ protocolo, sesión/presencia, handshake por estados, CLI y errores estructurados
* ⏳ criptografía E2EE real (ECDH + HKDF + AEAD) — objetivo de Fase 2
* ⏳ transporte asíncrono WebSocket bidireccional — objetivo de Fase 2

> Importante: estos componentes **no están descartados**. Están definidos como parte obligatoria del proyecto y se implementan en la siguiente fase.

---

## 🛡️ Modelo de amenaza

### Protege contra

* Intercepción pasiva de mensajes
* Lectura de contenido por parte del servidor

### No protege contra

* Ataques Man-in-the-Middle (MITM)
* Suplantación de identidad
* Compromiso de endpoints
* Ataques activos durante el intercambio de claves

> ⚠️ La ausencia de autenticación hace que el sistema sea vulnerable a MITM.

---

## 🔄 Flujo criptográfico (objetivo del proyecto)

1. Generación de claves efímeras por cliente
2. Intercambio de claves mediante ECDH
3. Derivación de clave compartida con HKDF (SHA-256)
4. Establecimiento de canal cifrado con Fernet
5. Enrutamiento de mensajes cifrados a través del servidor

---

## 🔐 Seguridad (estado actual)

* En la fase actual, el sistema valida reglas de canal seguro y protocolo en runtime local
* No se envían mensajes si el canal no está `ACTIVE`
* Manejo explícito de errores estructurados (`ERROR`)
* ECDH/HKDF/AEAD reales quedan pendientes para la Fase 2

### Identidad

* Fingerprints de claves públicas para detección de cambios
* **No existe verificación criptográfica de identidad**

---

## ⚠️ Limitaciones

* Sin autenticación fuerte entre usuarios
* Vulnerable a MITM
* Sin persistencia de mensajes
* Sin soporte offline
* Sin transporte websocket real en Fase 1
* Sin cifrado E2EE real en Fase 1

---

## 🚀 Setup

```bash
git clone https://github.com/Angel-crypt/E2EE-CLI-Secure-Messenger.git
cd E2EE-CLI-Secure-Messenger
uv sync
```

---

## 🔒 Git Hooks (recomendado)

```bash
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
```

Esto habilita:

* Validaciones automáticas antes de commit
* Ejecución de tests antes de push

---

## ▶️ Ejecutar CLI

```bash
uv run python main.py
```

Notas de esta fase (Fase 1: base funcional local):

* CLI interactivo local (sin websocket real todavía)
* estado en memoria por ejecución
* notificaciones push dirigidas vía buzón local (`/notif` + polling)

---

## 🧪 Tests

```bash
uv run pytest
```

Convención de pruebas (TDD real): [TESTING](./docs/TESTING.md)

---

## 🛠️ Desarrollo

```bash
uv run pre-commit run --all-files
```

Incluye:

* Linting
* Formateo
* Validaciones
* Tests

---

## 🧩 CLI

```bash
/user <name>
/users
/chat <user>
/msg <user> <msg>
/notif
/poll on|off
/theme <default|minimal|contrast|matrix>
/status
/clear
/leave
/exit
/help
```

Flujo rápido recomendado:

1. `/user alice`
2. `/users`
3. `/chat bob`
4. escribir texto libre (modo chat persistente)
5. `/notif` (ver notificaciones pendientes)

---

## 📦 Dependencias y licencias

Este proyecto utiliza librerías de terceros bajo licencias permisivas (MIT, BSD, Apache 2.0), incluyendo:

* cryptography
* prompt_toolkit
* websockets
* pytest / pytest-asyncio
* ruff

Cada dependencia mantiene su propia licencia.

---

## ⚖️ Licencia

Este proyecto está licenciado bajo la licencia MIT.
Ver archivo: [LICENSE](./LICENSE)

---

## 📄 NOTICE

Este proyecto incluye componentes de terceros.
Ver archivo: [NOTICE](./NOTICE)
