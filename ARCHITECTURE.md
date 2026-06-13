# 🏗️ Architektura Systemu

```
┌─────────────────────────────────────────────────────────────────┐
│                        RAILWAY SERVER                            │
│  (Linux container + PostgreSQL)                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐      ┌──────────────────┐                 │
│  │  main.py         │      │  bot.py          │                 │
│  │  (punkt start)   │      │  (Discord bot)   │                 │
│  │                  │      │                  │                 │
│  │  - init_db()     │◄─────┤  - /wpłata       │                 │
│  │  - run_scraper() │      │  - /zaległości   │                 │
│  │  - run_bot()     │      │  - /tydzień_off  │                 │
│  └──────────────────┘      │  - /sync_scrape  │                 │
│          ▲                  │  - /members      │                 │
│          │                  └────┬─────────────┘                 │
│          │                       │                               │
│  ┌───────┴──────────────────────┴─────┐                         │
│  │                                     │                         │
│  │    ┌──────────────────────────────┐ │                         │
│  │    │  scraper.py                  │ │                         │
│  │    │  - pobiera dane z Projekt    │ │                         │
│  │    │    Hard via Playwright       │ │                         │
│  │    │  - zapisuje do payments      │ │                         │
│  │    └────────┬─────────────────────┘ │                         │
│  │             │                       │                         │
│  │    ┌────────▼─────────────────────┐ │                         │
│  │    │  calculator.py               │ │                         │
│  │    │  - oblicza zaległości        │ │                         │
│  │    │  - wysyła na Discord webhook │ │                         │
│  │    └──────────────────────────────┘ │                         │
│  │                                     │                         │
│  │    ┌──────────────────────────────┐ │                         │
│  │    │  db_helper.py                │ │                         │
│  │    │  - operacje na bazie         │ │                         │
│  │    └────────┬─────────────────────┘ │                         │
│  └───────────────────────┬──────────────┘                         │
│                          │                                        │
│           ┌──────────────▼──────────────┐                         │
│           │      database.py            │                         │
│           │   (SQLAlchemy ORM)          │                         │
│           │                             │                         │
│           │  - GuildMember              │                         │
│           │  - Payment                  │                         │
│           │  - ManualCorrection         │                         │
│           │  - WeeklyMessage            │                         │
│           │  - DebtCarryover            │                         │
│           └────────────┬────────────────┘                         │
│                        │                                          │
│           ┌────────────▼────────────┐                             │
│           │   PostgreSQL Database    │                            │
│           │                          │                            │
│           │   ✅ Wpłaty z logów      │                            │
│           │   ✅ Ręczne korekty      │                            │
│           │   ✅ Długi przeniesione  │                            │
│           │   ✅ Wiadomości Discord  │                            │
│           │                          │                            │
│           └──────────────────────────┘                             │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
         ▲                             ▲
         │                             │
    INPUT                         OUTPUT
         │                             │
  Projekt Hard                   Discord Webhook
  (Login→ Scrape)                (Ranking → Send)
  
  
┌─────────────────────────────────────────────────────────────────┐
│                  UŻYTKOWNIK (Discord)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Wysyła komendę:                      Bot odpowiada:            │
│                                                                   │
│  /wpłata member:X amount:5  ─────────► Dodaj wpłatę do DB       │
│                                        Aktualizuj ranking        │
│                                        Wyślij embed              │
│                                                                   │
│  /zaległości member:X       ─────────► Pokaż stats z DB         │
│                                                                   │
│  /tydzień_off is_off:true   ─────────► Ustaw week.is_off = true │
│                                                                   │
│  /sync_scrape               ─────────► Uruchom scraper ręcznie  │
│                                        Aktualizuj ranking        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    TASK SCHEDULER (APScheduler)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Każdą godzinę:                                                   │
│  1. Uruchom scraper.run_scraper()                                │
│  2. Pobierz logi z Projekt Hard                                  │
│  3. Aktualizuj payments w bazie                                  │
│  4. Uruchom calculator.update_all_weeks()                        │
│  5. Wyślij rankingi na Discord                                  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## 📊 Przepływ danych

### 1️⃣ Auto-sync (co 1 godzinę)
```
Projekt Hard 
    ↓
Playwright scrapes logi
    ↓
Parse data (Nick, Amount, Date)
    ↓
Zapisz do DB.payments
    ↓
Oblicz zaległości
    ↓
Wyślij na Discord webhook
```

### 2️⃣ Ręczna wpłata (/wpłata command)
```
Discord /wpłata
    ↓
Waliduj: uprawnień, ilość
    ↓
DB.add_manual_correction()
    ↓
Oblicz zaległości
    ↓
Wyślij/zaktualizuj ranking
    ↓
Embed potwierdzenia
```

### 3️⃣ Zapytanie o zaległości (/zaległości)
```
Discord /zaległości
    ↓
Pobierz corrections z DB dla tygodnia
    ↓
Wyświetl w embedzie
```

## 🗄️ Baza danych

```
┌─────────────────────────────────────────────────┐
│           guild_members (członkowie)             │
├─────────────────────────────────────────────────┤
│ id* | nick | discord_id | join_date | is_active │
│  1  | NICK  | 123456    | 2024-01-01 | true      │
└─────────────────────────────────────────────────┘
           ▲
           │
    ┌──────┴──────┬─────────────────┐
    │             │                 │
    ▼             ▼                 ▼
┌──────┐   ┌──────────┐   ┌──────────────────┐
│Pay   │   │Debt      │   │ManualCorrection  │
│ments │   │Carryover │   │(ręczne korekty)  │
└──────┘   └──────────┘   └──────────────────┘

┌─────────────────────────────┐
│   weekly_messages           │
├─────────────────────────────┤
│ week_start | message_id | is_off
│ 2024-01-01 | 123456789  | false
└─────────────────────────────┘
```

## 🔌 Integracje

```
┌────────────────────────────────────────────────┐
│ EXTERNAL SERVICES (OUT)                        │
├────────────────────────────────────────────────┤
│                                                 │
│  Discord Webhook API                           │
│  (Wysyłanie rankingów)                         │
│                                                 │
│  Discord Bot API                               │
│  (Slash commands, embeds)                      │
│                                                 │
└────────────────────────────────────────────────┘
        ▲
        │
        │
┌───────┴────────────────────────────────────────┐
│ EXTERNAL SERVICES (IN)                         │
├────────────────────────────────────────────────┤
│                                                 │
│  Projekt Hard Website                          │
│  (Scraping logów via Playwright)               │
│                                                 │
│  Discord API (pobierz członków z rolą)        │
│                                                 │
└────────────────────────────────────────────────┘
```

---

**Streszczenie**: Bot automatycznie scrapuje Projekt Hard co godzinę, 
zapisuje do PostgreSQL, oblicza zaległości, wysyła rankingi na Discord.
Admini mogą dodawać ręczne wpłaty za pomocą `/wpłata` i zarządzać 
tygodniami za pomocą `/tydzień_off`.
