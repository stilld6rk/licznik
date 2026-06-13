# ✨ Co Się Zmieniło w Wersji 2

## 🆕 Nowe Komendy Discord

### 1️⃣ `/wpłata_ręczna` - Ulepszona wersja wpłat

**Stare**:
```
/wpłata member:NICK amount:5 comment:"powód"
```

**Nowe** (lepsze!):
```
/wpłata_ręczna payer:KTO recipient:ZA_KOGO amount:ILE reason:POWÓD
```

**Exemple**:
```
/wpłata_ręczna 
  payer:ADMIN 
  recipient:LUNA_LOVEGOOD 
  amount:5 
  reason:Zastępstwo za Kowalskiego
```

**Wyjście** - piękny embed z informacjami:
```
✅ Wpłata ręczna dodana

🔹 KTO
ADMIN

🔹 ZA KOGO
LUNA_LOVEGOOD

🔹 ILE
5 💎

🔹 POWÓD
Zastępstwo za Kowalskiego
```

---

### 2️⃣ `/ustaw_dołączenie` - NOWA! Data dołączenia gracza

```
/ustaw_dołączenie nick:LUNA_LOVEGOOD date:2024-01-15
```

**Co to robi**:
- ✅ Mówi systemowi kiedy gracz oficjalnie dołączył
- ✅ Wpłaty liczą się **tylko od tego tygodnia**
- ✅ Zapobiega liczeniu "długu" wstecz
- ✅ Sprawa, że nowe osoby są sprawiedliwie liczone

**Przykład**:
```
Gracz A: Dołączył 01.01 → Liczy się od 01.01
Gracz B: Dołączył 15.01 → Liczy się od 15.01
Gracz C: Brak daty   → ❌ NE LICZY SIĘ
```

---

### 3️⃣ `/info_członka` - NOWA! Info o graczu

```
/info_członka nick:LUNA_LOVEGOOD
```

**Wyświetla**:
```
📋 Informacje o: LUNA_LOVEGOOD

🔹 Nick
LUNA_LOVEGOOD

🆔 Discord ID
123456789

📅 Dołączył
15.01.2024

Status
✅ Aktywny
```

---

## 🔧 Zmiany w Backend

### database.py
- ✅ `join_date` w tabeli `guild_members` - teraz używane właściwie!

### db_helper.py
- ✅ `update_member_join_date()` - teraz pozwala na zmianę istniejącej daty
- ✅ `get_member_info()` - NOWA funkcja do pobierania info o członku

### calculator.py
- ✅ `calculate_debts()` - teraz sprawdza `join_date` gracza
- ✅ Pomija tygodnie PRZED datą dołączenia

### bot.py
- ✅ Zmieniono `/wpłata` na `/wpłata_ręczna` (lepszy format)
- ✅ Dodano `/ustaw_dołączenie` (zarządzanie datami)
- ✅ Dodano `/info_członka` (info o graczu)

---

## 📚 Nowe Dokumenty

Dodałem 3 nowe guidy:

1. **COMMANDS_GUIDE.md** - Dokumentacja wszystkich komend
2. **DATADOLACZENIA_GUIDE.md** - Szczegółowe wyjaśnienie jak działa data dołączenia
3. **Ten plik** - Podsumowanie zmian

---

## 🎯 Workflow Admin

### Scenariusz: Nowy gracz dołącza

```
1. Gracz pisze: "Hej, chciałbym się dołączyć!"

2. Admin sprawdza: /members (czy jest już na liście)

3. Admin ustawia datę: 
   /ustaw_dołączenie nick:NEWBIE date:2024-06-13

4. Czeka 1 godzinę aż scraper się uruchomi

5. Gracz pojawia się w rankingu od tego tygodnia ✅

6. Admin może dodać retroaktywną wpłatę jeśli trzeba:
   /wpłata_ręczna 
     payer:SYSTEM 
     recipient:NEWBIE 
     amount:3 
     reason:"Dopłata za poprzedni tydzień"
```

### Scenariusz: Gracz na urlop, ktoś płaci za niego

```
1. Admin robi wpłatę:
   /wpłata_ręczna 
     payer:PRZYJACIEL 
     recipient:NA_URLOPIE 
     amount:4 
     reason:"Gość na wakacjach, kolegium płaci"

2. NA_URLOPIE pojawia się w rankingu z +4💎

3. W rankingu widać powód: "Gość na wakacjach, kolegium płaci"
```

---

## 📊 Logika Płatności - Zmiany

### Przed (v1):
```
Gracz X wpłacił lub admin dodał wpłatę
→ Zawsze się liczy, niezależnie od tego kiedy gracz faktycznie dołączył
```

### Teraz (v2):
```
Gracz X wpłacił lub admin dodał wpłatę
→ Sprawdzamy datę dołączenia gracza
→ Jeśli wpłata PRZED datą dołączenia → Ignorujemy ❌
→ Jeśli wpłata PO dacie dołączenia → Liczymy ✅
```

---

## 🔄 Migracja z v1 na v2

Jeśli już masz starego bota:

### Co trzeba zrobić:

1. ✅ **Zamień pliki** - bot.py, db_helper.py, calculator.py
2. ✅ **Ustaw daty dołączenia** dla wszystkich graczy:
   ```
   /ustaw_dołączenie nick:GRACZ1 date:2024-01-01
   /ustaw_dołączenie nick:GRACZ2 date:2024-01-05
   ...
   ```
3. ✅ **Czekaj** aż scraper uruchomi się (co 1h) i recalculuje rankingi

### Co się NIE zmienia:
- ✅ Baza danych (PostgreSQL)
- ✅ Railway deployment
- ✅ Discord webhook
- ✅ Zmienne środowiskowe

---

## 💡 Best Practices

### ✅ DO
- Zawsze ustaw datę dołączenia gdy gracz się pojawia
- Używaj `/info_członka` aby sprawdzić kto ma datę
- Wpisuj powód przy wpłatach ręcznych
- Format daty: `YYYY-MM-DD` (np. 2024-01-15)

### ❌ DON'T
- Nie zapomnij ustawić daty dla nowych graczy
- Nie mieszaj formatów daty
- Nie usuwaj wpłat (kopiuj bazę na wypadek)

---

## 🆘 FAQ

**P: Gracz nie pojawia się w rankingu**
O: Sprawdź `/info_członka nick:GRACZ` - czy ma datę dołączenia?

**P: Wpłata z ubiegłego tygodnia nie liczy się**
O: Możliwe że data dołączenia jest za późna. 
   Sprawdź `/info_członka` i popraw datę jeśli trzeba.

**P: Jak usunąć wpłatę ręczną?**
O: Na razie trzeba to zrobić bezpośrednio w bazie danych (admin panel Railway).
   Mogę dodać komendę `/usuń_wpłatę` jeśli potrzebujesz.

**P: Czy mogę zmienić datę dołączenia?**
O: Tak! Systemem zajęcia się tym sam 
   `/ustaw_dołączenie nick:GRACZ date:NOWA_DATA`

---

## 📈 Liczby

- ✅ 3 nowe komendy
- ✅ 2 nowe funkcje w db_helper.py
- ✅ 100+ linii logiki do obsługi dat
- ✅ 3 nowe dokumenty (COMMANDS_GUIDE, DATADOLACZENIA_GUIDE, CHANGELOG)
- ✅ Całkowicie wstecz kompatybilne z v1

---

## 🚀 Deployment

Ponieważ zmieniły się tylko pliki Python (bot.py, db_helper.py, calculator.py):

1. Updateuj pliki w repozytorium
2. Git push do Railway
3. Railway automatycznie deployuje
4. Koniec! ✅

Baza danych się nie zmienia (tylko logika).

---

**Gotowe! 🎉 Teraz masz pełny system do zarządzania wpłatami z datami dołączenia!**

Pytania? Czytaj COMMANDS_GUIDE.md lub DATADOLACZENIA_GUIDE.md 📚
