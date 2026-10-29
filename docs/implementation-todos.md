# Plan wykonawczy i todos do kontynuacji w nowej sesji

## Decyzja obowiązująca

**Backend → UI → końcowe próby w CS2/Yprac.**

Przyjmujemy poprawność komend jako założenie implementacyjne. Nie czekamy
z eksporterem, backendem ani UI na próby w grze, odpowiedź autora Yprac
lub płatny pilot. Testy kodu i aplikacji wykonujemy na bieżąco.
Nie oznaczamy integracji jako sprawdzonej, dopóki nie przejdzie końcowych prób.

Ten plik jest skróconym planem wykonawczym. Pełny zakres, decyzje i ryzyka
opisuje [plan projektu](project-plan.md), a końcowe próby
[protokół integracji](integration-validation.md).
Przy zmianie zakresu lub statusów aktualizować oba plany. Nie polegać na
historii rozmowy ani sesyjnej bazie todos.

## Stan kodu — nie implementować od nowa

- Python 3.11+, `uv`, Awpy 3.1.1, kontrakt scenariuszy v1 i raport analizy v2.
- CLI: `players`, `analyze`, `benchmark`, `validate-scenarios`, `schema`,
  `export-scenario`, `build-pack`.
- Parser nieskompresowanych dem CS2 `de_mirage` do 1 GiB, zbiorcze migawki
  sprzed obrażeń, wykluczenia i grupowanie porównywalnych wygranych/przegranych.
- Reguły `damage-window-v3`: zachowują dostępne kąty przeciwnika, a brakujący
  pitch/yaw wyliczają ku pozycji gracza, z oznaczeniem
  `opponent_aim_inferred_toward_player`. Kąty gracza nie są zgadywane.
  Grupy przybliżone i kompletne są rozdzielone.
- Benchmark w osobnych procesach, Docker CLI, testy i workflow CI.
- Jest eksporter `yprac-sandbox-prototype-v1` i wybór/odrzucanie scenariuszy
  oraz paczki ZIP z manifestem, instrukcją, osobnymi liniami komend i opcjonalnym
  CFG. Wspólne moduły dla CLI i backendu: `exporting.py`, `packs.py`.
  Jest backend w `src/cs_map_trainer/web/` z zapamiętanym wyborem sytuacji,
  prywatnym eksportem komend/CFG i opcjonalnym ZIP na żądanie, bez treningowego UI.
  Nie wykonano próby Yprac; eksport pozostaje
  `unverified_in_game`. Nie ma ocen treningu ani kolejki powtórek.

## Zakończone iteracje eksportera i minimalnego backendu

- Zaimplementowano eksport pojedynczego scenariusza, selekcję/odrzucanie,
  paczki ZIP, opcjonalne CFG i zapis artefaktów bez nadpisywania.
- Dodano regresję eksportera, paczek, CLI i przepływu analiza → eksport
  bez ponownego parsowania. Zaliczone: 294 testy; 1 test integracyjny pominięty
  z powodu braku lokalnego dema. Lint, format i budowanie sdist/wheel przeszły.
- Wykonano review zmian: nie zgłoszono istotnych błędów ani regresji.
  Zaakceptowane hipotezy indeksu gracza i encji `2` nie były traktowane jako błędy.
  Review nie zastępuje próby w CS2/Yprac i nie zamyka G1.
- Następnie dodano fundament Django/PostgreSQL/Django-Q2, R2, rejestrację
  e-mail i Steam OpenID, kwoty na SteamID, jednorazową analizę i sprzątanie.
  Testy backendu używają PostgreSQL; prawdziwe R2/Steam/SMTP i obraz Compose
  wymagają próby w skonfigurowanym środowisku. Nie oznaczać ich jako potwierdzonych.
  Następnie zrealizowano `complete-training-backend`, bez przepisywania fundamentu.
- Odbiór lokalny backendu: 58 testów backendu na PostgreSQL; łącznie
  352 zaliczone testy, 2 pominięte (lokalne demo i kontrakt prawdziwego R2).
  Lint/format, build, Django checks i zgodność migracji przeszły.
  Potwierdzono odpowiedź HTTP logowania i odmowę dostępu do prywatnej historii
  bez sesji. Konfiguracja Compose jest poprawna; obrazu nie uruchomiono,
  ponieważ daemon Docker był niedostępny.
- Poprawki review backendu: parser dziedziczy blokadę wspólnego wolumenu,
  zachowując wyłączność po śmierci workera; ma ochronę przed utratą rodzica.
  Callback Steam minimalizuje profil przed lookup allauth, także przy
  ponownym i odrzuconym połączeniu. Migracja `0002_minimize_steam_profiles`
  usuwa starsze nadmiarowe dane; zastosować ją przy wdrożeniu.
  Po poprawkach: 69 testów backendu, 363 zaliczone w całej regresji i 2
  pominięte integracje; lint/format/build, checks i migracje bez błędów.
- Ponowne review poprawek zakończono bez nowych istotnych błędów.
  Potwierdzono poprawność zmian w wyłączności parsera, ochronie po utracie
  rodzica, przepływie kolejki i minimalizacji profili Steam. Review było
  odczytowe i nie uruchamiało ponownie regresji; nie zastępuje odbioru
  kontenera Linux ani prawdziwych R2/Steam/SMTP. G1/G2/G3 pozostają otwarte.

## Zakończony backend treningowy i następny etap

- Dodano zapis wyboru i odrzuceń przy raporcie oraz migrację
  `0003_training_selection`. Domyślnie wybierane są wszystkie nieodrzucone sytuacje.
- Połączono `select_scenarios`, `build_pack` i eksport pojedynczej sytuacji
  z prywatnymi operacjami `/backend/uploads/<id>/`. Główna ścieżka to jedna
  linia komend do skopiowania; ZIP i CFG są opcjonalne. ZIP powstaje na żądanie,
  bez R2 i ponownego parsowania. Pozostaje `unverified_in_game`.
- Regresja obejmuje zapis/odczyt wyboru, cudze/usunięte wyniki, złe ID i typy,
  pusty wybór, nieobsługiwany eksport, CSRF, brak cache i czyszczenie po usunięciu.
  Zaliczone: 127 testów backendu na PostgreSQL 16 w osobnym kontenerze;
  pełna regresja 421 zaliczonych, 2 pominięte (demo i prawdziwe R2).
  Lint/format, sdist/wheel, Django checks, migracje i zgodność modeli przeszły.
- Następny etap to `build-training-ui`: szablony Django korzystające
  z istniejących operacji, bez kolejnej warstwy API i bez przepisywania backendu.
- W skonfigurowanym środowisku osobno odebrać R2/Steam/SMTP oraz kontener
  Linux, zastosować migracje `0002_minimize_steam_profiles` oraz
  `0003_training_selection` i sprawdzić awarię workera. Brak tego środowiska
  nie oznacza pozytywnego odbioru ani potrzeby przepisywania działającej logiki.

Kod backendu treningowego jest gotowy; G2 pozostaje otwarte do odbiorów zewnętrznych.
Kontener PostgreSQL użyty w testach nie potwierdza działania kontenera workera.
Treningowy UI jest następnym krokiem. Pakiet trenera/akademii,
płatności i próby CS2/Yprac pozostają poza najbliższą iteracją.

### Najbliższa iteracja: `build-training-ui`

1. Szablony Django: konto/Steam, upload z potwierdzeniem uprawnień, prywatna
   historia i status zadania — na istniejącym backendzie.
2. Raport z liczebnością próby, ograniczeniami i jawnym brakiem kandydatów
   lub błędem; bez przedstawiania kandydatów jako pewnego werdyktu.
3. Zapamiętany wybór/odrzucenia i kopiowanie całej linii jednej sytuacji.
   ZIP i CFG wyłącznie jako opcjonalne pobrania, nie warunek treningu.
4. Testy przepływu UI, uprawnień, CSRF i błędów, następnie aktualizacja
   statusów. Oceny i proste powtórki należą do kolejnego `wire-personal-training`.

UI jest planowane, nie rozpoczęte. Przed uruchomieniem na istniejącej bazie
wykonać migracje, w tym `0003_training_selection`. Zmiany backendu pozostają
niezacommitowane; zachować je podczas kontynuacji. Tymczasowy kontener
PostgreSQL użyty do lokalnej regresji został zatrzymany i usunięty.

## Polityki minimalnego backendu

- Jeden prywatny R2 Standard, upload bezpośrednio do bucketa; lokalna kopia
  tylko na czas pracy izolowanego parsera. Po pierwszej próbie usuwamy obie
  kopie, także po błędzie; nowa analiza wymaga nowego uploadu. Automatyczny
  retry dotyczy tylko usuwania i dostarczenia komunikatu, nie parsowania.
- Publiczna rejestracja e-mail/hasło z potwierdzeniem adresu oraz obowiązkowe,
  unikalne powiązanie Steam OpenID przed uploadem. Analizujemy tylko tego gracza.
- 3 przyjęte dema na SteamID w ruchomych 7 dniach, jedno aktywne zadanie na
  SteamID i jeden worker globalnie. 1 GiB to limit techniczny pliku, nie kwota.
  Błędy wejścia zużywają przyjęcie; błędy infrastruktury zwalniają kwotę.
- Historia raportów, scenariuszy i komend zostaje do usunięcia przez użytkownika
  lub usunięcia konta. Ewidencja kwoty po usunięciu konta wygasa po 7 dniach;
  nowe konto nie resetuje kwoty ani aktywnego powiązania Steam.
- Porzucone uploady wygasają po 24 h. Reaper obsługuje utracone zadania,
  osierocone obiekty i multipart uploady. Szczegóły uruchomienia są w README.
- Pakiet trenera/akademii ma w przyszłości pozwolić analizować różnych zawodników
  na osobnym uprawnieniu; nie wchodzi do tej iteracji. Bez płatności i UI.

## Wymagania, których trzeba pilnować

- Jedna integracja: Yprac Hub `3070715607`, docelowo Mirage/Sandbox.
  Nie przełączać samodzielnie na vanilla CS2, własny serwer/plugin ani inną usługę.
- Po wejściu do mapy/trybu użytkownik raz wkleja ustawienie scenariusza
  do konsoli. Bot, pozycje, kierunki oczu i broń obu stron mają ustawić się
  automatycznie, bez ręcznego indeksu bota i przepisywania kolejnych komend.
- Jeden aktywny pojedynek i bot naraz. Nie nadpisywać bindów ani `autoexec.cfg`.
  CFG jest opcjonalny; UI ma przycisk kopiowania pełnego ustawienia.
- `setpos_player <player_index> <x> <y> [z]` używa indeksu gracza, nie `userid`.
  Prototyp przyjmuje indeks gracza `2` po `bot_kick` i dodaniu jednego bota.
  Osobno zaakceptowano hipotezę indeksu encji/pawn `2` do `ent_setname`;
  nie wywodzić drugiego indeksu z pierwszego. `point_teleport` próbuje ustawić
  orientację bota. Indeksy, oczy, spawn i kolejność podlegają końcowej próbie.
  Nie ma dynamicznego wyszukiwania encji; nie żądamy indeksu od użytkownika.
- Zapis/odczyt pozycji przyjmujemy roboczo jako działający.
  Udokumentowane nazwy Yprac to `savepos`/`loadpos`; dłuższe nazwy
  `saveposition`/`loadposition` nie mają potwierdzenia jako aliasy.
- Wyliczenie kąta w backendzie nie dowodzi możliwości ustawienia oczu bota.
  Założenia komend trzymać w jednym module eksportera, aby dało się je poprawić
  po końcowych próbach bez przebudowy backendu i UI.
- Nie emitować tekstu/nazw z dema jako komend. Walidować współrzędne, kąty,
  broń, mapę i dozwolone polecenia. Manifest i UI wskazują stan
  „niezweryfikowane w grze” do czasu odbioru.
- Stos aplikacji: Django, PostgreSQL, Django-Q2 z brokerem ORM,
  izolowany worker; UI na szablonach Django, HTMX tylko jeśli potrzebne.
  Wybrano prywatny R2 Standard. Nie dodawać osobnego
  frontendu/API, Redis/Celery, LLM ani płatności bez potrzeby lub decyzji.

## Todos i zależności

Status „planowane” nie oznacza implementacji. Zadania bez wspólnej zależności
mogą postępować niezależnie; UI zaczyna się po gotowym backendzie.

| ID | Status | Zakres i warunek odbioru | Zależności |
|---|---|---|---|
| `bootstrap-cli` | Gotowe | Istniejący parser, analiza, kontrakt, CLI, benchmark, Docker i testy | Brak |
| `build-training-exporter` | Gotowy prototyp; bez odbioru w grze | Bot, XYZ, hipoteza orientacji przez `point_teleport`, broń, jedna linia, walidacja i testy; indeksy/gotowość/oczy/synchronizacja do G1 | `bootstrap-cli` |
| `assemble-training-packs` | Gotowe — CLI/logika BE | Wybór/odrzucanie, ZIP, wersjonowany manifest, instrukcja, TXT/CFG; raport v2 lub dokument v1, bez nadpisywania | `build-training-exporter` |
| `define-saas-policies` | Gotowe | R2, e-mail + Steam, 3 dema/7 dni na SteamID, brak retry analizy i usuwanie wejść po próbie | `bootstrap-cli` |
| `build-minimal-web` | Kod, poprawki i review gotowe; integracje zewnętrzne do odbioru | Django/PostgreSQL, prywatny intake R2, Q2, jednorazowy worker, historia i reaper; wymagane prawdziwe R2/Steam/SMTP, migracja profili i odbiór kontenera Linux/Compose | `define-saas-policies` |
| `complete-training-backend` | Kod i lokalny odbiór gotowe | Zapis wyboru, prywatny ZIP na żądanie i komendy/CFG z raportu, bez ponownej analizy; migracja `0003_training_selection`; zewnętrzny odbiór fundamentu G2 nadal otwarty | `build-minimal-web`, `assemble-training-packs` |
| `build-training-ui` | Planowane — następny krok | Konta/Steam, upload, status zadania, raport z ograniczeniami, zapamiętany wybór sytuacji, kopiowanie komend i opcjonalne paczki | `complete-training-backend` |
| `wire-personal-training` | Planowane — G3 | Połączyć UI/BE, dodać deklarowane oceny i proste powtórki; testy aplikacji | `build-training-ui` |
| `add-operations-and-billing` | Planowane — przed odbiorem | Compose/TLS, retencja/usuwanie, backup/odtworzenie, monitoring i limity; abonament tylko po osobnej decyzji | `wire-personal-training` |
| `verify-end-to-end-pilot` | Planowane — aplikacyjne E2E | Upload → raport → paczka → kopiowanie, błędy/retry, uprawnienia, limity, usuwanie i odtworzenie; jeszcze bez próby gry | `wire-personal-training`, `add-operations-and-billing` |
| `prove-scenario-import` | Odłożone na końcowe próby — G1/G4 | Po BE/UI sprawdzić jedną i 10 sytuacji w CS2/Yprac: indeks/gotowość, XYZ, oczy, broń, mapa, restart i jedno wklejenie; poprawić wykryte problemy | `verify-end-to-end-pilot` |
| `benchmark-demo-pipeline` | Częściowo gotowe | Pozostały docelowy VPS, ręczne referencje i ocena trenera; nie blokuje BE/UI | `bootstrap-cli` |
| `validate-paid-training` | Po odbiorze | Prywatny pilot: rzeczywiste treningi, powroty, płatności, opinie i koszt obsługi | `prove-scenario-import`, `benchmark-demo-pipeline` |
| `approve-saas` | Po pilocie | Decyzja właściciela o uruchomieniu/skalowaniu, nie o rozpoczęciu implementacji | `validate-paid-training` |
| `launch-controlled-saas` | Po decyzji biznesowej | Kontrolowany nabór, limity i procedura wyłączenia niedziałającej integracji | `approve-saas` |

Historyczne numery bramek zachowano: **G2 (BE) → G3 (UI) → G1 (gra) → G4
(końcowy odbiór)**. G1 i płatności nie są zależnościami eksportera/BE/UI.

## Jak rozpocząć nową sesję

1. Przeczytać ten plik, `project-plan.md`, `../README.md` i odpowiednią część
   `integration-validation.md`. Sprawdzić stan Git, zachować zastane zmiany;
   w momencie przekazania wiele plików było nieśledzonych.
2. Rozpocząć `build-training-ui`; osobno dokończyć odbiór R2/Steam/SMTP.
   `complete-training-backend` jest zrealizowane; nie zaczynać go ani fundamentu od nowa.
   Przed uruchomieniem weba zastosować `0003_training_selection`.
   Obejrzeć istniejące moduły `exporting.py`, `packs.py`, `cli.py` i ich testy.
   Nie przepisywać parsera, reguły orientacji ani gotowego składania paczek.
   Django i polityki już istnieją; nie dodawać drugiego storage ani retry analizy.
3. Implementować i odbierać kolejne zadania według zależności. Po zadaniu
   aktualizować statusy w obu planach; nie zatrzymywać prac z powodu braku
   dostępu do CS2 na etapie BE/UI.
4. Używać poleceń z README: `uv run ruff check .`,
   `uv run ruff format --check .`, `uv run pytest`, `uv build`.
   Jeśli `uv` nie jest w PATH, istniejące `.venv/bin/python -m pytest`
   i `.venv/bin/ruff` były dostępne w poprzedniej sesji.
   Integracja parsera wymaga uprawnionego lokalnego dema przez
   `CS_MAP_TRAINER_DEMO`; brak próbki nie oznacza pozytywnego wyniku.

Przykładowa wiadomość startowa:

> Przeczytaj docs/implementation-todos.md i docs/project-plan.md.
> Kontynuuj od build-training-ui. Fundament i backend treningowy już istnieją;
> zapis wyboru, prywatny eksport komend i opcjonalny ZIP są gotowe.
> R2/Steam/SMTP wymagają odbioru z prawdziwą konfiguracją. Eksporter i paczki
> są gotowym prototypem, bez próby w grze. Obowiązuje kolejność BE → UI →
> końcowe próby CS2/Yprac; komendy przyjmujemy jako założenie implementacyjne.
> Zachowaj istniejący kod i zastane zmiany.
