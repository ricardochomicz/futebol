# Bot de futebol

MVP em Python + FastAPI + SQLite para testar comandos de grupo. Inscrições,
fila FIFO com promoção automática, declaração/validação de pagamento e frequência
real ficam persistidos. Cada grupo possui uma partida ativa independente.

## Instalação inicial (Ubuntu / Bash)

Execute os comandos na raiz do projeto. É necessário ter Python 3 com suporte
a ambientes virtuais e, para o WhatsApp Web, uma sessão gráfica no Ubuntu.

```bash
cd ~/Projetos/futebol
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Para instalar também o protótipo do WhatsApp Web:

```bash
python -m pip install -r requirements-whatsapp.txt
python -m playwright install chromium
```

Se a instalação indicar bibliotecas de sistema ausentes no Ubuntu, execute:

```bash
python -m playwright install-deps chromium
```

Esse último comando pode solicitar privilégios de administrador para instalar
pacotes do sistema. Não é necessário para executar somente a API e o terminal.

### Configurar o arquivo .env

Somente se ainda não existir um `.env`:

```bash
cp -n .env.example .env
```

Edite o arquivo com estes campos, substituindo a chave de exemplo:

```dotenv
ADMIN_IDS=admin
BOT_API_KEY=troque-por-uma-chave-secreta
DATABASE_PATH=data/futebol.db
```

- `ADMIN_IDS`: IDs dos administradores, separados por vírgula. Nos exemplos, `admin`.
- `BOT_API_KEY`: chave usada tanto pela API quanto pelos clientes.
- `DATABASE_PATH`: arquivo SQLite; pasta e tabelas são criadas na primeira transação.

O nome do grupo não define a permissão: `player_id` precisa corresponder a um
valor de `ADMIN_IDS`. No WhatsApp, o ID enviado pelo protótipo é o telefone
normalizado; ele não é associado automaticamente a IDs de teste como `admin` ou
`carlos`. Não publique o `.env` nem a pasta `data/` no Git.

## Executar a aplicação

Use terminais separados para a API e os adaptadores. Ative o ambiente virtual
em **cada terminal novo**. Todos os comandos abaixo partem da raiz do projeto.
A porta usada neste guia é **8001**.

### Terminal 1 — API (mantenha em execução)

```bash
cd ~/Projetos/futebol
source .venv/bin/activate
uvicorn app.main:app --reload --env-file .env --host 127.0.0.1 --port 8001
```

Acesse:

- Saúde da API: http://127.0.0.1:8001/health — resposta `{"status":"ok"}`.
- Interface de testes: http://127.0.0.1:8001/docs.

Opcionalmente, confira pelo terminal:

```bash
curl http://127.0.0.1:8001/health
```

No `/docs`, abra `POST /messages`, clique em **Try it out** e preencha
`x-api-key` com o valor de `BOT_API_KEY`. Exemplo de corpo:

```json
{
  "group_id": "whatsapp-teste",
  "player_id": "admin",
  "name": "Organizador",
  "text": "!abrir"
}
```

Use o mesmo `group_id` em todas as mensagens da mesma partida. `message_id` é
opcional no simulador; quando informado, repetir o mesmo evento devolve a resposta
anterior sem executar o comando novamente. Reutilizar o ID com outro remetente
ou texto retorna HTTP 409. Uma nova mensagem deve receber um novo ID.

Reinicie a API com `Ctrl+C` e o comando acima se alterar o `.env`.

### Terminal 2 — Simulador de comandos

```bash
cd ~/Projetos/futebol
source .venv/bin/activate
read -rsp "Chave da API: " BOT_API_KEY
export BOT_API_KEY
echo
python -m app.adapters.terminal \
  --url http://127.0.0.1:8001 \
  --group whatsapp-teste \
  --player admin \
  --name "Organizador"
```

No pedido de chave, digite o valor de `BOT_API_KEY` do `.env`, sem aspas.
Ele não aparece na tela. O adaptador de terminal **não carrega o .env sozinho**.
A variável exportada vale para esse terminal; informe-a novamente em outro.

No prompt `>`, envie um comando por vez (não inclua o próprio `>`):

```text
!abrir
!lista
!valor
!financeiro
```

Se já houver uma partida ativa nesse grupo, consulte `!lista` em vez de abrir
outra. Encerre com `/sair`. `!sair` é um comando do bot para cancelar inscrição;
`/sair` fecha o simulador.

Para simular outro jogador, após sair do simulador:

```bash
python -m app.adapters.terminal \
  --url http://127.0.0.1:8001 \
  --group whatsapp-teste \
  --player carlos \
  --name "Carlos"
```

Envie `!vou` para linha, `!gol` para goleiro ou `!frequencia` para histórico.
O simulador gera um ID novo a cada entrada e preserva o ID ao reenviar uma
mensagem após falha de conexão.

### Terminal 3 — Protótipo do WhatsApp Web

A API do Terminal 1 deve estar rodando. Execute somente uma instância deste
adaptador por vez:

```bash
cd ~/Projetos/futebol
source .venv/bin/activate
python -m app.adapters.whatsapp_web \
  --api-url http://127.0.0.1:8001 \
  --group-id whatsapp-teste
```

O código atual abre o grupo cujo nome visível é **Teste**. O argumento
`--group-id` define o grupo interno na API; ele não muda a conversa selecionada
no navegador. O seletor do nome visível está em `app/adapters/whatsapp_web.py`.

1. Na primeira execução, autentique pelo QR Code e aguarde as conversas carregarem.
2. Deixe o grupo **Teste** visível na lista e pressione Enter no terminal.
3. Peça ao outro participante para enviar `!lista TESTE-RECEBIDO-001`.
4. Deixe a mensagem e seu autor visíveis; feche painéis de contato abertos.
5. Pressione Enter. O programa clica no autor, lê o telefone candidato e envia
   uma mensagem selecionada à API.
6. Se solicitar a chave, digite `BOT_API_KEY` do `.env`. Se a variável já estiver
   exportada nesse terminal, ela será reutilizada.
7. Confira a resposta no terminal e pressione Enter para fechar o navegador.

Os padrões já são `http://127.0.0.1:8001` e `whatsapp-teste`; portanto, também
é possível executar apenas:

```bash
python -m app.adapters.whatsapp_web
```

O protótipo processa **uma mensagem por execução**, com o texto de teste exato e
um autor visível. Não monitora continuamente, não processa `!vou` automaticamente
e, por padrão, **não envia respostas ao WhatsApp**. O envio controlado é opcional,
conforme descrito abaixo. A integração pelo navegador é experimental.
Use uma conta e um grupo de teste.

A sessão fica em `data/whatsapp-session`; não apague a pasta para reiniciar.
Ao repetir um evento antigo, a deduplicação retorna sua resposta original. Para
consultar uma partida aberta depois daquele evento, envie uma nova mensagem no
WhatsApp, mesmo que o texto seja igual, e deixe o autor dela visível.

### Enviar uma resposta ao grupo de teste

Mantenha a API rodando e execute o protótipo com a opção explícita de envio:

```bash
python -m app.adapters.whatsapp_web \
  --api-url http://127.0.0.1:8001 \
  --group-id whatsapp-teste \
  --send-reply
```

Após consultar a API, o programa pede que você feche o painel de contato e
confira o grupo **Teste**. Pressione Enter no terminal. O programa verifica o
nome no cabeçalho e procura um único campo de mensagem editável no rodapé.
Rascunhos existentes bloqueiam o envio para preservar seu texto.

O seletor do campo de mensagem é experimental e ainda precisa ser validado na
interface real. Se o programa disser que não encontrou o campo ou o cabeçalho,
compartilhe o erro para ajustarmos o seletor; ele não escolhe outro campo por tentativa.
A verificação por nome não distingue dois grupos com nomes idênticos. Use apenas
um grupo com o nome Teste e não navegue para outra conversa durante o envio.

O registro local `data/whatsapp-outbox.db` impede uma nova tentativa para o mesmo
par `group_id` / `message_id`, inclusive após reiniciar o programa. As tentativas
são registradas antes de preencher o campo e pressionar Enter. `submitted` significa
que o Enter foi executado; não comprova entrega nem leitura. `reserved` e
`uncertain` também bloqueiam reenvio automático, pois o resultado pode ser incerto.
Confira visualmente o grupo. Não apague o registro para forçar reenvio: ele é a
proteção contra duplicação. O registro é local a esta instalação; preserve o
mesmo grupo interno e a pasta de dados entre execuções.

Essa opção envia somente a resposta da mensagem selecionada. Ela não ativa
leitura contínua nem processamento de outros comandos do WhatsApp. Sem
`--send-reply`, o comportamento continua sendo mostrar a resposta no terminal.

### Encerrar

- Adaptador de terminal: `/sair`.
- Adaptador WhatsApp: Enter no pedido final.
- API: `Ctrl+C` no Terminal 1.

Os dados permanecem no SQLite após encerrar os programas.

### Problemas comuns

| Problema | Como resolver |
|---|---|
| `python` não encontrado | Execute `source .venv/bin/activate` no terminal atual. |
| HTTP 401 / chave inválida | Use a mesma chave da API; exporte `BOT_API_KEY` no terminal do simulador. Reinicie a API se editou o `.env`. |
| Apenas administradores podem executar | Confira se `--player` ou `player_id` está em `ADMIN_IDS`. |
| HTTP 404 com HTML | Confira a porta e a URL; use 8001 na API e nos adaptadores. |
| Conexão recusada | Inicie a API e confira `/health`. |
| Porta 8001 ocupada | Use outra porta em `--port`, `--url` e `--api-url`, mantendo os três consistentes. |
| Navegador informa sessão existente | Encerre a execução anterior do adaptador e sua janela Chromium; não use duas instâncias com o mesmo perfil. |
| Nenhuma partida ativa | Abra a partida no mesmo `group_id` consultado. |
| Resposta antiga ao repetir mensagem | Envie um evento novo; a resposta anterior fica armazenada por ID. |
| Mensagem sem autor visível | Deixe uma mensagem com autor carregada; o protótipo não infere o remetente de mensagens agrupadas. |

## Arquitetura e próximos passos

- `app/main.py`: API e autenticação do simulador.
- `app/bot.py`: comandos e regras.
- `app/billing.py`: mensalidades e relatórios mensais.
- `app/adapters/terminal.py`: simulador HTTP pelo terminal.
- `app/adapters/whatsapp_web.py`: protótipo de leitura pelo navegador.
- `app/database.py`: schema e transações SQLite. `BEGIN IMMEDIATE` serializa
  alterações para impedir excesso de vagas com solicitações simultâneas.
- `tests/`: verificação dos fluxos e concorrência.

O endpoint é um simulador: quem possui a chave pode informar qualquer jogador.
Use-o localmente. Antes de expor em rede, um adaptador autenticado deve obter
identidade e grupo diretamente do provedor, sem aceitar IDs informados por jogadores.
Sem `BOT_API_KEY`, o endpoint fica sem autenticação para desenvolvimento local.

O adaptador experimental já encaminha uma mensagem selecionada do WhatsApp à API
local e mostra a resposta no terminal. Leitura contínua, identificação de mensagens
sem autor visível, recorrência e lembretes ainda não foram implementados. O envio
controlado de uma resposta ao grupo Teste está disponível com `--send-reply`. Não publique este simulador diretamente como webhook de produção.

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

### Abertura semanal simplificada

O futebol acontece às **quintas-feiras, às 19h, no horário de São Paulo**.
Basta o administrador enviar `!abrir`, em qualquer dia anterior ao próximo jogo:

- Segunda a quarta: abre a quinta daquela semana.
- Quinta antes das 19h: abre o jogo do mesmo dia.
- Quinta a partir das 19h, sexta, sábado ou domingo: abre a próxima quinta.
- Padrões: 18 vagas de linha, duas de goleiro e R$ 13,00 por avulso.
- Não é criada uma segunda partida enquanto houver uma ativa; encerre a anterior
  com os registros de presença/falta e `!encerrar`.

A data é calculada quando o comando é processado; não há abertura automática
por agendamento. As partidas existentes mantêm suas datas e valores.

Para uma exceção, o formato completo continua disponível:

```text
!abrir 2026-10-22T19:00:00-03:00 18 13.00
```

### Exemplo de abertura

O administrador envia:

```text
!abrir
```

Isso abre 18 vagas de linha e duas de goleiro.
O valor avulso por jogador de linha é R$ 13,00.

### Pagamentos e frequência

Declarar pagamento com `!paguei` não confirma o recebimento.
O administrador confirma com `!pagamento ID`.

A isenção não conta como pagamento recebido. Se alguém já pagou e depois
mudou para goleiro, o pagamento anterior permanece registrado.
Reembolsos são tratados manualmente.

Estar confirmado não significa ter comparecido.
O administrador registra `!presenca ID` ou `!falta ID` para cada confirmado.
A partida só pode ser encerrada após todos esses registros.

## Testes automatizados

Não precisam da API rodando, do WhatsApp ou de um navegador aberto. Os testes
existentes de backend usam bancos temporários e não alteram as partidas reais.

```bash
cd ~/Projetos/futebol
source .venv/bin/activate
python -m pytest -q
```

Para mostrar os nomes dos testes ou parar na primeira falha:

```bash
python -m pytest -v
python -m pytest -x --tb=short
```

## Convidados que não participam do grupo

Somente administradores podem inscrever convidados:

```text
!convidado linha Carlos Silva
!convidado gol Pedro Santos
```

O bot retorna um ID `convidado-...`, também exibido na lista junto ao ID do
administrador que cadastrou a pessoa. Guarde esse ID para administrar nomes iguais.
Cada execução cria um novo convidado: confira a lista antes de repetir o comando.
O cadastro é individual; em outra partida, um novo cadastro terá outro ID e histórico.

Convidados respeitam as vagas e a fila da função escolhida. Goleiros são isentos.
Inscrições fechadas impedem cadastrar novos convidados. Para administrar, use:

```text
!pagamento convidado-ID
!presenca convidado-ID
!falta convidado-ID
!remover convidado-ID
```

Substitua `convidado-ID` pelo identificador retornado. A remoção cancela a inscrição
na partida ativa do grupo e promove o primeiro da espera da mesma função.
Ela preserva pagamentos registrados. `!remover` é restrito a convidados;
participantes do grupo continuam usando `!sair`.

O banco existente recebe automaticamente a coluna `players.invited_by` na próxima
transação; os jogadores já cadastrados são preservados.

## Avulsos e mensalistas

O preço avulso padrão é **R$ 13,00**. Para abrir uma partida com esse valor:

```text
!abrir
```

O terceiro argumento opcional continua permitindo definir outro valor avulso
explicitamente. Preços e pagamentos de partidas anteriores não são alterados.

O administrador cadastra o jogador como mensalista **para um mês específico**:

```text
!mensalista carlos 2026-10
!mensalidade carlos 2026-10
```

O primeiro comando cria a cobrança de R$ 50,00; o segundo confirma o recebimento.
O jogador deve estar cadastrado no grupo (basta ter enviado um comando).
Esses comandos funcionam mesmo sem partida ativa. A modalidade não renova
automaticamente: cadastre o próximo mês explicitamente.

A mensalidade cobre todos os jogos do mês calendário, inclusive meses com cinco
jogos. A referência é o mês da data da partida, com o deslocamento de horário
informado na abertura, e não a data em que o pagamento é recebido.
Mensalistas precisam confirmar presença e entram na espera normalmente.
Mensalidade pendente não bloqueia inscrição; aparece como dívida mensal de R$ 50,
sem cobrança avulsa adicional. `!paguei` de um mensalista confirmado declara a
mensalidade da partida; a confirmação usa `!mensalidade ID AAAA-MM`.
`!pagamento ID` continua exclusivo para pagamentos avulsos.

Goleiros continuam isentos da partida e não recebem cobrança mensal automática.
Não cadastre goleiros isentos como mensalistas: o cadastro mensal é uma obrigação
explícita de R$ 50, independente do número de inscrições ou cancelamentos.
Não há conversão, desconto proporcional, estorno ou compensação automática.
Se já houver avulso pago no mês, o cadastro mensal é recusado para evitar
converter ou perder o recebimento anterior silenciosamente.

`!financeiro` mostra avulsos da partida e, em seção separada, mensalidades do mês.
`!financeiro 2026-10` consulta somente mensalidades, inclusive sem partida ativa.
O total mensal é do mês inteiro e não deve ser somado novamente por partida.
Convidados também podem ser cadastrados como mensalistas pelo ID gerado; lembre
que um novo cadastro de convidado gera outra identidade.

O banco ganha a tabela `memberships` automaticamente; inscrições, histórico e
respostas já armazenadas para deduplicação são preservados.
