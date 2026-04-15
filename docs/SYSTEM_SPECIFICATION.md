# E2EE-CLI Secure Messenger — Especificación del Sistema

---

## 1. Propósito

Describir la arquitectura y requisitos del sistema de mensajería segura extremo a extremo, así como su estado por fases de implementación.

Visión objetivo del proyecto:

* intercambio de claves (p. ej. ECDH)
* derivación de secretos (HKDF)
* cifrado autenticado AEAD (p. ej. AES-GCM)
* transporte asíncrono bidireccional (WebSockets)
* arquitectura desacoplada para testabilidad y mantenibilidad

En la fase vigente (Fase 1) ya están consolidados:

* contrato de protocolo estable
* reglas de sesión/presencia
* flujo de handshake por estados
* CLI operativa y predecible
* manejo explícito de errores

---

## 2. Alcance por fases

### Fase 1 — Base funcional local (IMPLEMENTADA)

* Runtime local en memoria
* CLI interactiva determinista
* validación estricta de mensajes de protocolo
* sesión única por usuario
* presencia (`online/offline`) y listado `/users`
* bloqueo de `MESSAGE` sin canal `ACTIVE`
* handshake on-demand por estado de canal
* notificaciones dirigidas en buzón local

### Fase 2 — Implementación completa del objetivo académico (PENDIENTE)

* criptografía real ECDH + HKDF + AEAD (AES-GCM)
* transporte websocket real cliente-servidor (asíncrono)
* integración E2EE end-to-end sobre canal no confiable

Nota: Fase 2 mantiene estilo de prototipo local/entorno controlado; no implica despliegue público en Internet.

---

## 3. Arquitectura operativa vigente (Fase 1)

```text
CLI (prompt-toolkit + rich)
        |
        v
AppController (orquestación)
        |
        v
Servicios de dominio (session/chat/key_exchange)
        |
        v
Repositorios en memoria
```

Módulos de infraestructura (`infrastructure/crypto.py`, `infrastructure/websocket_client.py`) están definidos para Fase 2.

---

## 4. Constantes normativas (Fase 1)

Esta sección es la referencia única para constantes de comportamiento de la Fase 1.

| Constante | Valor | Fuente de implementación |
| --- | --- | --- |
| `KEY_EXCHANGE_TIMEOUT_SECONDS` | `5` | `app/services/key_exchange_service.py` |
| `TIMESTAMP_TOLERANCE_SECONDS` | `120` | `app/protocol.py` |
| Estados de canal válidos | `NONE`, `ESTABLISHING`, `ACTIVE`, `INVALID` | `app/services/key_exchange_service.py` |
| Estados de usuario válidos | `online`, `offline` | `app/repositories/in_memory_repositories.py` |

Regla: ninguna documentación debe declarar valores distintos a esta tabla para Fase 1.

---

## 5. Reglas duras del sistema

* No se envían `MESSAGE` sin canal `ACTIVE`.
* No hay fallback inseguro a envío en claro por bypass de canal.
* No hay fallos silenciosos: los errores se devuelven como `ERROR` estructurado.
* En Fase 1 no hay cifrado real de contenido; el payload de `MESSAGE` es mock para validar flujo.

---

## 6. Protocolo (resumen operativo)

Tipos válidos:

* `REGISTER`
* `HANDSHAKE_INIT`
* `MESSAGE`
* `ERROR`

Estructura base:

```json
{
  "message_id": "uuid",
  "timestamp": "iso8601-utc",
  "type": "REGISTER|HANDSHAKE_INIT|MESSAGE|ERROR",
  "from": "username",
  "to": "username-opcional-según-tipo",
  "payload": {}
}
```

Reglas clave:

* `to` obligatorio por tipo (ver SRS-03).
* sin campos extra en raíz ni `payload`.
* validación de timestamp con tolerancia ±120s.
* errores de validación devuelven `ERROR` con código específico.

---

## 7. Flujos clave (Fase 1)

### Registro

1. Cliente envía `REGISTER`.
2. Sistema valida contrato.
3. Si username no tiene sesión activa: crea sesión y estado `online`.
4. Si ya está activo: `ERROR 409_USERNAME_TAKEN`.

### Envío de mensaje

1. Usuario intenta `MESSAGE`.
2. Si canal no está `ACTIVE`, se inicia/garantiza handshake y se responde `403_SECURE_CHANNEL_REQUIRED`.
3. Una vez canal `ACTIVE`, `MESSAGE` se acepta.

### Timeout de handshake

1. Canal en `ESTABLISHING`.
2. Si supera 5 segundos sin completarse: pasa a `INVALID`.
3. Se responde `504_KEY_EXCHANGE_TIMEOUT`.

### Reconexión/desconexión

1. Cambio de sesión del usuario.
2. Canales asociados pasan a `INVALID`.
3. Se requiere nuevo `HANDSHAKE_INIT` antes de `MESSAGE`.

---

## 8. Interfaz CLI (Fase 1)

Comandos operativos:

* `/user <name>`
* `/logout`
* `/users`
* `/chat <user>`
* `/msg <user> <texto>`
* `/notif`
* `/poll on|off`
* `/theme <default|minimal|contrast|matrix>`
* `/status`
* `/clear`
* `/leave`
* `/help`
* `/exit`

---

## 9. Relación normativa con SRS

* `SRS-01` — CLI Core
* `SRS-02` — Gestión de Sesión y Usuarios
* `SRS-03` — Protocolo de Comunicación
* `SRS-04` — Key Exchange
* `SRS-06` — Manejo de Errores y Resiliencia
* `SRS-07` — Estados del Sistema

Requisitos de Fase 2 (no implementados aún):

* `SRS-05` — Criptografía
* `SRS-08` — Transporte y Enrutamiento Real-time

---

## 10. Criterios de salida por fase

### Salida de Fase 1 (base funcional local)

* Documentación sin contradicciones internas de Fase 1.
* SRS homogéneos en formato y trazabilidad.
* Constantes alineadas entre SRS/spec/código.
* Tests de Fase 1 en verde.

### Salida de Fase 2 (objetivo académico completo)

* E2EE real implementado (ECDH + HKDF + AEAD).
* Transporte WebSocket asíncrono integrado.
* Pruebas de integración E2EE sobre canal no confiable.
