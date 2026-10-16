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

                print("Aguarde as conversas carregarem.")
                print("Se necessário, pesquise pelo grupo no WhatsApp Web.")
                input("Com o grupo visível na lista, pressione Enter...")

                group = page.get_by_text(
                    "Mineiro Society Quinta19h",
                    exact=True,
                ).filter(has_not=page.locator("*"))

                group = page.locator('span[title="Mineiro Society Quinta19h"]')

                group.click(timeout=15000)

                print("Grupo aberto.")
                print(
                    "Envie pelo celular uma mensagem de teste: " "!lista TESTE-BOT-001"
                )
                input(
                    "Quando ela aparecer na conversa, "
                    "pressione Enter para abrir o inspetor..."
                )

                page.pause()

                input("Pressione Enter para encerrar...")
            finally:
                context.close()

    except (EOFError, KeyboardInterrupt):
        print("\nProtótipo encerrado.")
    except PlaywrightError as error:
        print(f"Não foi possível executar o navegador: {error}")


if __name__ == "__main__":
    main()
