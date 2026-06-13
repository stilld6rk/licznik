# 🆕 Nowe Komendy - Zarządzanie Członkami i Wpłatami

## 📝 Wpłaty Ręczne

### `/wpłata_ręczna` - Dodaj wpłatę (KTO → ZA KOGO, ILE, POWÓD)

**Format**: 
```
/wpłata_ręczna payer:KTO recipient:ZA_KOGO amount:ILE reason:POWÓD
```

**Przykłady**:

```
/wpłata_ręczna 
  payer:ADMIN 
  recipient:NICK 
  amount:5 
  reason:Zastępstwo za Kowalskiego
```

```
/wpłata_ręczna 
  payer:GRYFINDOM 
  recipient:LUNA_LOVEGOOD 
  amount:3 
  reason:Płata za dwa dni
```

**Parametry**:
- `payer` (KTO) - Osoba/admin która wpłaca
- `recipient` (ZA KOGO) - Członek gildii który otrzymuje wpłatę
- `amount` (ILE) - Ilość diamentów (1-10)
- `reason` (POWÓD) - Opcjonalnie: komentarz wyjaśniający

**Wyjście**:
```
✅ Wpłata ręczna dodana

🔹 KTO
ADMIN

🔹 ZA KOGO
NICK

🔹 ILE
5 💎

🔹 POWÓD
Zastępstwo za Kowalskiego
```

---

## 📅 Zarządzanie Datą Dołączenia

### `/ustaw_dołączenie` - Ustaw kiedy gracz dołączył [ADMIN]

**Format**:
```
/ustaw_dołączenie nick:NAZWA date:YYYY-MM-DD
```

**Przykłady**:

```
/ustaw_dołączenie nick:NICK date:2024-01-15
```

```
/ustaw_dołączenie nick:LUNA_LOVEGOOD date:2024-06-01
```

**Parametry**:
- `nick` - Nazwa gracza
- `date` - Data w formacie YYYY-MM-DD (np. 2024-01-15)

**Co to robi**:
- 🔹 Ustawia datę kiedy gracz dołączył do gildii
- 🔹 Wpłaty będą liczone **od tego tygodnia**
- 🔹 Przedtem gracza nie będzie w rankingu

**Wyjście**:
```
✅ Data dołączenia ustawiona

🔹 Gracz
NICK

📅 Dołączył
15.01.2024

ℹ️ Info
Wpłaty będą liczone od tego tygodnia
```

---

## 👤 Informacje o Członku

### `/info_członka` - Pokaż dane członka

**Format**:
```
/info_członka nick:NAZWA
```

**Przykład**:
```
/info_członka nick:NICK
```

**Wyświetla**:
- 🔹 Nick
- 🆔 Discord ID
- 📅 Data dołączenia
- ✅ Status (Aktywny/Nieaktywny)

**Wyjście**:
```
📋 Informacje o: NICK

🔹 Nick
NICK

🆔 Discord ID
123456789

📅 Dołączył
15.01.2024

Status
✅ Aktywny
```

---

## 🔄 Logika Płatności z Datą Dołączenia

### Jak to działa?

```
Gracz A:
├─ Dołączył: 01.01.2024
├─ Tygodnie się liczą od 01.01
└─ Wszystkie wpłaty są liczone ✅

Gracz B:
├─ Dołączył: 15.01.2024
├─ Tygodnie PRZED 15.01 się NIE liczą ❌
├─ Począwszy od 15.01 wszystkie wpłaty się liczą ✅
└─ Jeśli dołączył w środku tygodnia, liczy się pełny tydzień
```

### Przykład

```
Gracz XYZ dołączył: 10.01.2024 (środa)

Tydzień 01.01-07.01:
❌ Nie liczymy (jeszcze go nie było)

Tydzień 08.01-14.01:
❌ Nie liczymy (dołączył dopiero 10.01, ale to na początku tygodnia)

Tydzień 15.01-21.01 (PIERWSZY PEŁNY TYDZIEŃ):
✅ ZACZYNAMY LICZYĆ od tu
```

---

## 📊 Scenariusze Użycia

### Scenario 1: Nowy gracz dołącza
```
1. Admin zrobi /ustaw_dołączenie nick:NEWBIE date:2024-06-13
2. System zapamięta, że od 10.06.2024 (poniedziałek) liczy się gracz
3. Wpłaty od tego tygodnia będą w rankingu
```

### Scenario 2: Admin wpłaca za gracza (zastępstwo)
```
1. Admin robi: /wpłata_ręczna 
   payer:ADMIN 
   recipient:SICK_PLAYER 
   amount:5 
   reason:"Gracz jest chory"

2. W rankingu pojawi się +5💎 dla SICK_PLAYER
3. W komentarzu będzie: "Gracz jest chory"
```

### Scenario 3: Współgracze dzielą się wpłatą
```
1. GRACZ_A robi: /wpłata_ręczna 
   payer:GRACZ_A_i_GRACZ_B 
   recipient:GRACZ_C 
   amount:4 
   reason:"Dzielą się płatą (2+2💎)"

2. GRACZ_C ma +4💎 w rankingu
3. Wiadomo kto płacił: "GRACZ_A_i_GRACZ_B"
```

---

## ⚠️ Ważne Notatki

### Uprawnienia
- **`/wpłata_ręczna`** - Tylko ADMIN
- **`/ustaw_dołączenie`** - Tylko ADMIN
- **`/info_członka`** - Wszyscy
- **`/zaległości`** - Wszyscy

### Format daty
- ✅ Poprawnie: `2024-01-15`
- ❌ Źle: `15-01-2024` lub `15.01.2024`

### Nazwa gracza
- Czułość na wielkość liter
- Musi być dokładnie jak w rankingu

---

## 🔧 Backend Info

### Baza danych - Tabela `manual_corrections`

```
id              - ID wpłaty
recipient_id    - ID gracza (FK)
payer           - Tekst: "kto płacił"
amount          - Ilość diamentów
date            - Kiedy wpłacono
week_start      - Poniedziałek tygodnia
comment         - Powód/notatka
set_by          - Discord ID admina
created_at      - Kiedy wpłata została dodana
updated_at      - Ostatnia zmiana
```

### Baza danych - Tabela `guild_members`

```
id              - ID członka
nick            - Nazwa gracza
discord_id      - ID Discord (opcjonalnie)
join_date       - Kiedy dołączył ← KLUCZOWE
is_active       - Czy aktywny
created_at      - Kiedy dodano do bazy
updated_at      - Ostatnia zmiana
```

---

## 💡 Porady

1. **Zawsze ustal datę dołączenia** - Bez niej gracz może być liczony wstecz
2. **Powód wpłat** - Zawsze wpisuj aby wiedzieć dlaczego
3. **Weryfikuj gracza** - Zanim wpłacisz, sprawdź `/info_członka`
4. **Zachowaj spójność** - Wszystkie daty w formacie YYYY-MM-DD

---

Jeśli coś jest niejasne, sprawdź logi w Railway! 📊
