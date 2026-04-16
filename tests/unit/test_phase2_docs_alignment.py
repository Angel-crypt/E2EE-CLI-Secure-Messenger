from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGE_ROOT = REPO_ROOT / "openspec" / "changes" / "phase2-crypto-transport"
IMPLEMENTATION_ROOT = REPO_ROOT / "docs" / "IMPLEMENTATION"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


REQUIRED_IMPLEMENTATION_SECTIONS = (
    "## 1. Que es",
    "## 2. Que resuelve",
    "## 3. API publica del modulo",
    "## 4. Reglas que aplica",
    "## 5. Flujo interno principal",
    "## 6. Relacion con SRS",
    "## 7. Relacion con tests",
    "## 8. Como ejecutar validacion local",
    "## 9. Limites actuales (intencionales)",
    "## 10. Como extender sin romper",
)


EXPECTED_IMPLEMENTATION_DOCS = {
    "app/app_controller.py": "APP_CONTROLLER_IMPLEMENTATION.md",
    "app/interfaces.py": "INTERFACES_IMPLEMENTATION.md",
    "app/protocol.py": "PROTOCOL_IMPLEMENTATION.md",
    "app/services/chat_service.py": "CHAT_SERVICE_IMPLEMENTATION.md",
    "app/services/key_exchange_service.py": "KEY_EXCHANGE_IMPLEMENTATION.md",
    "app/services/user_service.py": "USER_SERVICE_IMPLEMENTATION.md",
    "app/repositories/in_memory_repositories.py": "IN_MEMORY_REPOSITORIES_IMPLEMENTATION.md",
    "cli/cli_app.py": "CLI_APP_IMPLEMENTATION.md",
    "cli/command_catalog.py": "COMMAND_CATALOG_IMPLEMENTATION.md",
    "cli/formatters.py": "CLI_FORMATTERS_IMPLEMENTATION.md",
    "cli/status_diagnostics.py": "STATUS_DIAGNOSTICS_IMPLEMENTATION.md",
    "cli/themes.py": "CLI_THEMES_IMPLEMENTATION.md",
    "infrastructure/crypto.py": "CRYPTO_IMPLEMENTATION.md",
    "infrastructure/websocket_client.py": "WEBSOCKET_CLIENT_IMPLEMENTATION.md",
    "infrastructure/minimal_relay_server.py": "MINIMAL_RELAY_SERVER_IMPLEMENTATION.md",
    "infrastructure/runtime_transport_gateway.py": "RUNTIME_TRANSPORT_GATEWAY_IMPLEMENTATION.md",
    "infrastructure/relay_runner.py": "RELAY_RUNNER_IMPLEMENTATION.md",
    "main.py": "MAIN_IMPLEMENTATION.md",
}


@pytest.mark.unit
def test_phase2_docs_are_fernet_only_with_required_crypto_constraints() -> None:
    srs05 = _read("docs/SRS/SRS-05 — Criptografía.md")
    srs03 = _read("docs/SRS/SRS-03 — Protocolo de Comunicación.md")

    assert "FERNET" in srs05
    assert "SECP384R1" in srs05
    assert "HKDF SHA-256" in srs05
    assert "base64url" in srs05 or "urlsafe_b64encode" in srs05
    assert "AES-GCM" not in srs05

    assert "nonce" in srs03
    assert "sent_at" in srs03
    assert "409_REPLAY_DETECTED" in srs03
    assert "400_REPLAY_TIMESTAMP_INVALID" in srs03
    assert "409_REMOTE_KEY_CHANGED" in srs03


@pytest.mark.unit
def test_system_spec_and_readme_match_phase2_runtime_scope() -> None:
    system_spec = _read("docs/SYSTEM_SPECIFICATION.md")
    readme = _read("README.md")

    assert "Fase 2" in system_spec
    assert "IMPLEMENTADA" in system_spec
    assert "FERNET" in system_spec
    assert "honesto-pero-curioso" in system_spec
    assert "warning" in system_spec.lower()
    assert "AES-GCM" not in system_spec

    assert "Fase 2" in readme
    assert "FERNET" in readme
    assert "SECP384R1" in readme
    assert "honesto-pero-curioso" in readme
    assert "warning" in readme.lower()
    assert "pendiente" not in readme.lower()


@pytest.mark.unit
def test_traceability_checklist_covers_requirement_to_test_chain() -> None:
    traceability = (CHANGE_ROOT / "traceability-phase2.md").read_text(encoding="utf-8")

    assert "Requisito" in traceability
    assert "Spec" in traceability
    assert "Diseño" in traceability
    assert "Task" in traceability
    assert "Test" in traceability
    assert "phase2-docs-alignment" in traceability
    assert "5.1" in traceability
    assert "5.2" in traceability
    assert "5.3" in traceability


@pytest.mark.unit
def test_implementation_docs_cover_all_runtime_modules_and_have_uniform_structure() -> (
    None
):
    for module_path, doc_name in EXPECTED_IMPLEMENTATION_DOCS.items():
        doc_path = IMPLEMENTATION_ROOT / doc_name
        assert doc_path.exists(), f"Falta doc de implementación para {module_path}"

        content = doc_path.read_text(encoding="utf-8")
        assert module_path in content
        for section in REQUIRED_IMPLEMENTATION_SECTIONS:
            assert section in content, f"{doc_name} no incluye sección base: {section}"


@pytest.mark.unit
def test_implementation_readme_indexes_modules_documents_and_completion_status() -> (
    None
):
    readme = (IMPLEMENTATION_ROOT / "README.md").read_text(encoding="utf-8")

    assert "# Índice de Implementación" in readme
    assert "| Módulo | Documento | Estado |" in readme

    for module_path, doc_name in EXPECTED_IMPLEMENTATION_DOCS.items():
        assert module_path in readme
        assert doc_name in readme

    assert "Cobertura" in readme
    assert "18/18" in readme
