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
  Jest minimalny backend w `src/cs_map_trainer/web/`, bez treningowego UI.
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
  Następny etap: `complete-training-backend`, bez przepisywania fundamentu.
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

## Najbliższy zakres: dokończenie backendu G2

1. Dodać autoryzowany wybór/odrzucanie scenariuszy z zapisanego raportu,
   wykorzystując `select_scenarios`, bez ponownego parsowania usuniętego dema.
2. Połączyć ten wybór z `build_pack` i autoryzowanym pobieraniem paczek
   oraz eksportem pojedynczej sytuacji. Zachować kontrolę właściciela,
   ograniczenia eksportera i `unverified_in_game`.
3. Rozszerzyć testy przepływu od prywatnego raportu do selekcji i eksportu:
   cudze/usunięte wyniki, błędne ID, pusty wybór i nieobsługiwane sytuacje.
4. W skonfigurowanym środowisku osobno odebrać R2/Steam/SMTP oraz kontener
   Linux, zastosować `0002_minimize_steam_profiles` i sprawdzić awarię workera.
   Brak tego środowiska nie oznacza pozytywnego odbioru ani potrzeby
   przepisywania działającej logiki.

Treningowy UI zaczyna się po dokończeniu backendu. Pakiet trenera/akademii,
płatności i próby CS2/Yprac pozostają poza najbliższą iteracją.

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
| `complete-training-backend` | Planowane — następny krok G2 | Rozszerzyć istniejącą analizę i historię o selekcję oraz autoryzowane paczki/eksport; gracz wynika z powiązania Steam | `build-minimal-web`, `assemble-training-packs` |
| `build-training-ui` | Planowane — po BE | Konta/Steam, upload, status zadania, raport z ograniczeniami, selekcja sytuacji, paczki i kopiowanie komend | `complete-training-backend` |
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
2. Dokończyć odbiór integracji R2/Steam/SMTP i zacząć `complete-training-backend`.
   Poprawki review są zamknięte; nie zaczynać ich ani fundamentu od nowa.
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
> Kontynuuj od complete-training-backend. Fundament Django już istnieje;
> R2/Steam/SMTP wymagają odbioru z prawdziwą konfiguracją. Eksporter i paczki
> są gotowym prototypem, bez próby w grze. Obowiązuje kolejność BE → UI →
> końcowe próby CS2/Yprac; komendy przyjmujemy jako założenie implementacyjne.
> Zachowaj istniejący kod i zastane zmiany.
