from pathlib import Path

from playwright.sync_api import (
    Error as PlaywrightError,
    sync_playwright,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = PROJECT_ROOT / "data" / "whatsapp-session"


def main():
    SESSION_DIR.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR),
                headless=False,
                viewport={"width": 1280, "height": 900},
            )

            try:
                page = context.pages[0] if context.pages else context.new_page()

                page.goto(
                    "https://web.whatsapp.com/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                print("WhatsApp Web aberto.")
                print("Se aparecer um QR Code, autentique pelo celular.")
                print("Aguarde suas conversas carregarem.")
                print("Depois, pressione Enter aqui para encerrar.")

                input()
            finally:
                context.close()

    except (EOFError, KeyboardInterrupt):
        print("\nProtótipo encerrado.")
    except PlaywrightError as error:
        print(f"Não foi possível executar o navegador: {error}")


if __name__ == "__main__":
    main()
