# Convencion de Pruebas (TDD)

## Objetivo

Definir un patron comun para escribir pruebas en este proyecto con enfoque TDD real.

---

## Flujo TDD obligatorio

1. **Red**: escribir primero la prueba que falla.
2. **Green**: implementar lo minimo para que pase.
3. **Refactor**: mejorar codigo y pruebas sin romper comportamiento.

Regla: no se implementa funcionalidad nueva sin una prueba previa que la justifique.

---

## Tipos de pruebas

## 1) Pruebas unitarias (`@pytest.mark.unit`)

Propósito: validar logica pura en aislamiento.

Reglas:

* usar **fakes internos simples** (clases/funciones fake del propio test o modulo)
* evitar mocks complejos o acoplamiento a detalles internos
* no usar red real, filesystem real, ni procesos externos
* deben ser rapidas y deterministas

Ejemplos de alcance:

* validadores de protocolo
* reglas de sesion/presencia
* mapeo de errores estructurados

## 2) Pruebas de integracion (`@pytest.mark.integration`)

Propósito: validar flujos reales entre componentes.

Reglas:

* usar infraestructura real cuando aplique (crypto real, websockets reales, etc.)
* evitar reemplazar componentes criticos con fakes
* aceptan mayor costo de ejecucion
* validan comportamiento end-to-end de un flujo

Ejemplos de alcance:

* cliente <-> servidor por websocket
* handshake + envio de mensaje cifrado
* manejo real de desconexion/reconexion

---

## Estructura y naming

* tests por dominio en carpetas separadas (`tests/protocol`, `tests/session`, etc.)
* archivos por tema (ejemplo: `test_*_validation_base.py`, `test_*_rules.py`)
* nombres de prueba descriptivos en formato `test_<comportamiento_esperado>()`

---

## Criterios de calidad

* cada requisito SRS debe mapearse a al menos una prueba
* preferir aserciones de comportamiento observable
* errores deben validarse por codigo y estructura, no solo por texto
* evitar duplicacion excesiva: usar helpers pequeños y claros

---

## Comandos recomendados

Suite completa:

```bash
uv run pytest
```

Solo unitarias:

```bash
uv run pytest -m unit
```

Solo integracion:

```bash
uv run pytest -m integration
```

---

## Regla final

Si una prueba tarda mucho o depende de infraestructura real, es integracion.
Si valida logica aislada con fakes internos simples, es unitaria.
