import argparse
import os
import re
import sqlite3
from getpass import getpass
from pathlib import Path

from playwright.sync_api import (
    Error as PlaywrightError,
    sync_playwright,
)

from app.adapters.terminal import deliver
from app.adapters.whatsapp_delivery import send_reply, verify_chat
from app.adapters.whatsapp_messages import normalize_self_phone, rejection_reason, select_new_command, wait_for_new_command
from app.adapters.whatsapp_session import run_session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = PROJECT_ROOT / "data" / "whatsapp-session"
OUTBOX_PATH = PROJECT_ROOT / "data" / "whatsapp-outbox.db"
PHONE_PATTERN = re.compile(r"\+\d[\d\s()-]+")
MESSAGE_SELECTOR = '[data-testid^="conv-msg-"][data-id]'


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


def loaded_message_ids(page):
    panel = page.get_by_test_id("conversation-panel-messages")
    panel.wait_for(state="visible", timeout=15000)
    return set(panel.locator(MESSAGE_SELECTOR).evaluate_all(
        "elements => elements.map(element => element.getAttribute('data-id')).filter(Boolean)"
    ))


def read_message_records(page):
    panel = page.get_by_test_id("conversation-panel-messages")
    return panel.locator(MESSAGE_SELECTOR).evaluate_all("""elements => elements.map(element => {
        const authors = element.querySelectorAll('[data-testid="author"]');
        return {
            message_id: element.getAttribute('data-id'),
            texts: Array.from(element.querySelectorAll('[data-testid="selectable-text"]'))
                .map(body => body.innerText),
            text_contents: Array.from(element.querySelectorAll('[data-testid="selectable-text"]'))
                .map(body => body.textContent),
            author_count: authors.length,
            author_visible: authors.length === 1 && authors[0].getClientRects().length > 0
        };
    })""")


def inspect_command_message(page, initial_ids, self_phone=None):
    drawer = page.get_by_test_id("chat-info-drawer")
    if drawer.is_visible():
        print("Feche o painel de contato antes de iniciar a identificação.")
        return
    verify_chat(page, "Teste")

    panel = page.get_by_test_id("conversation-panel-messages")
    panel.wait_for(state="visible", timeout=15000)
    records = read_message_records(page)
    candidate = select_new_command(records, initial_ids, require_author=False)
    manual_contact = False
    if candidate is not None:
        record = next(row for row in records if row["message_id"] == candidate["message_id"])
        manual_contact = select_new_command([record], initial_ids) is None
    if candidate is None:
        print("Nenhum comando novo elegível entre as mensagens carregadas.")
        print("Aceitos: !lista, !vou, !gol e !sair, sem argumentos.")
        print("Mensagens iniciais e comandos administrativos são ignorados.")
        new_records = [record for record in records if record.get("message_id") not in initial_ids]
        print(f"Mensagens carregadas: {len(records)}; IDs novos nesta captura: {len(new_records)}.")
        for record in new_records[-5:]:
            print(f"ID {record.get('message_id')}: {rejection_reason(record, initial_ids)}.")
            for index, text in enumerate(record.get("texts", [])[:3], start=1):
                print(f"  Texto lido {index}: {ascii(text[:160]) if isinstance(text, str) else repr(text)}")
            for index, text in enumerate(record.get("text_contents", [])[:3], start=1):
                print(f"  textContent {index}: {ascii(text[:160]) if isinstance(text, str) else repr(text)}")
            print(
                f"  Autores encontrados: {record.get('author_count')}; "
                f"autor visível: {record.get('author_visible')}."
            )
        print("Envie o comando depois do aviso Captura iniciada.")
        print("Se o próximo comando não tiver autor visível, será solicitada identificação assistida.")
        return

    selected = panel.get_by_test_id(f"conv-msg-{candidate['message_id']}")
    message_id = selected.get_attribute("data-id")
    bodies = selected.get_by_test_id("selectable-text")
    if (message_id != candidate["message_id"] or bodies.count() != 1
            or bodies.inner_text().strip() != candidate["text"]):
        print("Estrutura da mensagem ambígua. Identificação interrompida.")
        return

    text = bodies.inner_text().strip()
    display_name = None
    own_phone = None
    if manual_contact:
        print(f"\nComando encontrado: {text} | ID: {message_id}")
        print("O HTML não permite identificar automaticamente o remetente desta mensagem.")
        print("Abra os dados do remetente pelo grupo e deixe o telefone visível.")
        print("Não selecione pelo nome de outra mensagem sem conferir quem enviou este comando.")
        action = input(
            "Enter com os dados do remetente abertos; /eu se a mensagem é sua; /cancelar: "
        ).strip().lower()
        if action == "/cancelar":
            return
        if action == "/eu":
            own_phone = normalize_self_phone(
                self_phone or input("Telefone da SUA conta conectada (com + e código do país): ")
            )
        elif action:
            print("Opção não reconhecida. Nenhum comando foi enviado à API.")
            return
    else:
        author = selected.get_by_test_id("author")
        display_name = author.inner_text().strip()
        author.click(timeout=15000)

    if own_phone is not None:
        candidates = {own_phone}
        print("Identificação da própria conta informada pelo operador, não inferida do HTML.")
    else:
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
    if display_name:
        print(f"Autor exibido: {display_name}")
    phone = candidates.pop()
    print(f"Telefone candidato: {phone}")
    if manual_contact:
        confirmed = input(f"Esse telefone pertence a quem enviou {text}? [s/N] ").strip().lower()
        if confirmed != "s":
            print("Identificação cancelada. O comando não foi enviado à API.")
            return
    return {
        "message_id": message_id,
        "player_id": phone,
        "name": display_name,
        "text": text,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Encaminha um comando recebido no grupo Teste à API local."
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8001")
    parser.add_argument("--group-id", default="whatsapp-teste")
    parser.add_argument(
        "--self-phone", type=normalize_self_phone,
        help="Telefone da conta conectada; usado somente ao escolher /eu na identificação.",
    )
    parser.add_argument(
        "--send-reply", action="store_true",
        help="Envia uma resposta ao grupo Teste; sem esta opção, apenas mostra no terminal.",
    )
    parser.add_argument(
        "--watch", action="store_true",
        help="Detecta novos comandos sem Enter; identificação e envio continuam assistidos.",
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
                input("Aguarde a conversa carregar e pressione Enter para iniciar a captura...")
                initial_ids = loaded_message_ids(page)
                print("Captura iniciada. As mensagens já carregadas serão ignoradas.")
                print("Agora envie ou peça ao outro participante: !lista, !vou, !gol ou !sair.")
                print("Para comandos da própria conta, escolha /eu na identificação assistida.")
                print("Envie um comando por vez, sem argumentos. Não role o histórico durante a captura.")
                print("Deixe a mensagem e o nome do autor visíveis e feche painéis de contato.")
                run_session(
                    initial_ids=initial_ids,
                    group_id=args.group_id,
                    api_url=args.api_url,
                    api_key=os.getenv("BOT_API_KEY", ""),
                    inspect_message=lambda ignored: inspect_command_message(page, ignored, args.self_phone),
                    deliver=deliver,
                    send_response=(
                        lambda message, reply: send_reply(
                            page, OUTBOX_PATH, args.group_id,
                            message["message_id"], "Teste", reply,
                        )
                    ) if args.send_reply else None,
                    read_key=getpass,
                    browser_errors=(PlaywrightError, sqlite3.Error, ValueError),
                    wait_for_message=(
                        lambda ignored: wait_for_new_command(
                            scan=lambda: read_message_records(page),
                            ignored_ids=ignored,
                            pause=lambda: page.wait_for_timeout(1000),
                            check_chat=lambda: verify_chat(page, "Teste"),
                        )
                    ) if args.watch else None,
                )
            finally:
                context.close()

    except (EOFError, KeyboardInterrupt):
        print("\nProtótipo encerrado.")
    except PlaywrightError as error:
        print(f"Não foi possível executar o navegador: {error}")


if __name__ == "__main__":
    main()
