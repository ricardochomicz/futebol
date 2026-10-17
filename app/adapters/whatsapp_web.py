import argparse
import os
import re
import sqlite3
from getpass import getpass
from pathlib import Path
from urllib.error import HTTPError, URLError

from playwright.sync_api import (
    Error as PlaywrightError,
    sync_playwright,
)

from app.adapters.terminal import deliver
from app.adapters.whatsapp_delivery import send_reply

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = PROJECT_ROOT / "data" / "whatsapp-session"
OUTBOX_PATH = PROJECT_ROOT / "data" / "whatsapp-outbox.db"
TEST_TEXT = "!lista TESTE-RECEBIDO-001"
PHONE_PATTERN = re.compile(r"\+\d[\d\s()-]+")


def phone_candidates(texts):
    candidates = set()
    for text in texts:
        text = text.strip()
        if not PHONE_PATTERN.fullmatch(text):
            continue
        digits = re.sub(r"\D", "", text)
        if 8 <= len(digits) <= 15:
            candidates.add(f"+{digits}")
    return candidates


def inspect_test_message(page):
    drawer = page.get_by_test_id("chat-info-drawer")
    if drawer.is_visible():
        print("Feche o painel de contato antes de iniciar a identificação.")
        return

    panel = page.get_by_test_id("conversation-panel-messages")
    panel.wait_for(state="visible", timeout=15000)
    messages = panel.locator('[data-testid^="conv-msg-"][data-id]').filter(
        has=page.get_by_test_id("selectable-text").filter(
            has_text=re.compile(rf"^{re.escape(TEST_TEXT)}$")
        )
    )

    # Only consider messages with their own visible author; never infer identity
    # from a neighbouring message or a display-name lookup.
    selected = None
    for message in messages.all():
        authors = message.get_by_test_id("author")
        if message.is_visible() and authors.count() == 1 and authors.is_visible():
            selected = message

    if selected is None:
        print("Nenhuma mensagem de teste carregada com autor visível.")
        print("Peça uma nova mensagem ao participante e deixe o autor visível.")
        return

    message_id = selected.get_attribute("data-id")
    bodies = selected.get_by_test_id("selectable-text")
    if not message_id or bodies.count() != 1 or bodies.inner_text().strip() != TEST_TEXT:
        print("Estrutura da mensagem ambígua. Identificação interrompida.")
        return

    text = bodies.inner_text().strip()
    author = selected.get_by_test_id("author")
    display_name = author.inner_text().strip()
    author.click(timeout=15000)

    drawer.wait_for(state="visible", timeout=15000)
    fields = drawer.get_by_test_id("selectable-text")
    # Wait for the contact details, rather than reading the loading panel.
    fields.filter(has_text=PHONE_PATTERN).first.wait_for(
        state="visible", timeout=15000
    )
    candidates = phone_candidates(fields.all_text_contents())
    if len(candidates) != 1:
        print("Telefone ausente ou ambíguo. Nenhum vínculo foi produzido.")
        return

    print("\nVínculo candidato da mensagem selecionada:")
    print(f"ID da mensagem: {message_id}")
    print(f"Texto: {text}")
    print(f"Autor exibido: {display_name}")
    phone = candidates.pop()
    print(f"Telefone candidato: {phone}")
    return {
        "message_id": message_id,
        "player_id": phone,
        "name": display_name,
        "text": text,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Encaminha uma mensagem de teste do WhatsApp à API local."
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8001")
    parser.add_argument("--group-id", default="whatsapp-teste")
    parser.add_argument(
        "--send-reply", action="store_true",
        help="Envia uma resposta ao grupo Teste; sem esta opção, apenas mostra no terminal.",
    )
    args = parser.parse_args()

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

                group = page.locator('span[title="Teste"]')

                group.click(timeout=15000)

                print("Grupo aberto.")
                print(f"Peça ao outro participante para enviar: {TEST_TEXT}")
                print("Deixe a mensagem e o nome do autor visíveis e feche painéis de contato.")
                input(
                    "Quando ela aparecer na conversa, "
                    "pressione Enter para identificar o remetente..."
                )

                message = inspect_test_message(page)
                if message is not None:
                    message["group_id"] = args.group_id
                    api_key = os.getenv("BOT_API_KEY", "") or getpass("Chave da API: ")
                    try:
                        reply = deliver(args.api_url, api_key, message)
                    except HTTPError as error:
                        detail = error.read().decode("utf-8", errors="replace")
                        print(f"Erro HTTP {error.code}: {detail}")
                    except (URLError, TimeoutError, OSError) as error:
                        print(f"Falha de conexão com a API: {error}")
                        print("Ao repetir esta mensagem, mantenha o mesmo ID para deduplicação.")
                    except (ValueError, KeyError) as error:
                        print(f"Resposta inesperada da API: {error}")
                    else:
                        print(f"\nResposta da API (grupo {args.group_id}):")
                        print(reply)
                        if args.send_reply:
                            input("Feche o painel de contato, confira o grupo Teste e pressione Enter para enviar...")
                            try:
                                print(send_reply(
                                    page, OUTBOX_PATH, args.group_id,
                                    message["message_id"], "Teste", reply,
                                ))
                            except (PlaywrightError, ValueError, OSError, sqlite3.Error) as error:
                                print(f"Envio interrompido: {error}")
                                print("Confira o grupo antes de tentar novamente; não há reenvio automático.")
                        else:
                            print("A resposta não foi enviada ao WhatsApp. Use --send-reply para ativar o envio controlado.")

                input("Pressione Enter para encerrar...")
            finally:
                context.close()

    except (EOFError, KeyboardInterrupt):
        print("\nProtótipo encerrado.")
    except PlaywrightError as error:
        print(f"Não foi possível executar o navegador: {error}")


if __name__ == "__main__":
    main()
