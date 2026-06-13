# 📊 Bot Rankingów - Refaktor do Railway + PostgreSQL

## 🎯 Co się zmieniło?

Refaktoryzowałem Twój bot, aby:

1. **Zamiast plików → PostgreSQL baza**
   - ✅ Przeniesiono wpłaty (payments)
   - ✅ Ręczne korekty (manual_corrections)
   - ✅ Członkowie gildii (guild_members)
   - ✅ Przeniesione długi (debt_carryover)
   - ✅ ID wiadomości Discord (weekly_messages)

2. **Discord.py bot z slash commands**
   ```
   /wpłata member:NICK amount:5 comment:"nota" payer:"kto_zapłacił"
   /zaległości [member:NICK]
   /tydzień_off is_off:true/false
   /sync_scrape
   /members
   ```

3. **Auto-scheduler**
   - Co godzinę uruchamia scraper
   - Automatycznie oblicza zaległości
   - Wysyła/aktualizuje ranking na Discord

4. **Railway deployment**
   - Łatwe uruchomienie na Railway
   - Automatyczna baza PostgreSQL
   - Zero konfiguracji lokalnej

## 📁 Struktura plików

```
├── main.py                  # Punkt wejścia dla Railway
├── bot.py                   # Discord bot z slash commands
├── scraper.py               # Pobieranie danych z Projekt Hard
├── calculator.py            # Obliczanie zaległości
├── config.py                # Zmienne środowiskowe
├── database.py              # SQLAlchemy modele
├── db_helper.py             # Helper funkcje do bazy
├── requirements.txt         # Python packages
├── Procfile                 # Railway config
├── railway.toml             # Railway build config
├── .env.example             # Template zmiennych
└── README.md                # Pełna dokumentacja
```

## 🚀 Szybki start na Railway

### Krok 1: Przygotuj repo
```bash
git init
git add .
git commit -m "Refaktor na Railway + DB"
git push origin main
```

### Krok 2: Railway setup (https://railway.app)
1. Zaloguj się z GitHub
2. "Create New Project" → "Deploy from GitHub"
3. Wybierz swoje repo
4. Railway automatycznie deployuje!

### Krok 3: Dodaj PostgreSQL
- W projekcie: "Add Plugin" → "PostgreSQL"
- Railway ustawia `DATABASE_URL` automatycznie

### Krok 4: Ustaw zmienne
W Railway Variables dodaj (ze `$ env` z .env.example):
```
DISCORD_BOT_TOKEN=xyz...
GUILD_ID=123...
ROLE_ID=456...
WEBHOOK_URL=https://discord.com...
HARD_LOGIN=your_login
HARD_PASSWORD=your_pass
HARD_PIN=your_pin
LIMIT=4
HEADLESS=true
```

### Krok 5: Deploy!
Gotowe! Railway automatycznie uruchamia `python main.py` z Procfile

## 🤖 Nowe komendy bota

### Dodaj wpłatę ręczną
```
/wpłata member:NICK amount:5 comment:"powód" payer:"kto_zapłacił"
```
- **member**: Nazwa gracza
- **amount**: Ilość diamentów (1-10)
- **comment**: Opcjonalnie np. "Płata za gościa"
- **payer**: Opcjonalnie nazwa osoby co zapłaciła

### Pokaż zaległości
```
/zaległości
/zaległości member:NICK
```

### Wyłącz tydzień
```
/tydzień_off is_off:true
```
(Ranking nie będzie wysłany na Discord)

### Ręczny scraper
```
/sync_scrape
```
(Dla admina - uruchamia scraper i aktualizuje rankingi)

### Lista członków
```
/members
```

## 🔄 Jak to działa teraz

```
Railway Server
├── Discord Bot (24/7)
│   ├── Czeka na /komendy
│   ├── Co 1h uruchamia scraper
│   └── Wysyła rankingi na webhook
├── PostgreSQL
│   ├── guild_members
│   ├── payments
│   ├── manual_corrections
│   ├── weekly_messages
│   └── debt_carryover
└── Playwright (headless)
    └── Scrapuje projekt-hard.eu
```

## 💾 Migracja danych ze starego systemu

Jeśli chcesz przenieść stare dane z Excela:

```python
# Script do migracji (opcjonalnie)
from db_helper import add_payment, add_manual_correction
from datetime import datetime

# Czytaj stary Excel
df = pd.read_excel("stary_ranking.xlsx")

# Konwertuj do bazy
for _, row in df.iterrows():
    add_payment(
        nick=row['Nick'],
        amount=row['Amount'],
        date=datetime.fromisoformat(row['Date']),
        item_name="Migrated"
    )
```

## ⚙️ Zmienne środowiskowe

| Zmienna | Opis | Przykład |
|---------|------|---------|
| `DISCORD_BOT_TOKEN` | Token bota Discord | `MTQ5MDI0...` |
| `GUILD_ID` | ID serwera | `1473620113021472870` |
| `ROLE_ID` | ID roli gildii | `1512190222320799865` |
| `WEBHOOK_URL` | Webhook do kanału | `https://discord.com/api/webhooks/...` |
| `HARD_LOGIN` | Login do Projekt Hard | `stillindark` |
| `HARD_PASSWORD` | Hasło | `RIPn#W5.Moa:2FnR` |
| `HARD_PIN` | PIN | `99711` |
| `DATABASE_URL` | PostgreSQL URL | Auto-ustawiane przez Railway |
| `LIMIT` | Max wpłaty/tydzień | `4` |
| `HEADLESS` | Playwright headless | `true` |

## 🐛 Jeśli coś nie działa

### Bot się nie loguje
```
Sprawdzić: DISCORD_BOT_TOKEN, intents, uprawnienia na serwerze
```

### Scraper fails
```
Sprawdzić: HARD_LOGIN, HARD_PASSWORD, HARD_PIN, strona dostępna?
```

### Baza się nie tworzy
```
Railway powinno mieć PostgreSQL plugin
Sprawdzić logi: Railway Dashboard → Logs
```

## 📊 Dashboard Railway

Railway pokaż w real-time:
- 📈 CPU/Memory usage
- 📝 Logi (wszystko co print i logger)
- 🔗 Status deploya
- 💾 PostgreSQL backupy

Szukaj w logach `✅` to jest ok, `❌` to błąd.

## 💡 Co dalej?

- [ ] Archiwum rankingów (ostatnie 3 miesiące)
- [ ] Notyfikacje Discord dla zalegających
- [ ] Statystyki gracza (/stats @member)
- [ ] Auto-kory za złe formatowanie logów
- [ ] Leaderboard na embeddzie (top 10)

## 🎨 Customizacja

Kolory w `config.py`:
```python
GOLD = "FFD700"      # 1. miejsce
SILVER = "C0C0C0"    # 2. miejsce
BRONZE = "CD7F32"    # 3. miejsce
ORANGE = "FFA500"    # Nadpłaty
RED = "FF4444"       # Niedopłaty
```

---

**Gotowe! Wystarczy push do GitHub i Railway robi się magią! 🚀**
