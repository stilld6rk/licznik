from datetime import datetime, timedelta
from config import LIMIT, GUILD_NAME
from db_helper import (
    get_all_active_members, get_all_payments_grouped, get_all_corrections_grouped,
    get_corrections_with_comments, is_week_off
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

START_DATE = datetime(2026, 6, 1)  # poniedziałek pierwszego tygodnia


def get_current_week_start() -> datetime:
    now = datetime.now()
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def get_weeks_since_start() -> list:
    weeks = []
    week = START_DATE
    current = get_current_week_start()
    while week <= current:
        weeks.append(week)
        week += timedelta(days=7)
    return weeks


def _get_all_member_info() -> dict:
    """Batch fetch wszystkich info o członkach {nick: info}"""
    from database import get_session, GuildMember
    from config import GUILD_ID
    session = get_session()
    try:
        members = session.query(GuildMember).filter(
            GuildMember.guild_id == GUILD_ID,
            GuildMember.is_active == True,
            GuildMember.discord_id.isnot(None)
        ).all()
        return {
            m.nick: {
                'join_date': m.join_date,
                'discord_nick': m.discord_nick or m.nick,
            }
            for m in members
        }
    finally:
        session.close()


def oblicz_zaleglosci() -> tuple:
    """
    Identyczna logika jak w oryginalnym skrypcie.
    Zwraca (wyniki_per_tydzien, aktywne_tygodnie).
    """
    lista_dc = get_all_active_members()
    payments_grouped = get_all_payments_grouped()
    corrections_grouped = get_all_corrections_grouped()
    member_info_map = _get_all_member_info()

    # Połącz payments + corrections per week+nick
    rankingi_per_tydzien = {}
    all_weeks = set(list(payments_grouped.keys()) + list(corrections_grouped.keys()))
    for ws in all_weeks:
        rankingi_per_tydzien[ws] = {}
        for nick in lista_dc:
            val = payments_grouped.get(ws, {}).get(nick, 0)
            val += corrections_grouped.get(ws, {}).get(nick, 0)
            rankingi_per_tydzien[ws][nick] = val

    tygodnie_posortowane = get_weeks_since_start()
    aktywne = [t for t in tygodnie_posortowane if not is_week_off(t)]

    # In-memory carryover — identycznie jak oryginał
    przeniesienia = {nick: 0 for nick in lista_dc}
    wyniki = {}

    for tydzien in aktywne:
        ranking_dict = rankingi_per_tydzien.get(tydzien, {})
        wyniki[tydzien] = {}

        for nick in lista_dc:
            # Logika daty dołączenia
            member_info = member_info_map.get(nick)
            if member_info and member_info['join_date']:
                join_date = member_info['join_date']
                start_week = (join_date - timedelta(days=join_date.weekday())).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                if tydzien < start_week:
                    continue

            wplata_raw = ranking_dict.get(nick, 0)
            przen = przeniesienia[nick]
            efektywna = wplata_raw + przen

            if efektywna > LIMIT:
                nadwyzka = efektywna - LIMIT
                wyswietlana = LIMIT
            elif efektywna <= 0:
                nadwyzka = efektywna - LIMIT
                wyswietlana = 0
            else:
                nadwyzka = 0
                wyswietlana = efektywna

            wyniki[tydzien][nick] = {
                "ilosc_raw": wplata_raw,
                "ilosc_wyswietlana": wyswietlana,
                "przeniesienie_z": przen,
                "przeniesienie_na": nadwyzka,
            }
            przeniesienia[nick] = nadwyzka

        logger.info(f"📅 {tydzien.strftime('%d.%m.%Y')} | ranking_dict: {ranking_dict}")

    return wyniki, aktywne, member_info_map


def build_ranking_content() -> str:
    wyniki, aktywne, member_info_map = oblicz_zaleglosci()

    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=6)
    comments_map = get_corrections_with_comments(week_start)

    wyniki_tygodnia = wyniki.get(week_start, {})

    if not wyniki_tygodnia:
        zakres = f"{week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m')}"
        return f"💎 RANKING TYGODNIOWY — {GUILD_NAME} ({zakres})\n\nBrak danych."

    posortowani = sorted(
        wyniki_tygodnia.items(),
        key=lambda x: x[1]['ilosc_raw'] + x[1]['przeniesienie_z'],
        reverse=True
    )

    medals = ["🥇", "🥈", "🥉"]
    medal_idx = 0
    lines = [f"💎 RANKING TYGODNIOWY — {GUILD_NAME} ({week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m')})"]

    for nick, dane in posortowani:
        ilosc_raw = int(dane['ilosc_raw'])
        przen_z = int(dane['przeniesienie_z'])
        efektywna = ilosc_raw + przen_z
        display = member_info_map.get(nick, {}).get('discord_nick', nick)

        if przen_z > 0:
            detail = f"(wpłacono {ilosc_raw}💎 | NadD +{przen_z})"
        elif przen_z < 0:
            detail = f"(wpłacono {ilosc_raw}💎 | NieD {przen_z})"
        else:
            detail = f"(wpłacono {ilosc_raw}💎)"

        if efektywna >= LIMIT:
            ikona = medals[medal_idx] if medal_idx < 3 else "🔹"
            medal_idx += 1
        elif efektywna > 0:
            ikona = "🔹"
        else:
            ikona = "○"

        lines.append(f"{ikona} {display}: {efektywna}💎 {detail}")

    footer = f"\n🕐 Ostatnia aktualizacja: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    content = "\n".join(lines)
    max_len = 2000 - len(footer)
    if len(content) > max_len:
        cutoff = content.rfind("\n", 0, max_len - 30)
        remaining = content[cutoff:].count("\n")
        content = content[:cutoff] + f"\n*... i {remaining} więcej*"
    return content + footer


# backward compat
def run_week_calc_and_send(week_start: datetime):
    pass
