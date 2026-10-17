import pytest

from app.adapters.whatsapp_messages import normalize_self_phone, rejection_reason, select_new_command, wait_for_new_command


def message(identifier="new", text="!vou", **changes):
    return {
        "message_id": identifier, "texts": [text],
        "author_count": 1, "author_visible": True, **changes,
    }


@pytest.mark.parametrize("text", ["!lista", "!vou", "!gol", "!sair", " !VOU "])
def test_supported_commands_preserve_original_case(text):
    result = select_new_command([message(text=text)], set())
    assert result == {"message_id": "new", "text": text.strip()}


@pytest.mark.parametrize("text", ["!abrir", "!pagamento a", "!lista TESTE-RECEBIDO-001", "Olá", "!vou a", ""])
def test_other_messages_do_not_reach_api(text):
    assert select_new_command([message(text=text)], set()) is None


def test_initial_messages_are_skipped_and_order_is_preserved():
    records = [message("old"), message("first", "!vou"), message("second", "!sair")]
    assert select_new_command(records, {"old"}) == {"message_id": "first", "text": "!vou"}
    assert select_new_command([message("old")], {"old"}) is None


@pytest.mark.parametrize("changes", [
    {"author_count": 0}, {"author_count": 2}, {"author_visible": False},
    {"texts": ["!vou", "Texto citado"]}, {"texts": []}, {"message_id": None},
])
def test_ambiguous_or_unidentified_messages_are_skipped(changes):
    assert select_new_command([message(**changes)], set()) is None


def test_diagnostics_distinguish_old_missing_author_and_hidden_author():
    assert "antes do início" in rejection_reason(message("old"), {"old"})
    assert "própria ou agrupada" in rejection_reason(message(author_count=0), set())
    assert "não está visível" in rejection_reason(message(author_visible=False), set())
    assert "argumentos" in rejection_reason(message(text="!vou teste"), set())
    assert rejection_reason(message(), set()) is None


def test_manual_contact_mode_selects_command_without_inferring_identity():
    record = message(author_count=0, author_visible=False)
    assert select_new_command([record], set()) is None
    assert select_new_command([record], set(), require_author=False) == {
        "message_id": "new", "text": "!vou",
    }


def test_manual_contact_mode_still_rejects_old_and_invalid_messages():
    assert select_new_command([message("old", author_count=0)], {"old"}, require_author=False) is None
    assert select_new_command([message(text="!abrir")], set(), require_author=False) is None
    assert select_new_command([message(texts=["!vou", "citação"])], set(), require_author=False) is None


def test_assisted_mode_keeps_order_even_when_first_command_has_no_author():
    records = [message("join", "!vou", author_count=0), message("leave", "!sair")]
    assert select_new_command(records, set(), require_author=False)["message_id"] == "join"


def test_watch_ignores_history_and_waits_for_supported_command():
    from unittest.mock import MagicMock
    scan = MagicMock(side_effect=[
        [message("old")],
        [message("old"), message("chat", "Olá")],
        [message("new", "!vou", author_count=0)],
    ])
    pause, check = MagicMock(), MagicMock()
    assert wait_for_new_command(scan, {"old"}, pause, check)
    assert pause.call_count == 2
    assert check.call_count == 3


def test_watch_stops_before_scanning_if_chat_changes():
    from unittest.mock import MagicMock
    scan, pause = MagicMock(), MagicMock()
    check = MagicMock(side_effect=ValueError("grupo errado"))
    with pytest.raises(ValueError, match="grupo errado"):
        wait_for_new_command(scan, set(), pause, check)
    scan.assert_not_called()
    pause.assert_not_called()


def test_own_account_phone_normalization():
    assert normalize_self_phone(" +55 (11) 90000-0000 ") == "+5511900000000"


@pytest.mark.parametrize("value", ["admin", "5511900000000", "+123", "+" + "1" * 16, "+55 outro contato"])
def test_invalid_own_account_phone_is_rejected(value):
    with pytest.raises(ValueError, match="telefone"):
        normalize_self_phone(value)
