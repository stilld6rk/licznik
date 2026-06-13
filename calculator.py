import requests
from datetime import datetime, timedelta
from config import WEBHOOK_URL, LIMIT, GOLD, ORANGE, RED, GREEN, WHITE
from db_helper import (
    get_all_active_members, get_payments_for_week, get_corrections_for_week,
    get_carryover_debt, set_carryover_debt, get_pinned_message_id, save_pinned_message_id,
    is_week_off, get_all_weeks, get_member_info
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_current_week_start() -> datetime:
    now = datetime.now()
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def calculate_week(week_start: datetime) -> dict:
    """Oblicz wpłaty dla danego tygodnia"""
    members = get_all_active_members()
    payments = get_payments_for_week(week_start)
    corrections = get_corrections_for_week(week_start)

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

        if total >= LIMIT:
            next_carryover = total - LIMIT
        else:
            next_carryover = total - LIMIT  # negative = debt

        results[nick] = {
            "payment": payment_raw,
            "correction": correction_total,
            "carryover_in": prev_debt,
            "total": total,
        }

        next_week = week_start + timedelta(days=7)
        set_carryover_debt(nick, next_week, next_carryover)

    return results


def build_ranking_content() -> str:
    """Zbuduj treść przypiętej wiadomości rankingowej"""
    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=6)
    zakres = f"{week_start.strftime('%d.%m')} — {week_end.strftime('%d.%m.%Y')}"

    results = calculate_week(week_start)

    if not results:
        return f"## 💎 RANKING GEM — {zakres}\n\nBrak danych."

    # Sortuj: najwięcej wpłacono najpierw
    sorted_members = sorted(results.items(), key=lambda x: x[1]['total'], reverse=True)

    lines = [f"## 💎 RANKING GEM — {zakres}\n", f"**Wymagane: {LIMIT} 💎 / tydzień**\n"]

    ok, partial, zero = [], [], []
    for nick, data in sorted_members:
        total = data['total']
        paid = int(data['payment'] + data['correction'])
        carry = data['carryover_in']

        bar = min(int(total), LIMIT)
        bar_str = "█" * bar + "░" * (LIMIT - bar) if bar >= 0 else "░" * LIMIT

        extras = []
        if carry > 0:
            extras.append(f"nadpłata +{int(carry)}💎")
        elif carry < 0:
            extras.append(f"dług {int(carry)}💎")

        extra_str = f" *({', '.join(extras)})*" if extras else ""

        if total >= LIMIT:
            icon = "✅"
            line = f"{icon} **{nick}** — {int(total)}/{LIMIT} 💎 `[{bar_str}]`{extra_str}"
            ok.append(line)
        elif total > 0:
            icon = "🔸"
            line = f"{icon} **{nick}** — {int(total)}/{LIMIT} 💎 `[{bar_str}]`{extra_str}"
            partial.append(line)
        else:
            icon = "❌"
            debt_str = f" (dług {int(total)}💎)" if total < 0 else ""
            line = f"{icon} **{nick}** — 0/{LIMIT} 💎 `[{bar_str}]`{debt_str}{extra_str}"
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


def update_pinned_ranking():
    """Zaktualizuj lub stwórz przypiętą wiadomość rankingową"""
    if is_week_off(get_current_week_start()):
        logger.info("⏭️  Tydzień wyłączony, pomijam aktualizację")
        return

    content = build_ranking_content()
    msg_id = get_pinned_message_id()

    if msg_id:
        response = requests.patch(
            f"{WEBHOOK_URL}/messages/{msg_id}",
            json={"content": content}
        )
        if response.status_code == 200:
            logger.info(f"✏️  Zaktualizowano przypiętą wiadomość {msg_id}")
        else:
            logger.warning(f"⚠️  Nie można zaktualizować ({response.status_code}), tworzę nową")
            msg_id = None

    if not msg_id:
        response = requests.post(
            f"{WEBHOOK_URL}?wait=true",
            json={"content": content}
        )
        if response.status_code in (200, 204):
            new_id = response.json()['id']
            save_pinned_message_id(new_id)
            logger.info(f"📤 Wysłano nową przypiętą wiadomość {new_id}")
        else:
            logger.error(f"❌ Błąd wysyłania: {response.status_code} {response.text}")


# kept for backward compat with sync_scrape_command
def run_week_calc_and_send(week_start: datetime):
    update_pinned_ranking()
