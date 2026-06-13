from datetime import datetime, timedelta
from config import LIMIT
from db_helper import (
    get_all_active_members, get_payments_for_week, get_corrections_for_week,
    get_carryover_debt, set_carryover_debt, is_week_off, get_member_info
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Obliczenia zaczynają się od tego tygodnia
START_DATE = datetime(2026, 6, 2)  # poniedziałek tygodnia 02.06–08.06


def get_current_week_start() -> datetime:
    now = datetime.now()
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def get_all_weeks_since_start() -> list:
    """Zwróć listę wszystkich tygodni od START_DATE do dziś"""
    weeks = []
    week = START_DATE
    current = get_current_week_start()
    while week <= current:
        weeks.append(week)
        week += timedelta(days=7)
    return weeks


def calculate_week(week_start: datetime) -> dict:
    members = get_all_active_members()
    payments = get_payments_for_week(week_start)
    corrections = get_corrections_for_week(week_start)
    logger.info(f"📅 Tydzień: {week_start.strftime('%d.%m.%Y')} | Wpłaty: {payments}")

    results = {}
    for nick in members:
        member_info = get_member_info(nick)
        if member_info and member_info['join_date']:
            join_date = member_info['join_date']
            week_joined = (join_date - timedelta(days=join_date.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            if week_start < week_joined:
                continue

        prev_debt = get_carryover_debt(nick, week_start)
        payment_raw = payments.get(nick, 0)
        correction_total = sum(c.amount for c in corrections.get(nick, []))
        total = payment_raw + correction_total + prev_debt

        results[nick] = {
            "payment": payment_raw,
            "correction": correction_total,
            "carryover_in": prev_debt,
            "total": total,
        }

        next_week = week_start + timedelta(days=7)
        set_carryover_debt(nick, next_week, total - LIMIT)

    return results


def recalculate_all():
    """Przelicz wszystkie tygodnie od START_DATE (buduje carryover chain)"""
    weeks = get_all_weeks_since_start()
    logger.info(f"🔄 Przeliczam {len(weeks)} tygodni od {START_DATE.strftime('%d.%m.%Y')}")
    for week in weeks:
        if not is_week_off(week):
            calculate_week(week)


def build_ranking_content() -> str:
    # Najpierw przelicz wszystkie tygodnie żeby carryover był aktualny
    recalculate_all()

    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=6)
    zakres = f"{week_start.strftime('%d.%m')} — {week_end.strftime('%d.%m.%Y')}"

    results = calculate_week(week_start)

    if not results:
        return f"## 💎 RANKING GEM — {zakres}\n\nBrak danych."

    sorted_members = sorted(results.items(), key=lambda x: x[1]['total'], reverse=True)

    lines = [f"## 💎 RANKING GEM — {zakres}", f"**Wymagane: {LIMIT} 💎 / tydzień**\n"]

    ok, partial, zero = [], [], []
    for nick, data in sorted_members:
        total = data['total']
        carry = data['carryover_in']

        bar = max(0, min(int(total), LIMIT))
        bar_str = "█" * bar + "░" * (LIMIT - bar)

        extras = []
        if carry > 0:
            extras.append(f"nadpłata +{int(carry)}💎")
        elif carry < 0:
            extras.append(f"dług {int(carry)}💎")
        extra_str = f" *({', '.join(extras)})*" if extras else ""

        if total >= LIMIT:
            line = f"✅ **{nick}** — {int(total)}/{LIMIT} 💎 `[{bar_str}]`{extra_str}"
            ok.append(line)
        elif total > 0:
            line = f"🔸 **{nick}** — {int(total)}/{LIMIT} 💎 `[{bar_str}]`{extra_str}"
            partial.append(line)
        else:
            debt_str = f" (dług {int(total)}💎)" if total < 0 else ""
            line = f"❌ **{nick}** — 0/{LIMIT} 💎 `[{bar_str}]`{debt_str}{extra_str}"
            zero.append(line)

    if ok:
        lines.append("**✅ Zapłacone:**")
        lines.extend(ok)
        lines.append("")
    if partial:
        lines.append("**🔸 Częściowo:**")
        lines.extend(partial)
        lines.append("")
    if zero:
        lines.append("**❌ Brak wpłaty:**")
        lines.extend(zero)
        lines.append("")

    lines.append(f"⏱️ *Ostatnia aktualizacja: {datetime.now().strftime('%d.%m.%Y %H:%M')}*")

    content = "\n".join(lines)
    if len(content) > 2000:
        content = content[:1990] + "..."
    return content


# kept for backward compat
def run_week_calc_and_send(week_start: datetime):
    pass
