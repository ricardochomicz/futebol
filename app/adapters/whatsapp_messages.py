"""Seleção de comandos do piloto, sem inferir remetentes pelo nome."""

import re

SUPPORTED_COMMANDS = frozenset({"!lista", "!vou", "!gol", "!sair"})


def normalize_self_phone(value):
    value = value.strip()
    digits = re.sub(r"\D", "", value)
    if not re.fullmatch(r"\+\d[\d\s()-]+", value) or not 8 <= len(digits) <= 15:
        raise ValueError("Informe seu telefone com +, código do país, DDD e número.")
    return f"+{digits}"


def rejection_reason(message, initial_ids, require_author=True):
    identifier = message.get("message_id")
    if not identifier:
        return "mensagem sem ID"
    if identifier in initial_ids:
        return "mensagem já carregada antes do início da captura"
    bodies = message.get("texts", [])
    if len(bodies) != 1:
        return "texto ausente ou estrutura ambígua (por exemplo, mensagem com citação)"
    text = bodies[0]
    if not isinstance(text, str) or text.strip().lower() not in SUPPORTED_COMMANDS:
        return "texto não é um dos quatro comandos aceitos, sem argumentos"
    if require_author and message.get("author_count") != 1:
        return "sem autor único; pode ser mensagem própria ou agrupada"
    if require_author and not message.get("author_visible"):
        return "autor não está visível"
    return None


def select_new_command(messages, initial_ids, require_author=True):
    """Escolhe o primeiro comando elegível na ordem das mensagens carregadas."""
    for message in messages:
        if rejection_reason(message, initial_ids, require_author=require_author) is not None:
            continue
        return {"message_id": message["message_id"], "text": message["texts"][0].strip()}
    return None


def wait_for_new_command(scan, ignored_ids, pause, check_chat):
    """Aguarda um comando carregado; a pausa é fornecida pelo navegador."""
    while True:
        check_chat()
        if select_new_command(scan(), ignored_ids, require_author=False) is not None:
            return True
        pause()
