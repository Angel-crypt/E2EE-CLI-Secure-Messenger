from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Sequence

from app.app_controller import AppController
from cli.cli_app import CliApp
from infrastructure.crypto import CryptoProvider
from infrastructure.minimal_relay_server import MinimalRelayServer


def _load_dotenv(path: str = ".env") -> None:
    """Carga variables de .env en os.environ sin sobreescribir las ya seteadas."""
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    except FileNotFoundError:
        pass


async def _relay_main(host: str, port: int) -> None:
    relay = MinimalRelayServer(host=host, port=port)
    await relay.start()
    try:
        logging.info("Relay escuchando en %s", relay.url)
        await asyncio.Future()
    finally:
        await relay.stop()
        logging.info("Relay detenido.")


def main(argv: Sequence[str] | None = None) -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(prog="main.py")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--server", action="store_true", help="Ejecutar relay server")
    mode.add_argument(
        "--client", action="store_true", help="Ejecutar CLI client (default)"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.server:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [RELAY] %(message)s",
            datefmt="%H:%M:%S",
        )
        logging.getLogger("websockets").setLevel(logging.WARNING)
        host = os.getenv("E2EE_RELAY_HOST", "127.0.0.1")
        port = int(os.getenv("E2EE_RELAY_PORT", "8765"))
        try:
            asyncio.run(_relay_main(host, port))
        except KeyboardInterrupt:
            pass
        return

    relay_url = os.getenv("E2EE_RELAY_URL")
    controller = AppController(crypto_provider=CryptoProvider())
    CliApp(controller, relay_url=relay_url).run()


if __name__ == "__main__":
    main()
