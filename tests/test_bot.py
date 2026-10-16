from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_IDS", "admin")
    monkeypatch.setenv("BOT_API_KEY", "secret")
    return TestClient(create_app(str(tmp_path / "test.db")))


def send(client, text, player="admin", group="g"):
    response = client.post(
        "/messages",
        headers={"x-api-key": "secret"},
        json={"player_id": player, "group_id": group, "text": text},
    )
    assert response.status_code == 200
    return response.json()["reply"]


def test_queue_payment_attendance(client):
    assert "aberta" in send(client, "!abrir 2026-10-21T20:00:00-03:00 1 20")
    assert "confirmada" in send(client, "!vou", "a")
    assert "já" in send(client, "!vou", "a")
    assert "espera" in send(client, "!vou", "b")
    assert "espera" in send(client, "!vou", "c")
    assert "b (b)" in send(client, "!sair", "a")
    assert "espera" in send(client, "!vou", "a")
    assert send(client, "!espera").index("c (c)") < send(client, "!espera").index(
        "a (a)"
    )
    assert "Aguardando" in send(client, "!paguei", "b")
    assert "administradores" in send(client, "!pagamento b", "b")
    send(client, "!pagamento b")
    assert "20.00" in send(client, "!financeiro")
    assert "Registre" in send(client, "!encerrar")
    send(client, "!presenca b")
    send(client, "!encerrar")
    assert "1/1" in send(client, "!frequencia", "b")
    assert "0/0" in send(client, "!frequencia", "a")


def test_auth_isolation_and_validation(client):
    assert (
        client.post("/messages", json={"player_id": "a", "text": "!lista"}).status_code
        == 401
    )
    assert "Use:" in send(client, "!abrir 2026-10-21T20:00:00 2 20")
    assert "Use:" in send(client, "!abrir 2026-10-21T20:00:00-03:00 0 20")
    assert "Use:" in send(client, "!abrir 2026-10-21T20:00:00-03:00 2 NaN")
    send(client, "!abrir 2026-10-21T20:00:00-03:00 2 20")
    assert "Nenhuma" in send(client, "!lista", group="other")
    send(client, "!fechar")
    assert "fechadas" in send(client, "!vou", "a")


def test_capacity_under_concurrency(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 3 20")
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda i: send(client, "!vou", f"p{i}"), range(12)))
    assert sum("confirmada" in reply for reply in replies) == 3
    assert sum("fila" in reply for reply in replies) == 9
    assert "3/3" in send(client, "!lista")


def test_cancelled_payment_is_preserved(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 2 20")
    send(client, "!vou", "a")
    send(client, "!pagamento a")
    send(client, "!sair", "a")
    assert "20.00" in send(client, "!financeiro")
    send(client, "!vou", "a")
    assert "já foi confirmado" in send(client, "!paguei", "a")


def test_goalkeeper_capacity_and_exemption(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 1 20")

    assert "confirmada" in send(client, "!vou", "linha-a")
    assert "espera" in send(client, "!vou", "linha-b")

    assert "isento" in send(client, "!gol", "g1")
    assert "isento" in send(client, "!gol", "g2")
    assert "espera de goleiros" in send(client, "!gol", "g3")

    listing = send(client, "!lista")
    assert "Linha: 1/1" in listing
    assert "Goleiros — isentos: 2/2" in listing
    assert "g3 (g3)" not in listing

    assert "isento" in send(client, "!paguei", "g1")
    assert "isento" in send(client, "!pagamento g1")

    financial = send(client, "!financeiro")
    assert "Recebido: R$ 0.00" in financial
    assert "Pendente dos confirmados: R$ 20.00" in financial
    assert "Confirmados isentos: 2" in financial


def test_promotion_respects_role(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 1 20")

    send(client, "!vou", "linha-a")
    send(client, "!vou", "linha-b")

    send(client, "!gol", "g1")
    send(client, "!gol", "g2")
    send(client, "!gol", "g3")
    send(client, "!gol", "g4")

    reply = send(client, "!sair", "g1")
    assert "g3 (g3)" in reply

    listing = send(client, "!lista")
    assert "g3 (g3)" in listing
    assert "linha-b (linha-b)" not in listing

    waiting = send(client, "!espera")
    assert "linha-b (linha-b)" in waiting
    assert "g4 (g4)" in waiting
    assert "g3 (g3)" not in waiting

    reply = send(client, "!sair", "linha-a")
    assert "linha-b (linha-b)" in reply

    listing = send(client, "!lista")
    assert "linha-b (linha-b)" in listing
    assert "g4 (g4)" not in listing


def test_goalkeeper_attendance(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 18 20")

    send(client, "!gol", "g1")
    send(client, "!gol", "g2")

    assert "Registre" in send(client, "!encerrar")

    assert "administradores" in send(client, "!presenca g1", "g1")

    send(client, "!presenca g1")
    send(client, "!falta g2")

    assert "encerrada" in send(client, "!encerrar")

    assert "1/1" in send(client, "!frequencia", "g1")
    assert "0/1" in send(client, "!frequencia", "g2")


def test_closed_match_blocks_goalkeeper_registration(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 18 20")

    send(client, "!fechar")

    assert "fechadas" in send(client, "!gol", "g1")

    listing = send(client, "!lista")
    assert "Goleiros — isentos: 0/2" in listing
    assert "g1 (g1)" not in listing
