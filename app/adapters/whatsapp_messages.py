"""Seleção de comandos do piloto, sem inferir remetentes pelo nome."""

SUPPORTED_COMMANDS = frozenset({"!lista", "!vou", "!gol", "!sair"})


def rejection_reason(message, initial_ids):
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
    if message.get("author_count") != 1:
        return "sem autor único; pode ser mensagem própria ou agrupada"
    if not message.get("author_visible"):
        return "autor não está visível"
    return None


def select_new_command(messages, initial_ids):
    """Escolhe o primeiro comando elegível na ordem das mensagens carregadas."""
    for message in messages:
        if rejection_reason(message, initial_ids) is not None:
            continue
        return {"message_id": message["message_id"], "text": message["texts"][0].strip()}
    return None
