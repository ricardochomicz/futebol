import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


def deliver(base_url, api_key, message):
    body = json.dumps(message).encode("utf-8")

    request = Request(
        f"{base_url.rstrip('/')}/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
        },
        method="POST",
    )

    with urlopen(request, timeout=20) as response:
        return json.load(response)["reply"]


def main():
    parser = argparse.ArgumentParser(
        description="Simulador de mensagens do bot de futebol"
    )

    parser.add_argument("--group", required=True)
    parser.add_argument("--player", required=True)
    parser.add_argument("--name")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
    )

    args = parser.parse_args()
    api_key = os.getenv("BOT_API_KEY", "")

    print("Digite um comando do bot. Use /sair para fechar o terminal.")

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSimulador encerrado.")
            return

        if text == "/sair":
            return

        if not text:
            continue

        message = {
            "group_id": args.group,
            "player_id": args.player,
            "message_id": uuid4().hex,
            "text": text,
        }

        if args.name:
            message["name"] = args.name

        while True:
            try:
                reply = deliver(args.url, api_key, message)
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")
                print(f"Erro HTTP {error.code}: {detail}")
                break
            except (URLError, TimeoutError, OSError) as error:
                print(f"Falha de conexão: {error}")

                try:
                    retry = input("Reenviar a mesma mensagem? [s/N] ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\nSimulador encerrado.")
                    return

                if retry != "s":
                    break
            except (ValueError, KeyError) as error:
                print(f"Resposta inesperada da API: {error}")
                break
            else:
                print(reply)
                break


if __name__ == "__main__":
    main()
