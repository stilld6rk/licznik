# Bot Rankingów Gildii - Wersja Railway + PostgreSQL

## 🎯 Co się zmieniło

- ✅ **Baza danych PostgreSQL** zamiast plików tekstowych/Excel
- ✅ **Discord bot z slash commands** do ręcznych wpłat
- ✅ **Auto-scraper** uruchamiany co godzinę
- ✅ **Wdrażanie na Railway** w kilka kliknięć
- ✅ **Zmienne środowiskowe** zamiast hardkodów

## 📋 Wymagania

- Konto Railway (free tier wystarczy)
- Bot Discord z intencjami (intents)
- Webhook do Discord kanału

## 🚀 Wdrażanie na Railway

### 1. Przygotuj repozytorium
```bash
git init
git add .
git commit -m "Initial commit"
git push -u origin main
```

### 2. Połącz się z Railway
- Wejdź na https://railway.app
- Zaloguj się z GitHub
- Kliknij "Create New Project"
- Wyberz "Deploy from GitHub repo"

### 3. Dodaj PostgreSQL
- W Railway dashboard kliknij "Add Plugin"
- Wybierz "PostgreSQL"
- Railway automatycznie ustawia `DATABASE_URL`

### 4. Ustaw zmienne środowiskowe
W Railway, w sekcji "Variables" dodaj:

```
DISCORD_BOT_TOKEN=your_discord_bot_token_here
GUILD_ID=your_guild_id_here
ROLE_ID=your_role_id_here
WEBHOOK_URL=your_webhook_url_here
HARD_LOGIN=your_login_here
HARD_PASSWORD=your_password_here
HARD_PIN=99711
LIMIT=4
HEADLESS=true
```

### 5. Dodaj Procfile
Railway będzie szukać komendy do uruchomienia w:

```
web: python main.py
```

### 6. Deploy
Railway automatycznie deployuje gdy push-niesz do `main`.

## 🤖 Komendy Discord Bot

### `/wpłata`
Dodaj wpłatę ręczną dla członka
```
/wpłata member:NICK amount:5 comment:"Płata za wpłatę" payer:"PŁATNIK"
```

### `/zaległości`
Pokaż zaległości w tym tygodniu
```
/zaległości
/zaległości member:NICK  # Dla konkretnego członka
```

### `/tydzień_off`
Wyłącz/włącz tydzień (nie będzie rankingu)
```
/tydzień_off is_off:true   # Wyłączenie
/tydzień_off is_off:false  # Włączenie
```

### `/sync_scrape`
Ręczne uruchomienie scrapera
```
/sync_scrape
```

### `/members`
Lista wszystkich członków
```
/members
```

## 📊 Struktura bazy danych

### `guild_members`
- `id` - PK
- `nick` - Nazwa gracza
- `discord_id` - ID Discord
- `join_date` - Kiedy dołączył
- `is_active` - Czy aktywny

### `payments`
- `id` - PK
- `member_id` - FK do guild_members
- `amount` - Ilość diamentów
- `date` - Kiedy wpłacił
- `week_start` - Poniedziałek tygodnia

### `manual_corrections`
- `id` - PK
- `recipient_id` - FK do guild_members
- `amount` - Ilość
- `payer` - Kto zapłacił
- `comment` - Komentarz
- `set_by` - Discord ID admina

### `weekly_messages`
- `week_start` - Kiedy jest tydzień
- `message_id` - ID wiadomości Discord
- `is_off` - Czy tydzień wyłączony

### `debt_carryover`
- `member_id` - FK
- `week_start` - Za jaki tydzień
- `amount` - Ilość do przeniesienia

## ⚙️ Jak działa auto-scraper

Bot automatycznie:
1. **Co godzinę** uruchamia scraper do Projekt Hard
2. Pobiera logi gildii
3. Aktualizuje tabelę `payments` w bazie
4. Oblicza zaległości
5. Wysyła/aktualizuje ranking na Discord

## 🔧 Monitoring i debug

Railway wyświetla logi w real-time. Szukaj:

```
✅ Bot zalogowany jako <bot_name>
✅ Slash commands zsynchronizowane
🔄 Auto-scraper uruchomiony
✅ Scraper ukończony
📤 Wysłano nową wiadomość
✏️  Zaktualizowano wiadomość
```

## 🐛 Troubleshooting

### Bot nie odpowiada
1. Sprawdź czy `DISCORD_BOT_TOKEN` jest poprawny
2. Sprawdź czy bot ma uprawnienia na serwerze
3. Sprawdź czy slashe są zsynchronizowane: `/` powinno pokazać komendy

### Scraper nie działa
1. Sprawdzić czy `HARD_LOGIN`, `HARD_PASSWORD`, `HARD_PIN` są poprawne
2. Sprawdzić czy strona `projekt-hard.eu` jest dostępna
3. Sprawdzić logi w Railway

### Błędy bazy danych
1. Sprawdzić czy `DATABASE_URL` jest ustawiony
2. Railway powinno ustawić go automatycznie
3. Jeśli nie, sprawdzić panel PostgreSQL w Railway

## 📝 Notatki

- Railway **free tier** pozwala na:
  - Bezpłatne 500 godzin compute/miesiąc
  - PostgreSQL z 5GB storage
  - 1 bot 24/7 to ok. 730 godzin, więc będzie koszt (~$5-10/miesiąc)

- Jeśli chcesz oszczędzić, możesz:
  - Zmienić scraper na co 6 godzin zamiast 1
  - Wyłączyć bota w nocy

- **Ważne**: Nie rób `git push` haseł! Zawsze używaj `.env` i `DATABASE_URL`

## 🎨 Kustomizacja

Kolory w `config.py`:
```python
DARK_BG    = "1a1a2e"  # Tło
GOLD       = "FFD700"  # 1. miejsce
SILVER     = "C0C0C0"  # 2. miejsce
BRONZE     = "CD7F32"  # 3. miejsce
```

LIMIT zmień w `.env`:
```
LIMIT=4  # Max wpłaty na tydzień
```

## 💡 Kolejne ulepszenia

- [ ] Leaderboard za ostatnie 3 miesiące
- [ ] Alerty dla graczy z zaległościami
- [ ] Export do czystszych Excel'a (na żądanie)
- [ ] Historyka wpłat dla każdego gracza
- [ ] Role basowane na rankingu (automatyczne assign)

---

**Pytania?** Sprawdź logi w Railway dashboard!
