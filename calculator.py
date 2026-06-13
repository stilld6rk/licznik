import requests
from datetime import datetime, timedelta
from config import WEBHOOK_URL, LIMIT, GOLD, ORANGE, RED, GREEN, WHITE
from db_helper import (
    get_all_active_members, get_payments_for_week, get_corrections_for_week,
    get_carryover_debt, set_carryover_debt, save_weekly_message, get_weekly_message,
    is_week_off, get_all_weeks
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def calculate_debts(week_start: datetime):
    """Oblicz zaległości dla danego tygodnia"""
    members = get_all_active_members()
    payments = get_payments_for_week(week_start)
    corrections = get_corrections_for_week(week_start)
    
    results = {}
    carryover = {}
    
    from db_helper import get_member_info
    
    for nick in members:
        # Sprawdzenie daty dołączenia
        member_info = get_member_info(nick)
        if member_info and member_info['join_date']:
            join_date = member_info['join_date']
            # Poniedziałek tygodnia w którym dołączył
            week_joined = (join_date - timedelta(days=join_date.weekday())).replace(hour=0, minute=0, second=0)
            
            # Jeśli tydzień jest przed datą dołączenia, pomijamy
            if week_start < week_joined:
                continue
        # Pobrań poprzedni dług
        prev_debt = get_carryover_debt(nick, week_start)
        
        # Wpłaty
        payment_raw = payments.get(nick, 0)
        
        # Korekty
        correction_total = 0
        if nick in corrections:
            for corr in corrections[nick]:
                correction_total += corr.amount
        
        total = payment_raw + correction_total + prev_debt
        
        # Logika limitu
        if total > LIMIT:
            displayed = LIMIT
            next_carryover = total - LIMIT
        elif total <= 0:
            displayed = 0
            next_carryover = total - LIMIT
        else:
            displayed = total
            next_carryover = 0
        
        # Status
        if prev_debt > 0:
            status = f"NadD +{prev_debt}"
            color = ORANGE
        elif prev_debt < 0:
            status = f"NieD {prev_debt}"
            color = RED
        else:
            status = ""
            color = WHITE
        
        results[nick] = {
            "payment": payment_raw,
            "correction": correction_total,
            "carryover_in": prev_debt,
            "displayed": displayed,
            "carryover_out": next_carryover,
            "status": status,
            "color": color,
        }
        
        # Zapisz następny przeniesiony dług
        next_week = week_start + timedelta(days=7)
        set_carryover_debt(nick, next_week, next_carryover)
    
    return results


def send_to_discord(week_start: datetime, results: dict, comments: dict = None):
    """Wyślij ranking na Discord"""
    
    if is_week_off(week_start):
        logger.info(f"⏭️  Tydzień wyłączony, pomijam")
        return
    
    if comments is None:
        comments = {}
    
    # Sortuj po wpłatach + przeniesieniu
    sorted_members = sorted(
        results.items(),
        key=lambda x: x[1]['payment'] + x[1]['carryover_in'],
        reverse=True
    )
    
    lines = []
    zakres = f"{week_start.strftime('%d.%m')} - {(week_start + timedelta(days=6)).strftime('%d.%m')}"
    lines.append(f"## 💎 RANKING TYGODNIOWY ({zakres})\n")
    
    for i, (nick, data) in enumerate(sorted_members):
        total_status = data['payment'] + data['carryover_in']
        
        # Ikona
        if i == 0 and total_status > 0:
            icon = "🥇"
        elif i == 1 and total_status > 0:
            icon = "🥈"
        elif i == 2 and total_status > 0:
            icon = "🥉"
        elif total_status <= 0:
            icon = "○"
        else:
            icon = "🔹"
        
        # Szczegóły
        details = [f"wpłacono {int(data['payment'])}💎"]
        if data['carryover_in'] > 0:
            details.append(f"NadD +{int(data['carryover_in'])}")
        elif data['carryover_in'] < 0:
            details.append(f"NieD {int(data['carryover_in'])}")
        
        details_str = " | ".join(details)
        status_str = f"{int(total_status)}💎"
        
        comment_str = f" - {comments.get(nick, '')}" if nick in comments else ""
        
        lines.append(f"{icon} **{nick}**: {status_str} ({details_str}){comment_str}\n")
    
    lines.append(f"\n⏱️ *{datetime.now().strftime('%d.%m.%Y %H:%M')}*")
    lines.append("\n`NadD`=nadpłata | `NieD`=dług z poprzedniego tygodnia")
    
    content = "".join(lines)
    
    # Sprawdzenie długości
    if len(content) > 2000:
        logger.warning(f"⚠️  Wiadomość przekracza 2000 znaków!")
        content = content[:1990] + "..."
    
    # Aktualizuj lub wyślij nową
    existing_msg = get_weekly_message(week_start)
    
    if existing_msg:
        # Aktualizuj
        response = requests.patch(
            f"{WEBHOOK_URL}/messages/{existing_msg}",
            json={"content": content}
        )
        if response.status_code == 200:
            logger.info(f"✏️  Zaktualizowano wiadomość {existing_msg}")
        else:
            logger.error(f"❌ Błąd aktualizacji: {response.status_code}")
    else:
        # Wyślij nową
        response = requests.post(
            f"{WEBHOOK_URL}?wait=true",
            json={"content": content}
        )
        if response.status_code in (200, 204):
            msg_id = response.json()['id']
            save_weekly_message(week_start, msg_id)
            logger.info(f"📤 Wysłano nową wiadomość {msg_id}")
        else:
            logger.error(f"❌ Błąd wysyłania: {response.status_code}")


def run_week_calc_and_send(week_start: datetime):
    """Oblicz zaległości i wyślij na Discord"""
    logger.info(f"📊 Obliczam zaległości dla {week_start.strftime('%d.%m')}")
    
    results = calculate_debts(week_start)
    send_to_discord(week_start, results)


def update_all_weeks():
    """Zaktualizuj wszystkie tygodnie"""
    weeks = get_all_weeks()
    logger.info(f"🔄 Aktualizuję {len(weeks)} tygodni")
    
    for week_start in weeks:
        run_week_calc_and_send(week_start)
