import re
import io
import pandas as pd
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
from config import HARD_LOGIN, HARD_PASSWORD, HARD_PIN, GUILD_ID, ROLE_ID, DISCORD_BOT_TOKEN as BOT_TOKEN, HEADLESS
from db_helper import get_or_create_member, add_payment, get_all_active_members, _update_discord_nick, get_all_active_guild_configs, save_guild_config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def oczysc_nick_v(nick):
    if not nick:
        return nick
    return re.sub(r'[Vv]\d+$', '', str(nick)).strip()


def _resolve_discord_guild_id(ranking_channel_id: int, fallback: int = None) -> int:
    """Derive the Discord server ID from a channel ID via the API."""
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    resp = requests.get(f"https://discord.com/api/v10/channels/{ranking_channel_id}", headers=headers)
    if resp.status_code == 200:
        resolved = int(resp.json().get('guild_id', 0))
        return resolved or fallback or None
    logger.warning(f"⚠️  Nie udało się pobrać guild_id z kanału {ranking_channel_id}: {resp.status_code} — {resp.text[:100]}")
    return fallback or None


def get_discord_members(guild_id: int = None, role_id: int = None, game_guild_id: int = None):
    """Pobierz listę członków z roli Discord.
    guild_id = Discord server ID (for API call)
    game_guild_id = ranking_channel_id (for DB storage, defaults to guild_id for legacy)
    """
    gid = guild_id or GUILD_ID
    rid = role_id or ROLE_ID
    db_gid = game_guild_id or gid  # use channel-based ID for DB
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    url = f"https://discord.com/api/v10/guilds/{gid}/members?limit=1000"

    logger.info(f"🔍 Pobieram członków z Guild ID: {gid}, Role ID: {rid}")
    response = requests.get(url, headers=headers)
    logger.info(f"📡 API status: {response.status_code}")

    if response.status_code != 200:
        logger.error(f"❌ Błąd API Discord: {response.status_code} — {response.text}")
        return []

    all_members = response.json()
    logger.info(f"👥 Wszystkich członków na serwerze: {len(all_members)}")

    members = []
    for member in all_members:
        roles = member.get('roles', [])
        user = member.get('user', {})
        username = user.get('username', '?')

        if str(rid) in [str(r) for r in roles]:
            dc_nick = oczysc_nick_v(member.get('nick') or user.get('display_name') or username)
            if dc_nick:
                game_nick = dc_nick
                if game_nick in ["SKUTABABA", "SKUTYSIURAS", "ASPIRIN"]:
                    game_nick = "SKUTY SZKIELET"
                get_or_create_member(game_nick, user.get('id'), guild_id=db_gid)
                _update_discord_nick(game_nick, dc_nick, guild_id=db_gid)
                members.append(game_nick)
                logger.info(f"  ✅ Znaleziono członka z rolą: {dc_nick}")
        else:
            logger.debug(f"  ⏭️  Brak roli: {username} (role: {roles})")

    current = list(set(members))
    logger.info(f"📋 Znaleziono {len(current)} członków z rolą {rid}")

    # Wyczyść discord_id dla członków którzy utracili rolę
    # added_manually=True = dodani przez /wpłata_ręczna — nie dotykamy ich
    from database import get_session, GuildMember
    session = get_session()
    try:
        old_with_role = session.query(GuildMember).filter(
            GuildMember.guild_id == db_gid,
            GuildMember.discord_id.isnot(None),
            GuildMember.added_manually == False,
        ).all()
        removed = [m for m in old_with_role if m.nick not in current]
        for m in removed:
            logger.info(f"  🔴 Utracił rolę, usuwam discord_id: {m.nick}")
            m.discord_id = None
        if removed:
            session.commit()
    finally:
        session.close()

    return current


def _creds_for_guild(env_key: str) -> tuple:
    """Zwróć (login, password, pin) z env vars używając env_key jako prefiksu."""
    import os
    key = env_key.upper().replace(" ", "_").replace("-", "_")
    login    = os.getenv(f"{key}_HARD_LOGIN")    or HARD_LOGIN
    password = os.getenv(f"{key}_HARD_PASSWORD") or HARD_PASSWORD
    pin      = os.getenv(f"{key}_HARD_PIN")      or HARD_PIN
    logger.info(f"🔑 Kredencjały dla klucza '{key}': login={login}")
    return login, password, pin


def scrape_hard_logs(login: str = None, password: str = None, pin: str = None) -> list:
    """Scrapuj logi z Projekt Hard"""
    _login = login or HARD_LOGIN
    _password = password or HARD_PASSWORD
    _pin = pin or HARD_PIN
    logger.info("🌐 Łączę się z Projekt Hard...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1920,1080",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pl-PL",
        )
        context.set_default_timeout(60000)
        page = context.new_page()

        try:
            page.goto("https://projekt-hard.eu/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            logger.info(f"📄 Tytuł strony: {page.title()}")

            buttons = page.get_by_role("button").all()
            logger.info(f"🔘 Przyciski na stronie: {[b.inner_text() for b in buttons]}")

            page.get_by_role("button", name="Zaloguj").click(timeout=60000)
            page.get_by_role("textbox", name="Login lub e-mail...").fill(_login)
            page.get_by_role("textbox", name="Hasło...").fill(_password)
            page.get_by_role("textbox", name="Pin...").fill(_pin)
            page.get_by_role("button", name="Zaloguj się").click()
            page.wait_for_timeout(3000)
            logger.info(f"📄 Po logowaniu — tytuł: {page.title()}, URL: {page.url}")

            # Kliknij przycisk "Logi Gildii" dla postaci w gildii (nie disabled)
            guild_btn = page.locator("#guild_logs:not(.disabled):not([disabled])")
            guild_btn.last.click()

            # Czekaj na otwarcie modala i załadowanie wierszy przez AJAX/DataTables
            page.wait_for_selector("#guild_logs_modal.show", timeout=30000)
            page.wait_for_selector("#guild_logs_table tbody tr", state="attached", timeout=15000)
            page.wait_for_timeout(500)

            # Ustaw 100 wierszy na stronę
            length_select = page.locator("select[name='guild_logs_table_length']")
            if length_select.count() > 0:
                length_select.select_option("100")
                page.wait_for_timeout(700)

            all_frames = []
            while True:
                page.wait_for_selector("#guild_logs_table tbody tr", state="attached", timeout=10000)
                html = page.inner_html("#guild_logs_table")
                all_frames.append(pd.read_html(io.StringIO(f"<table>{html}</table>"))[0])

                next_btn = page.locator("#guild_logs_table_next")
                classes = next_btn.get_attribute("class") or ""
                if "disabled" not in classes:
                    next_btn.locator("a").click()
                    page.wait_for_timeout(700)
                else:
                    break

            logger.info(f"✅ Pobrano {len(all_frames)} stron")
            browser.close()

            df = pd.concat(all_frames, ignore_index=True)
            logger.info(f"📋 Kolumny tabeli: {list(df.columns)}")
            # Keep only deposit rows — withdrawals contain 'wypłac' in the action column
            action_col = next(
                (c for c in df.columns if any(k in str(c).lower() for k in ('typ', 'dział', 'akcja'))),
                df.columns[0]  # fallback: first column is the action type
            )
            before = len(df)
            df = df[~df[action_col].str.contains('wypłac', case=False, na=False)].copy()
            logger.info(f"🔽 Odfiltrowano wypłaty: {before} → {len(df)} wpisów (kolumna: '{action_col}')")
            df = df[~df['Nazwa członka'].str.contains('->', na=False)].copy()
            df['Nazwa członka'] = (
                df['Nazwa członka']
                .apply(oczysc_nick_v)
                .replace({'SKUTABABA': 'SKUTY SZKIELET', 'SKUTYSIURAS': 'SKUTY SZKIELET', 'ASPIRIN': 'SKUTY SZKIELET'})
            )

            df['Ilość'] = df['Przedmiot'].str.extract(r'(\d+)').astype(float).fillna(0)
            df['Data'] = pd.to_datetime(df['Data'], format='%H:%M %d.%m.%Y')
            df['Tydzien'] = df['Data'].apply(
                lambda x: (x - timedelta(days=x.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            )

            logger.info(f"✅ Przetworzono {len(df)} wpisów łącznie")
            unikalne_nicki = sorted(df['Nazwa członka'].unique())
            logger.info(f"👤 Unikalne nicki w logach ({len(unikalne_nicki)}): {unikalne_nicki}")
            return df.to_dict('records')

        except Exception as e:
            logger.error(f"❌ Błąd podczas scrapowania: {e}")
            logger.error(f"📄 Tytuł przy błędzie: {page.title()}")
            logger.error(f"🔗 URL przy błędzie: {page.url}")
            browser.close()
            return []


def save_scrape_to_db(records: list, guild_id: int = None, guild_name: str = None):
    """Zapisz dane scrapowania.
    Deduplication is by (nick, date, amount, source_guild_name) — cross-guild.
    A payment is saved once regardless of how many guild counters share the same credentials."""
    from database import get_session, Payment, GuildMember
    gid = guild_id or GUILD_ID
    src = guild_name or str(gid)
    saved = 0
    skipped_dup = 0
    skipped_no_member = 0
    no_member_nicks = set()

    logger.info(f"[{src}] 📥 Otrzymano {len(records)} wpisów do zapisania")
    for r in records[:5]:
        logger.info(f"  📝 przykład: nick={r.get('Nazwa członka')!r}, ilość={r.get('Ilość')}, "
                    f"przedmiot={r.get('Przedmiot')!r}, data={r.get('Data')}")

    for record in records:
        nick = record['Nazwa członka']
        amount = int(record['Ilość'])
        date = record['Data']
        try:
            session = get_session()

            # Find member first (needed for member_id-based dedup of old rows with nick=NULL)
            member = session.query(GuildMember).filter_by(guild_id=gid, nick=nick).first()
            if not member:
                member = session.query(GuildMember).filter_by(nick=nick).first()

            if not member:
                session.close()
                skipped_no_member += 1
                no_member_nicks.add(nick)
                continue

            member_guild_id = member.guild_id
            member_id = member.id

            # Dedup: same date+amount for this nick OR this member_id (covers old rows where nick=NULL)
            from sqlalchemy import or_ as sa_or
            exists = session.query(Payment).filter(
                Payment.date == date,
                Payment.amount == amount,
                sa_or(
                    Payment.nick == nick,
                    Payment.member_id == member_id,
                )
            ).first()
            session.close()

            if exists:
                skipped_dup += 1
                continue

            add_payment(
                nick=nick,
                amount=amount,
                date=date,
                item_name=record['Przedmiot'],
                guild_id=member_guild_id,
                source_guild_name=src,
            )
            saved += 1
            logger.info(f"  💾 zapisano: {nick} +{amount}💎 ({record['Przedmiot']}) {date} [{src}]")
        except Exception as e:
            logger.error(f"❌ Błąd przy zapisie wpłaty {nick}: {e}")

    if no_member_nicks:
        logger.warning(f"[{src}] ⚠️  Brak rekordu członka (pominięto {skipped_no_member}): {sorted(no_member_nicks)}")
    logger.info(f"[{src}] ✅ Zapisano {saved} nowych wpłat, pominięto {skipped_dup} duplikatów, {skipped_no_member} bez członka")


def run_scraper():
    """Scrapuj logi dla każdego aktywnego guildu (osobne kredencjały jeśli różne konta)"""
    logger.info("🚀 Uruchamiam scraper...")

    configs = get_all_active_guild_configs()
    logger.info(f"📋 Znaleziono {len(configs)} aktywnych konfiguracji: {[c.guild_name for c in configs]}")
    if not configs:
        logger.info("⚠️  Brak konfiguracji w DB, używam zmiennych środowiskowych")
        get_discord_members(GUILD_ID, ROLE_ID)
        records = scrape_hard_logs()
        if records:
            save_scrape_to_db(records, GUILD_ID, guild_name="default")
        logger.info("✅ Scraper ukończony (tryb legacy)")
        return

    # Jedno logowanie na unikalny zestaw kredencjałów
    seen_creds = {}  # (login, password, pin) → records
    for cfg in configs:
        game_guild_id = cfg.ranking_channel_id
        discord_guild_id = _resolve_discord_guild_id(game_guild_id, fallback=cfg.discord_guild_id)
        logger.info(f"👥 Aktualizuję członków: {cfg.guild_name} (channel={game_guild_id}, server={discord_guild_id})")
        if not discord_guild_id:
            logger.warning(f"⚠️  Pomijam get_discord_members dla {cfg.guild_name} — brak prawidłowego discord_guild_id")
        else:
            if discord_guild_id != cfg.discord_guild_id:
                logger.info(f"🔧 Naprawiam discord_guild_id dla {cfg.guild_name}: {cfg.discord_guild_id} → {discord_guild_id}")
                save_guild_config(discord_guild_id, cfg.guild_name, game_guild_id,
                                  cfg.role_id, cfg.admin_role_id, cfg.member_role_id,
                                  cfg.limit, cfg.env_key)
            get_discord_members(discord_guild_id, cfg.role_id, game_guild_id=game_guild_id)

        creds = _creds_for_guild(cfg.env_key or cfg.guild_name)
        if creds not in seen_creds:
            logger.info(f"🌐 Scrapuję logi dla konta: {creds[0]} ({cfg.guild_name})")
            seen_creds[creds] = scrape_hard_logs(*creds) or []

        records = seen_creds[creds]
        if records:
            logger.info(f"💾 Zapisuję wpłaty: {cfg.guild_name}")
            save_scrape_to_db(records, game_guild_id, guild_name=cfg.guild_name)

    logger.info("✅ Scraper ukończony")


if __name__ == "__main__":
    run_scraper()
