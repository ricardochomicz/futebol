from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('ADMIN_IDS', 'admin')
    monkeypatch.setenv('BOT_API_KEY', 'secret')
    return TestClient(create_app(str(tmp_path / 'test.db')))


def send(client, text, player='admin', group='g'):
    response = client.post('/messages', headers={'x-api-key': 'secret'}, json={
        'player_id': player, 'group_id': group, 'text': text})
    assert response.status_code == 200
    return response.json()['reply']


def test_queue_payment_attendance(client):
    assert 'aberta' in send(client, '!abrir 2026-10-21T20:00:00-03:00 1 20')
    assert 'confirmada' in send(client, '!vou', 'a')
    assert 'já' in send(client, '!vou', 'a')
    assert 'espera' in send(client, '!vou', 'b')
    assert 'espera' in send(client, '!vou', 'c')
    assert 'b (b)' in send(client, '!sair', 'a')
    assert 'espera' in send(client, '!vou', 'a')
    assert send(client, '!espera').index('c (c)') < send(client, '!espera').index('a (a)')
    assert 'Aguardando' in send(client, '!paguei', 'b')
    assert 'administradores' in send(client, '!pagamento b', 'b')
    send(client, '!pagamento b')
    assert '20.00' in send(client, '!financeiro')
    assert 'Registre' in send(client, '!encerrar')
    send(client, '!presenca b')
    send(client, '!encerrar')
    assert '1/1' in send(client, '!frequencia', 'b')
    assert '0/0' in send(client, '!frequencia', 'a')


def test_auth_isolation_and_validation(client):
    assert client.post('/messages', json={'player_id': 'a', 'text': '!lista'}).status_code == 401
    assert 'Use:' in send(client, '!abrir 2026-10-21T20:00:00 2 20')
    assert 'Use:' in send(client, '!abrir 2026-10-21T20:00:00-03:00 0 20')
    assert 'Use:' in send(client, '!abrir 2026-10-21T20:00:00-03:00 2 NaN')
    send(client, '!abrir 2026-10-21T20:00:00-03:00 2 20')
    assert 'Nenhuma' in send(client, '!lista', group='other')
    send(client, '!fechar')
    assert 'fechadas' in send(client, '!vou', 'a')


def test_capacity_under_concurrency(client):
    send(client, '!abrir 2026-10-21T20:00:00-03:00 3 20')
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda i: send(client, '!vou', f'p{i}'), range(12)))
    assert sum('confirmada' in reply for reply in replies) == 3
    assert sum('fila' in reply for reply in replies) == 9
    assert '3/3' in send(client, '!lista')


def test_cancelled_payment_is_preserved(client):
    send(client, '!abrir 2026-10-21T20:00:00-03:00 2 20')
    send(client, '!vou', 'a')
    send(client, '!pagamento a')
    send(client, '!sair', 'a')
    assert '20.00' in send(client, '!financeiro')
    send(client, '!vou', 'a')
    assert 'já foi confirmado' in send(client, '!paguei', 'a')
