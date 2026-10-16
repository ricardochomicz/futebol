"""Cobranças mensais independentes das inscrições e dos pagamentos avulsos."""
from datetime import datetime

MONTHLY_PRICE = 5000
CASUAL_PRICE = 1300


def valid_month(value):
    try:
        return len(value) == 7 and datetime.strptime(value, "%Y-%m").strftime("%Y-%m") == value
    except ValueError:
        return False


def membership(db, group, player, month):
    return db.execute(
        "SELECT * FROM memberships WHERE group_id=? AND player_id=? AND month=?",
        (group, player, month),
    ).fetchone()


def manage_membership(db, group, args, confirm=False):
    usage = "Use: !mensalidade ID AAAA-MM" if confirm else "Use: !mensalista ID AAAA-MM"
    if len(args) != 2 or not valid_month(args[1]):
        return usage
    player, month = args
    if not db.execute("SELECT 1 FROM players WHERE group_id=? AND player_id=?", (group, player)).fetchone():
        return "Jogador não encontrado neste grupo. Peça que envie um comando primeiro."
    existing = membership(db, group, player, month)
    if confirm:
        if not existing:
            return "Cadastre primeiro com !mensalista ID AAAA-MM."
        db.execute("UPDATE memberships SET payment='paid' WHERE group_id=? AND player_id=? AND month=?",
                   (group, player, month))
        return f"Mensalidade de {month} confirmada: R$ {existing['amount'] / 100:.2f}."
    if existing:
        return f"Jogador já é mensalista em {month}."
    # Never silently convert an existing receipt into a monthly payment.
    if db.execute("SELECT 1 FROM registrations r JOIN matches m ON m.id=r.match_id "
                  "WHERE m.group_id=? AND r.player_id=? AND substr(m.starts_at,1,7)=? AND r.payment='paid'",
                  (group, player, month)).fetchone():
        return "Há pagamento avulso confirmado neste mês. Resolva o acerto antes de cadastrar a mensalidade."
    db.execute("INSERT INTO memberships(group_id,player_id,month,amount,payment) VALUES (?,?,?,?, 'pending')",
               (group, player, month, MONTHLY_PRICE))
    return f"Mensalista cadastrado em {month}: R$ 50.00 pendentes. Sem reserva de vaga."


def monthly_report(db, group, month):
    rows = db.execute("SELECT s.*,p.name FROM memberships s JOIN players p "
                      "ON p.group_id=s.group_id AND p.player_id=s.player_id "
                      "WHERE s.group_id=? AND s.month=? ORDER BY p.name,s.player_id", (group, month)).fetchall()
    paid = sum(r['amount'] for r in rows if r['payment'] == 'paid')
    pending = sum(r['amount'] for r in rows if r['payment'] != 'paid')
    lines = [f"Mensalidades {month}", f"Recebido mensal: R$ {paid / 100:.2f}",
             f"Pendente mensal: R$ {pending / 100:.2f}"]
    lines.extend(f"{r['name']} ({r['player_id']}): {r['payment']} — R$ {r['amount']/100:.2f}" for r in rows)
    return '\n'.join(lines)
