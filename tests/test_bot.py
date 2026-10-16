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


def test_player_name_is_preserved(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 18 20")

    response = client.post(
        "/messages",
        headers={"x-api-key": "secret"},
        json={
            "group_id": "g",
            "player_id": "jogador-123",
            "name": "Carlos",
            "text": "!vou",
        },
    )

    assert response.status_code == 200
    assert "confirmada" in response.json()["reply"]

    listing = send(client, "!lista", "jogador-123")
    assert "Carlos (jogador-123)" in listing

    response = client.post(
        "/messages",
        headers={"x-api-key": "secret"},
        json={
            "group_id": "g",
            "player_id": "jogador-123",
            "name": "   ",
            "text": "!lista",
        },
    )

    assert response.status_code == 200
    assert "Carlos (jogador-123)" in response.json()["reply"]


def guest(client, role, name, group="g"):
    reply = send(client, f"!convidado {role} {name}", group=group)
    assert "ID: convidado-" in reply
    return reply.split("ID: ")[1].strip()


def test_guest_registration_payment_and_attendance(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 1 20")
    send(client, "!vou")  # The administrator may already be registered.
    identifier = guest(client, "linha", "Carlos Silva")
    assert "Carlos Silva" in send(client, "!espera")
    assert "convidado por admin" in send(client, "!espera")
    assert identifier in send(client, "!sair")
    assert "Registro atualizado" in send(client, f"!pagamento {identifier}")
    assert "Recebido: R$ 20.00" in send(client, "!financeiro")
    send(client, f"!presenca {identifier}")
    assert "encerrada" in send(client, "!encerrar")


def test_guest_goalkeeper_queue_and_removal(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 1 20")
    send(client, "!vou", "a")
    send(client, "!vou", "b")
    first = guest(client, "gol", "Pedro Santos")
    guest(client, "gol", "Pedro Santos")  # Same names have distinct IDs.
    third = guest(client, "gol", "Outro Goleiro")
    assert "isento" in send(client, f"!pagamento {first}")
    assert third in send(client, f"!remover {first}")
    assert third in send(client, "!lista")
    assert "b (b)" in send(client, "!espera")
    assert "não encontrado" in send(client, f"!remover {first}")


def test_guest_permissions_validation_and_group_isolation(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 18 20")
    assert "administradores" in send(client, "!convidado linha Carlos", "a")
    assert "administradores" in send(client, "!remover qualquer", "a")
    assert "Use:" in send(client, "!convidado linha")
    assert "Use:" in send(client, "!convidado atacante Carlos")
    assert "100 caracteres" in send(client, "!convidado linha " + "a" * 101)
    identifier = guest(client, "linha", "Carlos")
    send(client, "!abrir 2026-10-21T20:00:00-03:00 18 20", group="other")
    assert "não encontrado" in send(client, f"!remover {identifier}", group="other")
    assert "não encontrado" in send(client, "!remover admin")
    send(client, "!fechar")
    assert "fechadas" in send(client, "!convidado gol Pedro")
    assert "cancelada" in send(client, f"!remover {identifier}")


def test_guest_migration_preserves_existing_players(tmp_path):
    import sqlite3
    from app.database import transaction

    path = str(tmp_path / "old.db")
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE players (group_id TEXT, player_id TEXT, name TEXT, "
            "PRIMARY KEY(group_id, player_id))"
        )
        db.execute("INSERT INTO players VALUES ('g','a','Carlos')")
    for _ in range(2):
        with transaction(path) as db:
            row = db.execute("SELECT * FROM players").fetchone()
            assert row["name"] == "Carlos"
            assert row["invited_by"] is None


def test_repeated_message_creates_only_one_guest(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 18 20")

    message = {
        "group_id": "g",
        "player_id": "admin",
        "message_id": "evento-001",
        "text": "!convidado linha Rafael Teste",
    }

    first = client.post(
        "/messages",
        headers={"x-api-key": "secret"},
        json=message,
    )

    second = client.post(
        "/messages",
        headers={"x-api-key": "secret"},
        json=message,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    listing = send(client, "!lista")
    assert listing.count("Rafael Teste") == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"text": "!convidado linha Outra Pessoa"},
        {"player_id": "outro-jogador"},
    ],
)
def test_reused_message_id_rejects_different_payload(client, changes):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 18 20")

    message = {
        "group_id": "g",
        "player_id": "admin",
        "message_id": "evento-001",
        "text": "!convidado linha Rafael Teste",
    }

    first = client.post(
        "/messages",
        headers={"x-api-key": "secret"},
        json=message,
    )
    assert first.status_code == 200

    conflicting = client.post(
        "/messages",
        headers={"x-api-key": "secret"},
        json={**message, **changes},
    )

    assert conflicting.status_code == 409

    listing = send(client, "!lista")
    assert listing.count("Rafael Teste") == 1
    assert "Outra Pessoa" not in listing


def test_concurrent_duplicate_message_creates_only_one_guest(client):
    send(client, "!abrir 2026-10-21T20:00:00-03:00 18 20")

    message = {
        "group_id": "g",
        "player_id": "admin",
        "message_id": "evento-simultaneo",
        "text": "!convidado linha Rafael Concorrente",
    }

    def deliver(_):
        return client.post(
            "/messages",
            headers={"x-api-key": "secret"},
            json=message,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(deliver, range(2)))

    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json()

    listing = send(client, "!lista")
    assert listing.count("Rafael Concorrente") == 1
