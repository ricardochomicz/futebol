from datetime import datetime
from decimal import Decimal, InvalidOperation

HELP = ('Comandos: !vou, !sair, !lista, !espera, !valor, !paguei, !frequencia. '
        'Admin: !abrir DATA_ISO VAGAS VALOR, !fechar, !pagamento ID, '
        '!presenca ID, !falta ID, !financeiro, !encerrar.')
ADMIN = {'!abrir', '!fechar', '!pagamento', '!presenca', '!falta', '!financeiro', '!encerrar'}


def handle(db, message, is_admin):
    group, player = message.group_id, message.player_id
    parts = message.text.strip().split()
    command = parts[0].lower() if parts else ''
    args = parts[1:]
    if command in ADMIN and not is_admin:
        return 'Apenas administradores podem executar esse comando.'
    db.execute('INSERT INTO players VALUES (?,?,?) ON CONFLICT(group_id,player_id) '
               'DO UPDATE SET name=excluded.name', (group, player, message.name or player))
    match = db.execute("SELECT * FROM matches WHERE group_id=? AND status!='finished'", (group,)).fetchone()
    if command == '!abrir':
        if match:
            return 'Já existe uma partida ativa neste grupo.'
        try:
            if len(args) != 3:
                raise ValueError
            date = datetime.fromisoformat(args[0])
            if date.tzinfo is None:
                raise ValueError
            capacity = int(args[1])
            price = Decimal(args[2].replace(',', '.'))
            if capacity < 1 or capacity > 1000 or not price.is_finite() or price < 0 or price > 100000 or price != price.quantize(Decimal('.01')):
                raise ValueError
        except (ValueError, InvalidOperation):
            return 'Use: !abrir 2026-10-21T20:00:00-03:00 14 20.00'
        db.execute('INSERT INTO matches(group_id,starts_at,capacity,price,status) VALUES (?,?,?,?,\'open\')',
                   (group, date.isoformat(), capacity, int(price * 100)))
        return '⚽ Partida aberta! Digite !vou para participar.'

    if command in {"!vou", "!lista", "!espera"} and not match:
        return "⚽ Nenhuma partida ativa. Peça ao administrador para usar !abrir."

        if command in {"!vou", "!lista", "!espera"}:
        mid = match["id"]

        rows = db.execute(
            """
            SELECT r.*, p.name
            FROM registrations AS r
            JOIN players AS p
              ON p.player_id = r.player_id
             AND p.group_id = ?
            WHERE r.match_id = ?
            ORDER BY r.id
            """,
            (group, mid),
        ).fetchall()

        confirmed = [
            row for row in rows
            if row["status"] == "confirmed"
        ]

        waiting = [
            row for row in rows
            if row["status"] == "waiting"
        ]

        mine = next(
            (
                row for row in rows
                if row["player_id"] == player
            ),
            None,
        )

        if command == "!vou":
        if match["status"] != "open":
            return "As inscrições estão fechadas."

        if mine and mine["status"] != "cancelled":
            return "Você já está na lista."

        status = (
            "confirmed"
            if len(confirmed) < match["capacity"]
            else "waiting"
        )

        payment = mine["payment"] if mine else "pending"

        if mine:
            db.execute(
                "DELETE FROM registrations WHERE id = ?",
                (mine["id"],),
            )

        db.execute(
            """
            INSERT INTO registrations (
                match_id,
                player_id,
                status,
                payment
            )
            VALUES (?, ?, ?, ?)
            """,
            (mid, player, status, payment),
        )

        if status == "confirmed":
            return "✅ Presença confirmada!"

        return "Você entrou na fila de espera."

        if command in {"!lista", "!espera"}:
        if command == "!lista":
            selected = confirmed
            title = (
                f"⚽ {match['starts_at']} — "
                f"{len(confirmed)}/{match['capacity']} confirmados"
            )
        else:
            selected = waiting
            title = "Fila de espera"

        lines = [
            f"{position}. {row['name']} ({row['player_id']})"
            for position, row in enumerate(selected, start=1)
        ]

        content = "\n".join(lines) if lines else "Lista vazia."

        return f"{title}\n{content}"

    if command == '!frequencia':
        row = db.execute("SELECT COUNT(*) total, COALESCE(SUM(r.attended),0) present FROM registrations r "
                         "JOIN matches m ON m.id=r.match_id WHERE m.group_id=? AND r.player_id=? "
                         "AND m.status='finished' AND r.attended IS NOT NULL", (group, player)).fetchone()
        return f"Presenças: {row['present']}/{row['total']} partidas com frequência registrada."
    if command not in {'!vou','!sair','!lista','!espera','!valor','!paguei'} | ADMIN:
        return HELP
    if not match:
        return '⚽ Nenhuma partida ativa. Peça ao administrador para usar !abrir.'
    mid = match['id']
    rows = db.execute('SELECT r.*,p.name FROM registrations r JOIN players p ON '
                      'p.player_id=r.player_id AND p.group_id=? WHERE match_id=? ORDER BY r.id', (group, mid)).fetchall()
    confirmed = [r for r in rows if r['status'] == 'confirmed']
    waiting = [r for r in rows if r['status'] == 'waiting']
    mine = next((r for r in rows if r['player_id'] == player), None)
    if command == '!vou':
        if match['status'] != 'open':
            return 'As inscrições estão fechadas.'
        if mine and mine['status'] != 'cancelled':
            return 'Você já está na lista.'
        status = 'confirmed' if len(confirmed) < match['capacity'] else 'waiting'
        if mine:
            # Rejoining goes to the end of the queue; preserve recorded payments.
            db.execute('DELETE FROM registrations WHERE id=?', (mine['id'],))
        db.execute('INSERT INTO registrations(match_id,player_id,status,payment) VALUES (?,?,?,?)',
                   (mid, player, status, mine['payment'] if mine else 'pending'))
        return '✅ Presença confirmada!' if status == 'confirmed' else 'Você entrou na fila de espera.'
    if command == '!sair':
        if not mine or mine['status'] == 'cancelled':
            return 'Você não está inscrito.'
        db.execute("UPDATE registrations SET status='cancelled',attended=NULL WHERE id=?", (mine['id'],))
        if mine['status'] == 'confirmed' and waiting:
            promoted = waiting[0]
            db.execute("UPDATE registrations SET status='confirmed' WHERE id=?", (promoted['id'],))
            return f"Inscrição cancelada. {promoted['name']} ({promoted['player_id']}) foi promovido da espera."
        return 'Inscrição cancelada.'
    if command in {'!lista', '!espera'}:
        selected = confirmed if command == '!lista' else waiting
        title = f"⚽ {match['starts_at']} — {len(confirmed)}/{match['capacity']} confirmados" if command == '!lista' else 'Fila de espera'
        return title + '\n' + ('\n'.join(f"{i}. {r['name']} ({r['player_id']})" for i, r in enumerate(selected, 1)) or 'Lista vazia.')
    if command == '!valor':
        return f"Valor por jogador: R$ {match['price']/100:.2f}"
    if command == '!paguei':
        if not mine or mine['status'] != 'confirmed':
            return 'Você precisa estar na lista de confirmados.'
        if mine['payment'] == 'paid':
            return 'Seu pagamento já foi confirmado.'
        db.execute("UPDATE registrations SET payment='declared' WHERE id=?", (mine['id'],))
        return 'Pagamento informado. Aguardando confirmação do administrador.'
    if command in {'!pagamento','!presenca','!falta'}:
        target = next((r for r in confirmed if len(args) == 1 and r['player_id'] == args[0]), None)
        if not target:
            return 'Informe o ID de um jogador confirmado, conforme !lista.'
        if command == '!pagamento':
            db.execute("UPDATE registrations SET payment='paid' WHERE id=?", (target['id'],))
        else:
            db.execute('UPDATE registrations SET attended=? WHERE id=?', (int(command == '!presenca'), target['id']))
        return 'Registro atualizado.'
    if command == '!financeiro':
        # Include payments from cancellations so receipts do not disappear.
        paid = sum(r['payment'] == 'paid' for r in rows)
        details = '\n'.join(f"{r['name']} ({r['player_id']}): {r['payment']} / {r['status']}" for r in rows)
        return f"Recebido: R$ {paid * match['price']/100:.2f}\n" + details
    if command == '!fechar':
        db.execute("UPDATE matches SET status='closed' WHERE id=?", (mid,))
        return 'Inscrições fechadas.'
    if command == '!encerrar':
        if any(r['attended'] is None for r in confirmed):
            return 'Registre !presenca ou !falta para todos os confirmados antes de encerrar.'
        db.execute("UPDATE matches SET status='finished' WHERE id=?", (mid,))
        return 'Partida encerrada. Frequência consolidada.'
    return HELP
