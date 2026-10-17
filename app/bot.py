from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.billing import CASUAL_PRICE, manage_membership, membership, monthly_report, valid_month

HELP = (
    "Comandos: !vou, !gol, !sair, !lista, !espera, !valor, !paguei, !frequencia. "
    "Admin: !abrir (próxima quinta às 19h), !fechar, !pagamento ID, "
    "!presenca ID, !falta ID, !financeiro, !encerrar, "
    "!convidado linha|gol NOME, !remover ID, "
    "!mensalista ID AAAA-MM, !mensalidade ID AAAA-MM, !financeiro [AAAA-MM]."
)
ADMIN = {
    "!mensalista",
    "!mensalidade",
    "!convidado",
    "!remover",
    "!abrir",
    "!fechar",
    "!pagamento",
    "!presenca",
    "!falta",
    "!financeiro",
    "!encerrar",
}


def next_match_start(now=None):
    timezone = ZoneInfo("America/Sao_Paulo")
    now = datetime.now(timezone) if now is None else now.astimezone(timezone)
    days = (3 - now.weekday()) % 7
    starts_at = (now + timedelta(days=days)).replace(
        hour=19, minute=0, second=0, microsecond=0
    )
    if starts_at <= now:
        starts_at += timedelta(days=7)
    return starts_at


def handle(db, message, is_admin):
    group, player = message.group_id, message.player_id
    parts = message.text.strip().split()
    command = parts[0].lower() if parts else ""
    args = parts[1:]
    if command in ADMIN and not is_admin:
        return "Apenas administradores podem executar esse comando."
    name = message.name.strip() if message.name else ""
    db.execute(
        """
        INSERT INTO players (group_id, player_id, name)
        VALUES (?, ?, ?)
        ON CONFLICT(group_id, player_id)
        DO UPDATE SET name = CASE
            WHEN ? != '' THEN excluded.name
            ELSE players.name
        END
        """,
        (group, player, name or player, name),
    )
    match = db.execute(
        "SELECT * FROM matches WHERE group_id=? AND status!='finished'", (group,)
    ).fetchone()
    if command == "!abrir":
        if match:
            return "Já existe uma partida ativa neste grupo."
        try:
            if not args:
                date = next_match_start()
                capacity = 18
                price = Decimal(CASUAL_PRICE) / 100
            elif len(args) in {2, 3}:
                date = datetime.fromisoformat(args[0])
                if date.tzinfo is None:
                    raise ValueError
                capacity = int(args[1])
                price = (
                    Decimal(args[2].replace(",", "."))
                    if len(args) == 3 else Decimal(CASUAL_PRICE) / 100
                )
            else:
                raise ValueError
            if (
                capacity < 1
                or capacity > 18
                or not price.is_finite()
                or price < 0
                or price > 100000
                or price != price.quantize(Decimal(".01"))
            ):
                raise ValueError
        except (ValueError, InvalidOperation):
            return "Use: !abrir ou !abrir DATA_ISO VAGAS [VALOR_AVULSO]"
        db.execute(
            "INSERT INTO matches(group_id,starts_at,capacity,price,status) VALUES (?,?,?,?,'open')",
            (group, date.isoformat(), capacity, int(price * 100)),
        )
        return (
            f"⚽ Partida aberta! {date:%d/%m/%Y às %H:%M} ({date:%z}).\n"
            f"Linha: {capacity} vagas | Goleiros: 2 vagas\n"
            f"Avulso: R$ {price:.2f} | Mensalidade: R$ 50.00\n"
            "Digite !vou para linha ou !gol para goleiro."
        )

    if command in {"!mensalista", "!mensalidade"}:
        return manage_membership(db, group, args, confirm=command == "!mensalidade")

    if command == "!financeiro" and args:
        if len(args) != 1 or not valid_month(args[0]):
            return "Use: !financeiro AAAA-MM"
        return monthly_report(db, group, args[0])

    if command == "!frequencia":
        row = db.execute(
            "SELECT COUNT(*) total, COALESCE(SUM(r.attended),0) present "
            "FROM registrations r "
            "JOIN matches m ON m.id=r.match_id "
            "WHERE m.group_id=? AND r.player_id=? "
            "AND m.status='finished' AND r.attended IS NOT NULL",
            (group, player),
        ).fetchone()

        return (
            f"Presenças: {row['present']}/{row['total']} "
            "partidas com frequência registrada."
        )

    if (
        command
        not in {
            "!vou",
            "!gol",
            "!sair",
            "!lista",
            "!espera",
            "!valor",
            "!paguei",
        }
        | ADMIN
    ):
        return HELP

    if not match:
        return "⚽ Nenhuma partida ativa. Peça ao administrador para usar !abrir."

    mid = match["id"]
    month = match["starts_at"][:7]

    rows = db.execute(
        """
        SELECT r.*, p.name, p.invited_by
        FROM registrations AS r
        JOIN players AS p
          ON p.player_id = r.player_id
         AND p.group_id = ?
        WHERE r.match_id = ?
        ORDER BY r.id
        """,
        (group, mid),
    ).fetchall()

    confirmed = [row for row in rows if row["status"] == "confirmed"]

    waiting = [row for row in rows if row["status"] == "waiting"]

    mine = next(
        (row for row in rows if row["player_id"] == player),
        None,
    )

    if command in {"!vou", "!gol", "!convidado"}:
        if match["status"] != "open":
            return "As inscrições estão fechadas."

        if command != "!convidado" and mine and mine["status"] != "cancelled":
            return (
                "Você já está na lista. "
                "Para mudar de função, use !sair e se inscreva novamente."
            )

        guest_name = None
        if command == "!convidado":
            if len(args) < 2 or args[0].lower() not in {"linha", "gol"}:
                return "Use: !convidado linha|gol NOME"
            guest_name = " ".join(args[1:])
            if len(guest_name) > 100:
                return "O nome do convidado deve ter até 100 caracteres."
            role = "goalkeeper" if args[0].lower() == "gol" else "line"
            player = f"convidado-{uuid4().hex}"
            db.execute(
                "INSERT INTO players(group_id,player_id,name,invited_by) VALUES (?,?,?,?)",
                (group, player, guest_name, message.player_id),
            )
        else:
            role = "goalkeeper" if command == "!gol" else "line"
        exempt = int(role == "goalkeeper")

        capacity = (
            match["goalkeeper_capacity"] if role == "goalkeeper" else match["capacity"]
        )

        occupied = sum(row["role"] == role for row in confirmed)

        status = "confirmed" if occupied < capacity else "waiting"
        if command == "!convidado":
            mine = None
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
                payment,
                role,
                exempt
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (mid, player, status, payment, role, exempt),
        )

        if guest_name is not None:
            situation = "confirmado" if status == "confirmed" else "na fila de espera"
            function = "goleiro (isento)" if role == "goalkeeper" else "linha"
            return f"{guest_name}: {situation} como {function}.\nID: {player}"

        if status == "confirmed":
            if role == "goalkeeper":
                return "🧤 Presença confirmada como goleiro! Você está isento."

            return "✅ Presença confirmada!"

        if role == "goalkeeper":
            return "Você entrou na fila de espera de goleiros."

        return "Você entrou na fila de espera de jogadores de linha."

    if command in {"!lista", "!espera"}:
        selected = confirmed if command == "!lista" else waiting
        match_date = datetime.fromisoformat(match["starts_at"]).strftime("%d/%m/%Y")

        sections = [
            f"⚽ Fut Arena Mineiro 19hrs {match_date}",
            "Confirmados" if command == "!lista" else "Fila de espera",
        ]

        for role, label, capacity in (
            ("line", "Linha", match["capacity"]),
            ("goalkeeper", "Goleiros — isentos", match["goalkeeper_capacity"]),
        ):
            players = [row for row in selected if row["role"] == role]

            heading = (
                f"{label}: {len(players)}/{capacity}"
                if command == "!lista"
                else f"{label}: {len(players)} aguardando"
            )

            lines = [
                f"{position}. {row['name']} ({row['player_id']})"
                + (f" — convidado por {row['invited_by']}" if row["invited_by"] else "")
                for position, row in enumerate(players, start=1)
            ]

            sections.append(heading)
            sections.append("\n".join(lines) if lines else "Lista vazia.")

        return "\n".join(sections)

    if command in {"!sair", "!remover"}:
        if command == "!remover":
            if len(args) != 1:
                return "Use: !remover ID_DO_CONVIDADO"
            mine = next((row for row in rows if row["player_id"] == args[0]
                         and row["invited_by"] is not None), None)
            if not mine or mine["status"] == "cancelled":
                return "Convidado não encontrado na lista desta partida."
        if not mine or mine["status"] == "cancelled":
            return "Você não está inscrito."
        db.execute(
            "UPDATE registrations SET status='cancelled',attended=NULL WHERE id=?",
            (mine["id"],),
        )
        same_role_waiting = [row for row in waiting if row["role"] == mine["role"]]
        if mine["status"] == "confirmed" and same_role_waiting:
            promoted = same_role_waiting[0]
            db.execute(
                "UPDATE registrations SET status='confirmed' WHERE id=?",
                (promoted["id"],),
            )
            return f"Inscrição cancelada. {promoted['name']} ({promoted['player_id']}) foi promovido da espera."
        return "Inscrição cancelada."

    if command == "!valor":
        return (
            f"Valor por jogador de linha: R$ {match['price'] / 100:.2f}\n"
            "Mensalidade: R$ 50.00 por mês calendário, sem reserva de vaga.\n"
            "Goleiros são isentos."
        )
    if command == "!paguei":
        if not mine or mine["status"] != "confirmed":
            return "Você precisa estar na lista de confirmados."
        if mine["exempt"]:
            return "Você está isento do pagamento desta partida."
        plan = membership(db, group, player, month)
        if plan:
            if plan["payment"] == "paid":
                return f"Sua mensalidade de {month} já foi confirmada."
            db.execute("UPDATE memberships SET payment='declared' WHERE group_id=? AND player_id=? AND month=?",
                       (group, player, month))
            return f"Mensalidade de {month} informada. Aguardando confirmação do administrador."
        if mine["payment"] == "paid":
            return "Seu pagamento já foi confirmado."
        db.execute(
            "UPDATE registrations SET payment='declared' WHERE id=?", (mine["id"],)
        )
        return "Pagamento informado. Aguardando confirmação do administrador."
    if command in {"!pagamento", "!presenca", "!falta"}:
        target = next(
            (r for r in confirmed if len(args) == 1 and r["player_id"] == args[0]), None
        )
        if not target:
            return "Informe o ID de um jogador confirmado, conforme !lista."
        if command == "!pagamento":
            if target["exempt"]:
                return "Esse jogador está isento do pagamento."
            if membership(db, group, target["player_id"], month):
                return f"Este jogador é mensalista. Use !mensalidade {target['player_id']} {month}."
            db.execute(
                "UPDATE registrations SET payment='paid' WHERE id=?", (target["id"],)
            )
        else:
            db.execute(
                "UPDATE registrations SET attended=? WHERE id=?",
                (int(command == "!presenca"), target["id"]),
            )
        return "Registro atualizado."

    if command == "!financeiro":
        plans = {row["player_id"]: membership(db, group, row["player_id"], month) for row in rows}
        paid = sum(row["payment"] == "paid" for row in rows)

        debtors = [
            row for row in confirmed if not row["exempt"] and not plans[row["player_id"]] and row["payment"] != "paid"
        ]

        exempt_count = sum(bool(row["exempt"]) for row in confirmed)

        details = []

        for row in rows:
            situation = "isento" if row["exempt"] else row["payment"]

            if not row["exempt"] and plans[row["player_id"]]:
                situation = f"mensalista {month}: {plans[row['player_id']]['payment']}"

            if row["exempt"] and row["payment"] == "paid":
                situation = "isento, com pagamento anterior registrado"

            details.append(
                f"{row['name']} ({row['player_id']}): " f"{situation} / {row['status']}"
            )

        return (
            f"Recebido: R$ {paid * match['price'] / 100:.2f}\n"
            f"Pendente dos confirmados: "
            f"R$ {len(debtors) * match['price'] / 100:.2f}\n"
            f"Confirmados isentos: {exempt_count}\n" + "\n".join(details)
            + "\n\n" + monthly_report(db, group, month)
        )

    if command == "!fechar":
        db.execute("UPDATE matches SET status='closed' WHERE id=?", (mid,))
        return "Inscrições fechadas."

    if command == "!encerrar":
        if any(r["attended"] is None for r in confirmed):
            return "Registre !presenca ou !falta para todos os confirmados antes de encerrar."
        db.execute("UPDATE matches SET status='finished' WHERE id=?", (mid,))
        return "Partida encerrada. Frequência consolidada."
    return HELP
