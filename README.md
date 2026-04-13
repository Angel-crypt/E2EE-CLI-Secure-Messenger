# 🔐 E2EE-CLI Secure Messenger

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
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

## 🔄 Flujo criptográfico

1. Generación de claves efímeras por cliente
2. Intercambio de claves mediante ECDH
3. Derivación de clave compartida con HKDF (SHA-256)
4. Establecimiento de canal cifrado con Fernet
5. Enrutamiento de mensajes cifrados a través del servidor

---

## 🔐 Seguridad

* Intercambio de claves: ECDH
* Derivación: HKDF (SHA-256)
* Cifrado autenticado: Fernet (AES-128 + HMAC-SHA256)
* Claves efímeras por sesión
* No se envían mensajes sin canal cifrado
* Manejo explícito de errores criptográficos

### Identidad

* Fingerprints de claves públicas para detección de cambios
* **No existe verificación criptográfica de identidad**

---

## ⚠️ Limitaciones

* Sin autenticación fuerte entre usuarios
* Vulnerable a MITM
* Sin persistencia de mensajes
* Sin soporte offline
* Requiere conexión simultánea

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

## ▶️ Ejecutar

```bash
uv run python main.py
```

---

## 🧪 Tests

```bash
uv run pytest
```

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
/exit
/help
```

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
