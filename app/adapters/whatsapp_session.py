"""Sessão assistida de comandos, independente do navegador concreto."""

from urllib.error import HTTPError, URLError


def run_session(
    initial_ids, group_id, api_url, api_key, inspect_message, deliver,
    send_response=None, read=input, read_key=None, output=print,
    browser_errors=(),
):
    ignored_ids = set(initial_ids)
    pending = None
    reply = None

    while True:
        prompt = (
            "Enter para repetir a tentativa, /pular para descartar ou /sair: "
            if pending else
            "Quando chegar um comando, feche painéis de contato e pressione Enter (/sair para encerrar): "
        )
        action = read(prompt).strip().lower()
        if action == "/sair":
            return
        if action == "/pular":
            if pending:
                ignored_ids.add(pending["message_id"])
                output("Mensagem ignorada nesta sessão. Alterações já feitas na API não são desfeitas.")
                pending = None
                reply = None
            continue
        if action:
            output("Use Enter, /pular ou /sair; comandos de futebol devem ser enviados no WhatsApp.")
            continue

        if pending is None:
            try:
                message = inspect_message(ignored_ids)
            except browser_errors as error:
                output(f"Falha na identificação: {error}. Nenhum comando foi enviado à API.")
                continue
            if message is None:
                continue
            pending = {**message, "group_id": group_id}

        if reply is None:
            if not api_key and read_key:
                api_key = read_key("Chave da API: ")
            try:
                reply = deliver(api_url, api_key, pending)
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")
                output(f"Erro HTTP {error.code}: {detail}")
                if error.code == 401:
                    api_key = ""
                    output("Na próxima tentativa, informe a chave novamente.")
                continue
            except (URLError, TimeoutError, OSError, ValueError, KeyError) as error:
                output(f"Falha na consulta à API: {error}")
                output("O ID e o remetente foram preservados para repetir a mesma mensagem.")
                continue
            ignored_ids.add(pending["message_id"])
            output(f"\nResposta da API (grupo {group_id}):")
            output(reply)

        if send_response:
            action = read(
                "Feche o painel de contato, confira o grupo Teste e pressione Enter para enviar "
                "(/pular para não enviar, /sair para encerrar): "
            ).strip().lower()
            if action == "/sair":
                return
            if action == "/pular":
                output("Resposta não enviada. O comando já foi processado pela API.")
            elif action:
                output("Opção inválida. A resposta continua pendente.")
                continue
            else:
                try:
                    output(send_response(pending, reply))
                except (OSError, ValueError) + browser_errors as error:
                    output(f"Envio interrompido: {error}")
                    output("Confira o grupo. A próxima tentativa respeitará o registro contra duplicatas.")
                    continue
        else:
            output("Resposta somente no terminal. Use --send-reply para ativar o envio controlado.")

        pending = None
        reply = None
        output("Pronto para outro comando, mantendo a mesma sessão do navegador.")
