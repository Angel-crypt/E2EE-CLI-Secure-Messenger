from app.app_controller import AppController
from cli.cli_app import CliApp


def main() -> None:
    controller = AppController()
    cli = CliApp(controller)
    cli.run()


if __name__ == "__main__":
    main()
