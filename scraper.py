import re
import io
import pandas as pd
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
from config import HARD_LOGIN, HARD_PASSWORD, HARD_PIN, GUILD_ID, ROLE_ID, DISCORD_BOT_TOKEN as BOT_TOKEN, HEADLESS
from db_helper import get_or_create_member, add_payment, get_all_active_members
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clean_nick(nick):
    """Oczyść nick z Version tagów"""
    if not nick:
        return nick
    return re.sub(r'[Vv]\d+$', '', str(nick)).strip()


def get_discord_members():
    """Pobierz listę członków z roli Discord"""
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/members?limit=1000"
    
    members = []
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        for member in response.json():
            if ROLE_ID in member.get('roles', []):
                user = member.get('user', {})
                nick = clean_nick(member.get('nick') or user.get('display_name') or user.get('username'))
                
                if nick:
                    # Aliasy
                    if nick in ["SKUTABABA", "SKUTYSIURAS", "ASPIRIN"]:
                        nick = "SKUTY SZKIELET"
                    
                    member_obj = get_or_create_member(nick, user.get('id'))
                    members.append(nick)
    
    return list(set(members))


def scrape_hard_logs() -> list:
    """Scrapuj logi z Projekt Hard"""
    logger.info("🌐 Łączę się z Projekt Hard...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_context().new_page()
        
        try:
            page.goto("https://projekt-hard.eu/")
            
            # Logowanie
            page.get_by_role("button", name="Zaloguj").click()
            page.get_by_role("textbox", name="Login lub e-mail...").fill(HARD_LOGIN)
            page.get_by_role("textbox", name="Hasło...").fill(HARD_PASSWORD)
            page.get_by_role("textbox", name="Pin...").fill(HARD_PIN)
            page.get_by_role("button", name="Zaloguj się").click()
            page.wait_for_timeout(2000)
            
            # Otwórz Logi Gildii
            page.get_by_role("link", name="Logi Gildii").filter(visible=True).first.click()
            page.get_by_label("Pokaż 102550100 pozycji", exact=True).select_option("100")
            page.wait_for_selector("#guild_logs_table")
            
            # Zbierz wszystkie strony
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
            
            # Przetwórz dane
            df = pd.concat(all_frames, ignore_index=True)
            df = df[~df['Nazwa członka'].str.contains('->', na=False)].copy()
            df['Nazwa członka'] = (
                df['Nazwa członka']
                .apply(clean_nick)
                .replace(['SKUTABABA', 'SKUTYSIURAS', 'ASPIRIN'], 'SKUTY SZKIELET')
            )
            
            df['Ilość'] = df['Przedmiot'].str.extract(r'(\d+)').astype(float).fillna(0)
            df['Data'] = pd.to_datetime(df['Data'], format='%H:%M %d.%m.%Y')
            
            # Filtruj tylko członków gildii
            valid_members = get_all_active_members()
            df = df[df['Nazwa członka'].isin(valid_members)].copy()
            
            logger.info(f"✅ Przetworzono {len(df)} wpisów")
            return df.to_dict('records')
        
        except Exception as e:
            logger.error(f"❌ Błąd podczas scrapowania: {e}")
            browser.close()
            return []


def save_scrape_to_db(records: list):
    """Zapisz dane scrapowania do bazy"""
    for record in records:
        try:
            add_payment(
                nick=record['Nazwa członka'],
                amount=int(record['Ilość']),
                date=record['Data'],
                item_name=record['Przedmiot']
            )
        except Exception as e:
            logger.error(f"❌ Błąd przy zapisie wpłaty: {e}")
    
    logger.info(f"✅ Zapisano {len(records)} wpłat do bazy")


def run_scraper():
    """Główna funkcja scrapowania"""
    logger.info("🚀 Uruchamiam scraper...")
    
    # Aktualizuj członków
    members = get_discord_members()
    logger.info(f"📋 Znaleziono {len(members)} członków")
    
    # Scrapuj i zapisz
    records = scrape_hard_logs()
    if records:
        save_scrape_to_db(records)
    
    logger.info("✅ Scraper ukończony")


if __name__ == "__main__":
    run_scraper()
