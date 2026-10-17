from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from app.adapters.whatsapp_delivery import (
    attempt_status,
    reserve_reply,
    send_reply,
)


def page_fixture(title="Teste", draft="", reply="Resposta\nLinha 2"):
    page = MagicMock()
    header = MagicMock()
    header.count.return_value = 1
    header.inner_text.return_value = title
    drawer = MagicMock()
    drawer.is_visible.return_value = False
    page.get_by_test_id.side_effect = lambda key: (
        header if key == "conversation-info-header-chat-title" else drawer
    )
    composer = page.locator.return_value
    composer.count.return_value = 1
    composer.inner_text.side_effect = [draft, reply]
    return page, composer


def test_reply_reservation_survives_reopening_and_is_scoped(tmp_path):
    path = tmp_path / "outbox.db"
    assert reserve_reply(path, "g", "event", "Teste", "Resposta")
    assert attempt_status(path, "g", "event") == "reserved"
    assert not reserve_reply(path, "g", "event", "Teste", "Outra resposta")
    assert reserve_reply(path, "other", "event", "Teste", "Resposta")


def test_concurrent_attempts_have_one_reservation(tmp_path):
    path = tmp_path / "outbox.db"
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda _: reserve_reply(path, "g", "event", "Teste", "Resposta"),
            range(8),
        ))
    assert sum(results) == 1


def test_controlled_send_and_duplicate_block(tmp_path):
    page, composer = page_fixture()
    path = tmp_path / "outbox.db"
    assert "Enter enviado" in send_reply(page, path, "g", "event", "Teste", "Resposta\nLinha 2")
    assert attempt_status(path, "g", "event") == "submitted"
    assert "bloqueado" in send_reply(page, path, "g", "event", "Teste", "Resposta\nLinha 2")
    composer.fill.assert_called_once_with("Resposta\nLinha 2", timeout=15000)
    composer.press.assert_called_once_with("Enter", timeout=15000)


def test_wrong_chat_blocks_before_typing(tmp_path):
    page, composer = page_fixture(title="Outro grupo")
    with pytest.raises(ValueError, match="grupo esperado"):
        send_reply(page, tmp_path / "outbox.db", "g", "event", "Teste", "Resposta")
    composer.fill.assert_not_called()
    composer.press.assert_not_called()


def test_draft_is_not_overwritten(tmp_path):
    page, composer = page_fixture(draft="Texto pessoal")
    with pytest.raises(ValueError, match="rascunho"):
        send_reply(page, tmp_path / "outbox.db", "g", "event", "Teste", "Resposta")
    composer.fill.assert_not_called()


def test_uncertain_attempt_is_not_retried(tmp_path):
    page, composer = page_fixture()
    composer.press.side_effect = TimeoutError("Conexão perdida durante Enter")
    path = tmp_path / "outbox.db"
    with pytest.raises(TimeoutError):
        send_reply(page, path, "g", "event", "Teste", "Resposta\nLinha 2")
    assert attempt_status(path, "g", "event") == "uncertain"
    assert "bloqueado" in send_reply(page, path, "g", "event", "Teste", "Resposta\nLinha 2")
    composer.press.assert_called_once()


def test_chat_changed_after_typing_blocks_enter(tmp_path):
    page, composer = page_fixture()
    header = page.get_by_test_id("conversation-info-header-chat-title")
    header.inner_text.side_effect = ["Teste", "Outro grupo"]
    path = tmp_path / "outbox.db"
    with pytest.raises(ValueError, match="grupo esperado"):
        send_reply(page, path, "g", "event", "Teste", "Resposta\nLinha 2")
    composer.press.assert_not_called()
    assert attempt_status(path, "g", "event") == "uncertain"


def test_open_contact_panel_blocks_send(tmp_path):
    page, composer = page_fixture()
    page.get_by_test_id("chat-info-drawer").is_visible.return_value = True
    with pytest.raises(ValueError, match="painel de contato"):
        send_reply(page, tmp_path / "outbox.db", "g", "event", "Teste", "Resposta")
    composer.press.assert_not_called()
