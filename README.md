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

## Regras das partidas

Cada grupo pode ter uma partida ativa por vez.

- Até 18 vagas de linha, com quantidade definida na abertura.
- Duas vagas de goleiro, adicionais às vagas de linha.
- Jogadores de linha pagam o valor definido na abertura.
- Goleiros são isentos.
- Linha e goleiros possuem filas de espera separadas.
- Cancelar uma confirmação promove o primeiro da espera da mesma função.
- Para mudar de função, o jogador deve cancelar e se inscrever novamente.
- Fechar inscrições bloqueia novas entradas, mas permite cancelamentos
  e promoções de quem já está na espera.

### Comandos dos jogadores

| Comando | Ação |
|---|---|
| `!vou` | Inscrever-se como jogador de linha |
| `!gol` | Inscrever-se como goleiro |
| `!sair` | Cancelar a inscrição |
| `!lista` | Consultar confirmados por função |
| `!espera` | Consultar as filas de espera |
| `!valor` | Consultar o valor e a regra de isenção |
| `!paguei` | Declarar pagamento, sujeito à validação |
| `!frequencia` | Consultar presenças e faltas em partidas encerradas |

### Exemplo de abertura

O administrador envia:

!abrir 2026-10-21T20:00:00-03:00 18 20.00

Isso abre 18 vagas de linha e duas de goleiro.
O valor por jogador de linha é R$ 20,00.

### Pagamentos e frequência

Declarar pagamento com `!paguei` não confirma o recebimento.
O administrador confirma com `!pagamento ID`.

A isenção não conta como pagamento recebido. Se alguém já pagou e depois
mudou para goleiro, o pagamento anterior permanece registrado.
Reembolsos são tratados manualmente.

Estar confirmado não significa ter comparecido.
O administrador registra `!presenca ID` ou `!falta ID` para cada confirmado.
A partida só pode ser encerrada após todos esses registros.

## Testes

```bash
python -m pytest -q
```
