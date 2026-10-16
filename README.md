# Bot de futebol

MVP em Python + FastAPI + SQLite para testar comandos de grupo. Inscrições,
fila FIFO com promoção automática, declaração/validação de pagamento e frequência
real ficam persistidos. Cada grupo possui uma partida ativa independente.

## Executar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --env-file .env --host 127.0.0.1
```

Abra http://127.0.0.1:8000/docs. No `POST /messages`, informe `x-api-key`
com o valor configurado em `.env`. Exemplo de corpo para o administrador:

```json
{"group_id":"futebol","player_id":"admin","text":"!abrir 2026-10-21T20:00:00-03:00 14 20.00"}
```

Para jogadores, use um `player_id` estável e opcionalmente `name`.
Envie `!vou`, `!sair`, `!lista`, `!espera`, `!valor`, `!paguei`, `!frequencia`.
O administrador usa `!pagamento ID`, `!presenca ID`, `!falta ID`,
`!financeiro`, `!fechar`, `!encerrar`. IDs estão na lista; menções do WhatsApp
precisarão ser resolvidas pelo adaptador. `ADMIN_IDS` aceita IDs separados por vírgula.

`!paguei` apenas declara pagamento. `!pagamento` confirma o valor integral da
partida; não há conciliação bancária, parcelas ou reembolsos automáticos.
Pagamentos de quem cancelou continuam no financeiro. A frequência considera
somente partidas encerradas com presença/falta registrada. Encerrar exige marcar
todos os confirmados. Fechar bloqueia novas inscrições; cancelamentos e promoção
continuam disponíveis. Quem sai e retorna vai ao fim da fila.

## Arquitetura e próximos passos

- `app/main.py`: API e autenticação do simulador.
- `app/bot.py`: comandos e regras.
- `app/database.py`: schema e transações SQLite. `BEGIN IMMEDIATE` serializa
  alterações para impedir excesso de vagas com solicitações simultâneas.
- `tests/`: verificação dos fluxos e concorrência.

O endpoint é um simulador: quem possui a chave pode informar qualquer jogador.
Use-o localmente. Antes de expor em rede, um adaptador autenticado deve obter
identidade e grupo diretamente do provedor, sem aceitar IDs informados por jogadores.
Sem `BOT_API_KEY`, o endpoint fica sem autenticação para desenvolvimento local.

Ainda não há conexão ao WhatsApp, envio de mensagens, recorrência ou lembretes.
A próxima etapa é escolher e validar um adaptador para o grupo existente.
Uma integração experimental pelo WhatsApp Web exige login por QR, sessão
persistente, identificação estável de participantes, deduplicação de eventos e
reconexão. A sessão deve ser protegida como uma credencial. A elegibilidade e as
condições atuais de uma integração oficial precisam ser verificadas antes da escolha.
Não publique este simulador diretamente como webhook de produção.

## Testes

```bash
python -m pytest -q
```
