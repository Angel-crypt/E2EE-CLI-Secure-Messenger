from app.app_controller import AppController
from cli.cli_app import CliApp
from infrastructure.crypto import CryptoProvider


def main() -> None:
    controller = AppController(crypto_provider=CryptoProvider())
    cli = CliApp(controller)
    cli.run()


if __name__ == "__main__":
    main()
