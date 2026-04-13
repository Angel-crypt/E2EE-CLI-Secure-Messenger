# *E2EE-CLI Secure Messenger*

---

## 1. Propósito

Sistema de mensajería en CLI que permite comunicación en tiempo real entre usuarios conectados, garantizando:

* confidencialidad (E2EE)
* integridad básica del canal
* manejo explícito de errores
* comportamiento predecible

El servidor **no tiene acceso al contenido de los mensajes**.

---

## 2. Modelo del sistema

``` bash
[ Cliente A ] ←→ [ Servidor (relay) ] ←→ [ Cliente B ]
     |                                         |
     └────── cifrado extremo a extremo ────────┘
```

---

## 3. Componentes

### Cliente

* identidad (`username`)
* generación de llaves (ECC)
* intercambio de llaves
* cifrado / descifrado
* CLI interactiva
* manejo de estados

---

### Servidor

* registro de usuarios activos
* validación de username único
* routing de mensajes
* gestión de presencia consultable por comandos CLI (`/users`)
* notificación de cambios mediante mensajes `ERROR`/estado local (sin tipo `USER_EVENT` dedicado)

---

## 4. Seguridad (by design)

### Cifrado

* ECDH → intercambio de secreto
* HKDF → derivación de clave
* AES (Fernet) → cifrado de mensajes

---

### Propiedades

* End-to-End Encryption
* Forward secrecy (por sesión)
* Zero-knowledge server

---

### Reglas duras

* No se envían mensajes sin shared key
* No hay fallback inseguro
* No hay fallos silenciosos

---

## 5. Flujos clave

### Conexión

``` bash
Cliente → genera llaves
Cliente → register(username, pubkey)
Servidor → valida / responde
Cliente → consulta usuarios activos con /users cuando lo requiera
```

---

### Mensaje normal

``` bash
if shared_key:
    encrypt → send → decrypt
else:
    establecer canal → luego enviar
```

---

### Usuario offline

``` bash
/chat bob
→ ERROR: usuario no disponible
```

---

### Key exchange (on-demand)

``` bash
Intento de mensaje
→ no hay shared_key
→ enviar HANDSHAKE_INIT
→ derivar clave
→ continuar
```

---

### Timeout

``` bash
No respuesta de pubkey
→ ERROR (5–10s)
→ abortar operación
```

---

### Reconexión

``` bash
Bob se reconecta
→ nueva public key
→ invalidar shared keys
→ notificar cambio
```

---

### Error de descifrado

``` bash
Mensaje inválido
→ notificar
→ borrar clave
→ reintercambiar
```

---

## 6. Interfaz CLI

### Comandos

``` bash
/user <name>
/users
/chat <user>
/msg <user> <mensaje>
/exit
/help
```

---

### Estados visibles

* `[INFO] usuario conectado`
* `[ERROR] usuario no disponible`
* `[WARNING] clave cambiada`
* `[INFO] estableciendo canal seguro`

---

### Modos

* modo comando
* modo chat (contexto persistente)

---

## 7. Protocolo (conceptual)

### Tipos de mensajes

* REGISTER
* HANDSHAKE_INIT
* MESSAGE (encrypted)
* ERROR

---

### Estructura base (obligatoriedad por tipo)

``` json
{
  message_id,
  timestamp,
  type,
  from,
  to,
  payload
}
```

Regla: la obligatoriedad de `to` es por tipo, no global. El objeto anterior representa el universo de campos posibles, no un conjunto obligatorio universal.

* `REGISTER` -> `to` no requerido
* `HANDSHAKE_INIT` -> `to` requerido
* `MESSAGE` -> `to` requerido
* `ERROR` -> `to` opcional

Matriz de obligatoriedad:

| Campo | REGISTER | HANDSHAKE_INIT | MESSAGE | ERROR |
|---|---|---|---|---|
| `message_id` | requerido | requerido | requerido | requerido |
| `timestamp` | requerido | requerido | requerido | requerido |
| `type` | requerido | requerido | requerido | requerido |
| `from` | requerido | requerido | requerido | requerido |
| `to` | no requerido | requerido | requerido | opcional |
| `payload` | requerido | requerido | requerido | requerido |

---

### Payload estricto y sin campos extra

* El `payload` se valida de forma estricta por `type`.
* No se aceptan campos extra en raíz ni dentro de `payload`.
* Todo mensaje inválido se rechaza antes de cualquier procesamiento.

---

### Errores estructurados

Los errores se transportan como mensajes `ERROR` con `payload` estructurado:

``` json
{
  "code": "404_USER_OFFLINE",
  "message": "El usuario destino no está disponible",
  "details": {},
  "retriable": true
}
```

Categorías usadas:

* 4xx -> formato, validación y estado del cliente/protocolo
* 5xx -> fallas operativas del servidor

Regla de direccionamiento para `ERROR`:

* con `to`: entrega unicast al usuario destino
* sin `to`: error local/contextual, no broadcast

Referencia normativa: `docs/SRS/SRS-03 — Protocolo de Comunicación.md`.

---

## 8. Estados del sistema

### Por usuario

* online
* offline

---

### Por canal

* NONE
* ESTABLISHING
* ACTIVE
* INVALID

---

## 9. Limitaciones

* sin autenticación fuerte → posible MITM
* sin persistencia
* sin mensajes offline
* dependencia de conexión simultánea

---

## 10. Decisiones clave

* username único obligatorio
* 1 sesión por usuario
* claves efímeras por ejecución
* intercambio de llaves bajo demanda
* bloqueo hasta canal seguro
* timeout en handshake
* detección de cambio de identidad
* notificaciones de presencia simples
* sin frameworks web

---

## 11. Enfoque de validación

El sistema debe demostrar:

### ✔ Funcionalidad

* envío y recepción correcta
* manejo de usuarios online/offline
* reconexión estable

---

### ✔ Seguridad

* mensajes no legibles en servidor
* fallo al usar claves incorrectas
* reintercambio automático funcional

---

### ✔ Robustez

* no hay fallos silenciosos
* errores siempre visibles
* sistema no se congela
