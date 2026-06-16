from datetime import datetime, timedelta
from config import LIMIT, GUILD_NAME, GUILD_ID
from db_helper import (
    get_all_active_members, get_all_payments_grouped, get_all_corrections_grouped,
    get_corrections_with_comments, is_week_off, _get_all_member_info
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

START_DATE = datetime(2026, 6, 1)  # poniedziałek pierwszego tygodnia


def get_current_week_start() -> datetime:
    now = datetime.now()
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def get_weeks_since(start: datetime) -> list:
    weeks = []
    week = start
    current = get_current_week_start()
    while week <= current:
        weeks.append(week)
        week += timedelta(days=7)
    return weeks


def get_weeks_since_start() -> list:
    return get_weeks_since(START_DATE)


def oblicz_zaleglosci(guild_id: int = None, limit: int = None) -> tuple:
    gid = guild_id or GUILD_ID
    lim = limit or LIMIT

    lista_dc = get_all_active_members(gid)
    payments_grouped = get_all_payments_grouped(gid)
    corrections_grouped = get_all_corrections_grouped(gid)
    member_info_map = _get_all_member_info(gid)

    rankingi_per_tydzien = {}
    all_weeks = set(list(payments_grouped.keys()) + list(corrections_grouped.keys()))
    for ws in all_weeks:
        rankingi_per_tydzien[ws] = {}
        for nick in lista_dc:
            val = payments_grouped.get(ws, {}).get(nick, 0)
            val += corrections_grouped.get(ws, {}).get(nick, 0)
            rankingi_per_tydzien[ws][nick] = val

    def _join_week(nick):
        info = member_info_map.get(nick)
        if info and info.get('join_date'):
            jd = info['join_date']
            return (jd - timedelta(days=jd.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return START_DATE

    earliest = min((_join_week(n) for n in lista_dc), default=START_DATE)
    tygodnie_posortowane = get_weeks_since(min(earliest, START_DATE))
    aktywne = [t for t in tygodnie_posortowane if not is_week_off(t, gid)]

    przeniesienia = {nick: 0 for nick in lista_dc}
    wyniki = {}

    for tydzien in aktywne:
        ranking_dict = rankingi_per_tydzien.get(tydzien, {})
        wyniki[tydzien] = {}

        for nick in lista_dc:
            member_start = _join_week(nick)
            if tydzien < member_start:
                continue

            wplata_raw = ranking_dict.get(nick, 0)
            przen = przeniesienia[nick]
            efektywna = wplata_raw + przen

            if efektywna > lim:
                nadwyzka = efektywna - lim
                wyswietlana = lim
            elif efektywna <= 0:
                nadwyzka = efektywna - lim
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


def build_ranking_content(guild_id: int = None, guild_name: str = None, limit: int = None) -> str:
    gid = guild_id or GUILD_ID
    lim = limit or LIMIT
    gname = guild_name or GUILD_NAME

    wyniki, aktywne, member_info_map = oblicz_zaleglosci(gid, lim)

    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=6)
    comments_map = get_corrections_with_comments(week_start, gid)

    wyniki_tygodnia = wyniki.get(week_start, {})

    if not wyniki_tygodnia:
        zakres = f"{week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m')}"
        return f"💎 RANKING TYGODNIOWY — {gname} ({zakres})\n\nBrak danych."

    posortowani = sorted(
        wyniki_tygodnia.items(),
        key=lambda x: x[1]['ilosc_raw'] + x[1]['przeniesienie_z'],
        reverse=True
    )

    medals = ["🥇", "🥈", "🥉"]
    medal_idx = 0
    lines = [f"💎 RANKING TYGODNIOWY — {gname} ({week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m')})"]

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

        if efektywna >= lim:
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


def build_overall_ranking_content(guild_id: int = None, guild_name: str = None) -> str:
    """Suma wszystkich wpłat + korekt per gracz, od początku śledzenia."""
    gid = guild_id or GUILD_ID
    gname = guild_name or GUILD_NAME

    lista_dc = get_all_active_members(gid)
    payments_grouped = get_all_payments_grouped(gid)
    corrections_grouped = get_all_corrections_grouped(gid)
    member_info_map = _get_all_member_info(gid)

    totals = {nick: 0 for nick in lista_dc}
    for week_data in payments_grouped.values():
        for nick, val in week_data.items():
            if nick in totals:
                totals[nick] += val
    for week_data in corrections_grouped.values():
        for nick, val in week_data.items():
            if nick in totals:
                totals[nick] += val

    posortowani = sorted(totals.items(), key=lambda x: x[1], reverse=True)

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"💎 RANKING OGÓLNY — {gname} (suma od początku)"]
    for idx, (nick, total) in enumerate(posortowani):
        display = member_info_map.get(nick, {}).get('discord_nick', nick)
        ikona = medals[idx] if idx < 3 else "🔹"
        lines.append(f"{ikona} {display}: {int(total)}💎")

    footer = f"\n🕐 Stan na: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
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
