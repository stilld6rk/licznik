import re
import io
import pandas as pd
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
from config import HARD_LOGIN, HARD_PASSWORD, HARD_PIN, GUILD_ID, ROLE_ID, DISCORD_BOT_TOKEN as BOT_TOKEN, HEADLESS
from db_helper import get_or_create_member, add_payment, get_all_active_members, _update_discord_nick, get_all_active_guild_configs
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def oczysc_nick_v(nick):
    if not nick:
        return nick
    return re.sub(r'[Vv]\d+$', '', str(nick)).strip()


def get_discord_members(guild_id: int = None, role_id: int = None):
    """Pobierz listę członków z roli Discord dla danego guildu"""
    gid = guild_id or GUILD_ID
    rid = role_id or ROLE_ID
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
                get_or_create_member(game_nick, user.get('id'), guild_id=gid)
                _update_discord_nick(game_nick, dc_nick, guild_id=gid)
                members.append(game_nick)
                logger.info(f"  ✅ Znaleziono członka z rolą: {dc_nick}")
        else:
            logger.debug(f"  ⏭️  Brak roli: {username} (role: {roles})")

    current = list(set(members))
    logger.info(f"📋 Znaleziono {len(current)} członków z rolą {rid}")

    # Wyczyść discord_id dla członków którzy utracili rolę
    from database import get_session, GuildMember
    session = get_session()
    try:
        old_with_role = session.query(GuildMember).filter(
            GuildMember.guild_id == gid,
            GuildMember.discord_id.isnot(None)
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


def scrape_hard_logs() -> list:
    """Scrapuj logi z Projekt Hard (jeden raz dla wszystkich gildii)"""
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
            page.get_by_role("textbox", name="Login lub e-mail...").fill(HARD_LOGIN)
            page.get_by_role("textbox", name="Hasło...").fill(HARD_PASSWORD)
            page.get_by_role("textbox", name="Pin...").fill(HARD_PIN)
            page.get_by_role("button", name="Zaloguj się").click()
            page.wait_for_timeout(3000)

            page.get_by_role("link", name="Logi Gildii").first.click()
            page.get_by_label("Pokaż 102550100 pozycji", exact=True).select_option("100")
            page.wait_for_selector("#guild_logs_table")

            all_frames = []
            while True:
                html = page.inner_html("#guild_logs_table")
                all_frames.append(pd.read_html(io.StringIO(f"<table>{html}</table>"))[0])

                next_btn = page.locator("#guild_logs_table_next")
                if "disabled" not in (next_btn.get_attribute("class") or ""):
                    next_btn.locator("a").click()
                    page.wait_for_timeout(700)
                else:
                    break

            logger.info(f"✅ Pobrano {len(all_frames)} stron")
            browser.close()

            df = pd.concat(all_frames, ignore_index=True)
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
            return df.to_dict('records')

        except Exception as e:
            logger.error(f"❌ Błąd podczas scrapowania: {e}")
            logger.error(f"📄 Tytuł przy błędzie: {page.title()}")
            logger.error(f"🔗 URL przy błędzie: {page.url}")
            browser.close()
            return []


def save_scrape_to_db(records: list, guild_id: int = None):
    """Zapisz dane scrapowania do bazy dla danego guildu (pomija duplikaty)"""
    from database import get_session, Payment, GuildMember
    gid = guild_id or GUILD_ID
    saved = 0
    skipped = 0
    for record in records:
        try:
            session = get_session()
            member = session.query(GuildMember).filter_by(guild_id=gid, nick=record['Nazwa członka']).first()
            if not member:
                session.close()
                skipped += 1
                continue
            exists = session.query(Payment).filter_by(
                member_id=member.id,
                date=record['Data'],
                amount=int(record['Ilość'])
            ).first()
            session.close()
            if not exists:
                add_payment(
                    nick=record['Nazwa członka'],
                    amount=int(record['Ilość']),
                    date=record['Data'],
                    item_name=record['Przedmiot'],
                    guild_id=gid,
                )
                saved += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error(f"❌ Błąd przy zapisie wpłaty {record.get('Nazwa członka')}: {e}")

    logger.info(f"[Guild {gid}] ✅ Zapisano {saved} nowych wpłat, pominięto {skipped}")


def run_scraper():
    """Scrapuj raz, zapisz do każdego aktywnego guildu"""
    logger.info("🚀 Uruchamiam scraper...")

    configs = get_all_active_guild_configs()
    if not configs:
        # Fallback: tryb legacy z env vars
        logger.info("⚠️  Brak konfiguracji w DB, używam zmiennych środowiskowych")
        get_discord_members(GUILD_ID, ROLE_ID)
        records = scrape_hard_logs()
        if records:
            save_scrape_to_db(records, GUILD_ID)
        logger.info("✅ Scraper ukończony (tryb legacy)")
        return

    # Zaktualizuj członków dla każdego guildu
    for cfg in configs:
        logger.info(f"👥 Aktualizuję członków: {cfg.guild_name} ({cfg.guild_id})")
        get_discord_members(cfg.guild_id, cfg.role_id)

    # Scrapuj logi raz
    records = scrape_hard_logs()
    if not records:
        logger.info("✅ Scraper ukończony (brak danych)")
        return

    # Zapisz dla każdego guildu
    for cfg in configs:
        logger.info(f"💾 Zapisuję wpłaty: {cfg.guild_name}")
        save_scrape_to_db(records, cfg.guild_id)

    logger.info("✅ Scraper ukończony")


if __name__ == "__main__":
    run_scraper()
