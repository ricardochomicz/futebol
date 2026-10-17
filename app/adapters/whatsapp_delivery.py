"""Envio controlado pela interface e registro local de tentativas.

Não garante entrega: após uma tentativa incerta não há reenvio automático.
"""

import sqlite3
from pathlib import Path


def connect_outbox(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=20)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS reply_attempts (
            group_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            group_name TEXT NOT NULL,
            reply TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('reserved','submitted','uncertain')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(group_id, message_id)
        )
    """)
    connection.commit()
    return connection


def reserve_reply(path, group_id, message_id, group_name, reply):
    connection = connect_outbox(path)
    try:
        with connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO reply_attempts "
                "(group_id,message_id,group_name,reply,status) VALUES (?,?,?,?,'reserved')",
                (group_id, message_id, group_name, reply),
            )
        return cursor.rowcount == 1
    finally:
        connection.close()


def attempt_status(path, group_id, message_id):
    connection = connect_outbox(path)
    try:
        row = connection.execute(
            "SELECT status FROM reply_attempts WHERE group_id=? AND message_id=?",
            (group_id, message_id),
        ).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def mark_attempt(path, group_id, message_id, status):
    connection = connect_outbox(path)
    try:
        with connection:
            connection.execute(
                "UPDATE reply_attempts SET status=? WHERE group_id=? AND message_id=?",
                (status, group_id, message_id),
            )
    finally:
        connection.close()


def verify_chat(page, group_name):
    title = page.get_by_test_id("conversation-info-header-chat-title")
    if title.count() != 1 or not title.is_visible() or title.inner_text().strip() != group_name:
        raise ValueError("O cabeçalho não identifica unicamente o grupo esperado. Envio bloqueado.")
    if page.get_by_test_id("chat-info-drawer").is_visible():
        raise ValueError("Feche o painel de contato antes do envio.")


def send_reply(page, path, group_id, message_id, group_name, reply):
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("A API não retornou uma resposta de texto preenchida.")
    previous = attempt_status(path, group_id, message_id)
    if previous:
        return f"Envio bloqueado: esta mensagem já tem uma tentativa ({previous})."

    verify_chat(page, group_name)
    composer = page.locator('footer [contenteditable="true"][role="textbox"]')
    if composer.count() != 1 or not composer.is_visible() or not composer.is_editable():
        raise ValueError("Campo de mensagem ausente ou ambíguo. Precisamos conferir o seletor.")
    if composer.inner_text().strip():
        raise ValueError("Há um rascunho no campo de mensagem. Remova-o antes de enviar.")

    # Reserve durably before interacting with the composer. A crash or timeout
    # cannot cause a second automatic attempt on the next execution.
    if not reserve_reply(path, group_id, message_id, group_name, reply):
        return "Envio bloqueado: outra execução já reservou esta resposta."
    try:
        composer.fill(reply, timeout=15000)
        if composer.inner_text().replace("\r\n", "\n").strip() != reply.replace("\r\n", "\n").strip():
            raise ValueError("O texto no campo difere da resposta. Envio interrompido.")
        verify_chat(page, group_name)
        composer.press("Enter", timeout=15000)
        mark_attempt(path, group_id, message_id, "submitted")
    except BaseException:
        mark_attempt(path, group_id, message_id, "uncertain")
        raise
    return "Enter enviado ao WhatsApp. Confira a mensagem no grupo; entrega não confirmada."
