# CS Map Trainer

Narzędzie do przygotowania treningu własnych pojedynków z CS2. Obecnie **CLI czyta
dema `.dem` z Mirage i Dust2, wyświetla graczy i analizuje porównywalne wygrane oraz
przegrane pojedynki**. Wynikiem jest raport JSON z kandydatami do treningu
przegranych sytuacji i ich ustawieniem przestrzennym. Działa też
walidator kontraktu scenariuszy v1.

**Jest prototyp eksportu do konsoli/CFG i paczek ZIP, nie ma potwierdzonego
importu do gry.** Cel to
[Yprac Hub by Yesber, Workshop `3070715607`](https://steamcommunity.com/sharedfiles/filedetails/?id=3070715607),
Mirage lub Dust2 / Sandbox. Eksporter zakłada osobno indeks gracza bota `2` i indeks jego
encji/pawn `2` po usunięciu botów. Nie wyszukuje indeksów dynamicznie.
Pozycje, kierunek oczu, broń, kolejność wykonania i zgodność mapy nadal wymagają
potwierdzenia w grze. Wyniki mają status `unverified_in_game`.
Nie planujemy własnego serwera/pluginu.

Istnieje też **aplikacja Django/PostgreSQL/Django-Q2 z treningowym UI**:
konta e-mail, SteamID64 podawane przy demie, prywatny upload R2, jednorazowa analiza
i prywatna historia z zapamiętywaniem wyboru sytuacji, eksportem pojedynczej
linii komend i opcjonalnymi paczkami ZIP. Responsywne szablony korzystają ze
stylistyki Tactical HUD z `design/`, bez zewnętrznych skryptów i fikcyjnych statystyk.
Są deklarowane oceny treningu i prosta kolejka powtórek, bez telemetrii z gry.
Jest też moduł Stripe Billing: **Free — 3 analizy na miesiąc kalendarzowy UTC;
Pro — 7,99 USD/mies. bez limitu liczby analiz na koncie serwisu**.
Integracje z rzeczywistym R2, SMTP i Stripe wymagają
konfiguracji i osobnej próby przed wdrożeniem; testy z atrapami nie są jej dowodem.

## Uruchomienie

Wymagany [uv](https://docs.astral.sh/uv/) i Python 3.11 lub nowszy.
`uv` może pobrać zgodny interpreter.

```sh
uv sync --locked
uv run cs-map-trainer validate-scenarios tests/fixtures/synthetic-scenarios.json
uv run cs-map-trainer schema
```

### Własne demo

Obsługiwane są nieskompresowane dema CS2 `.dem`, do 1 GiB, z map
`de_mirage` i `de_dust2`. Mapa jest odczytywana z nagłówka dema, nie z nazwy pliku.
Pliki CS:GO, archiwa i pozostałe mapy są jawnie odrzucane.

```sh
mkdir -p data results
# Umieść swoje demo w data/match.dem.
uv run cs-map-trainer players data/match.dem
uv run cs-map-trainer analyze data/match.dem \
  --steam-id 76561198000000001 \
  --output results/report.json

# Tak samo dla uprawnionego dema Dust2; użyj SteamID z polecenia players.
uv run cs-map-trainer players data/dust2.dem
uv run cs-map-trainer analyze data/dust2.dem \
  --steam-id 76561198000000001 \
  --output results/dust2-report.json
```

SteamID w przykładzie jest syntetyczny: zastąp go identyfikatorem z polecenia
`players`. Skład może zawierać obie strony i zmiany drużyn; pokazywana strona
gracza jest ostatnią zaobserwowaną, a analiza używa stron z chwili pojedynku.
Boty bez SteamID nie są oferowane do wyboru.

Bez `--output` JSON trafia na stdout, a diagnostyka na stderr. `--output` wymaga
istniejącego katalogu i **nie nadpisuje istniejącego pliku**.

Nowe raporty analizy mają **`analysis_version: 3`** i zapisane nazwy lokacji
z demka. Raporty v2 pozostają obsługiwane, ale nie mają tych danych.
Kontrakt dokumentu scenariuszy nadal ma `schema_version: 1`; to osobny format.
Statystyki w obu obsługiwanych wersjach raportu uwzględniają wygrane i porażki;
`groups[].observations` jest ich sumą.

Raport zawiera:

- `status`: `candidates_ready` albo `no_eligible_duels`;
- `scenario_document`: dokument v1 ze scenariuszami lub `null`, gdy brak kandydatów;
- `scenario_locations`: słownik po `scenario_id`, zawierający `snapshot_tick`,
  `source: "m_szLastPlaceName"` oraz surowe nazwy `player` (ofiara) i `opponent`
  (zabójca) dla wybranych przegranych pojedynków; brak nazwy jest jawnym `null`;
- `excluded` i `excluded_wins`: ticki rozstrzygnięć oraz przyczyny odrzuceń
  odpowiednio przegranych i wygranych starć;
- `deaths_considered`/`eligible_candidates` i `kills_considered`/`eligible_wins`:
  liczbę rozważanych oraz zakwalifikowanych zdarzeń dla obu wyników;
- `groups`: grupy podobnych ustawień z liczebnością próby, `wins`, `losses`
  i `win_rate` jako ułamek 0–1, stroną, bronią, komórkami obu pozycji i kontekstem;
- `metrics`: czas ścienny, CPU, rozmiar wejścia i szczyt RSS całego procesu
  oraz liczniki blokowych operacji I/O z `getrusage` dla całego procesu
  (na Windows RSS i te liczniki są jawnie niedostępne);
- wersje parsera/reguł, hash dema, mapę/build i ograniczenia rekonstrukcji.

W raporcie webowym główną sekcją jest **Choose your duels**, służąca do wyboru
konkretnych przegranych pojedynków do treningu. Ostrzeżenia dotyczące danego
scenariusza pozostają widoczne, a identyfikatory, ticki, pozycje i kąty są
w rozwijanych szczegółach. Wspólne ograniczenia rekonstrukcji opisujemy raz,
w sekcji **Limitations and exclusions**.

Zwijana sekcja **Duel statistics** poniżej listy pokazuje statystyki grup:
próby, wygrane, przegrane i win rate jako procent (np. 12.5%). Dotyczą one
wszystkich zakwalifikowanych pojedynków, niezależnie od bieżącego wyboru do
treningu; zapisany JSON nadal używa ułamka 0–1. Grupy są przybliżone, sortowane
według liczby przegranych i nie stanowią oceny umiejętności. Komórki siatki
w szczegółach technicznych nie są nazwami miejscówek.

Karty pojedynków pokazują **nazwy lokacji ofiary i zabójcy odczytane z demka**
na Mirage i Dust2. Awpy 3.1.1 nie zwraca ich w `snapshots()`, ale udostępnia
surowe pole przez `Demo.ticks(props=["m_szLastPlaceName"], players_only=True)`.
To dodatkowy przebieg po demie, wykonywany raz, tylko gdy wybrano scenariusze.
Z wyniku zachowujemy wyłącznie nazwy potrzebnych graczy w dokładnych
`snapshot_tick`, przed pierwszym obrażeniem, **nie w ticku śmierci**.
Nie interpolujemy między tickami i nie zastępujemy nazw mapowaniem XYZ.
Puste wartości pozostają `null`, mają ostrzeżenie w logu i widoczną etykietę
`Location unavailable in demo`; nie wykluczają poprawnego pojedynku.
Błędy struktury odczytu i duplikaty potrzebnej pary tick/gracz są jawne.

`m_szLastPlaceName` to ostatni nazwany obszar raportowany przez grę.
Może być szerszy niż społecznościowy callout i nie gwarantuje natychmiastowej
zmiany nazwy na granicy obszarów. `callouts.py` jedynie formatuje zapisane nazwy,
np. `BombsiteA → A Site`, a dla Mirage `SnipersNest → Window`, `Shop → Market`.
Surowe nazwy, tick i źródło są dostępne w szczegółach karty. Nie pobieramy
geometrii map, radarów ani innych assetów; usunięto ręczne prostopadłościany.

Lokacje zapisują się w raporcie przed usunięciem wejściowego demka. Starsze
raporty bez metadanych pokazują `Not recorded in this report` z informacją
o konieczności ponownego przesłania demka. Nie można odzyskać tych danych
z usuniętego wejścia. Kontrakt scenariuszy, grupowanie, wybory i eksport
pozostają bez zmian; metadane lokacji nie trafiają do komend treningowych.

Domyślnie wybieranych jest maksymalnie 10 scenariuszy, z pierwszymi obrażeniami
między oboma graczami w końcowym oknie 128 ticków przed śmiercią.
Parametry można zmienić przez `--max-scenarios` i `--contact-window-ticks`.
To przybliżenie początku wymiany obrażeń, **nie wykrycie pierwszego kontaktu
wzrokowego**. Wspólna migawka pochodzi dokładnie z ticka poprzedzającego te
obrażenia, a nie z chwili śmierci. Dane są pobierane zbiorczo dla kandydatów.

Wykluczamy m.in. world/samobójstwa, teamkille, granaty i noże, trafienia przez
przeszkody/smoke wskazane przez zdarzenie śmierci, kontakt z obrażeniami od
trzeciej osoby, brak wspólnej migawki oraz znaną pozycję kucającą lub w powietrzu.
Brakujące informacje o efektach są oznaczane jako nieznane, nie jako brak efektu.
Kąty gracza zostają zachowane; yaw jest tylko normalizowany do zakresu kontraktu.
Awpy nie zwraca roll w migawce, więc zapisujemy zero z jawnym `roll_not_recorded`.
Gdy przeciwnikowi brakuje pitch lub yaw, uzupełniamy tylko brakującą składową
kierunkiem od jego pozycji ku pozycji gracza z tej samej migawki, z oznaczeniem
`opponent_aim_inferred_toward_player`. To przybliżenie zakłada jednakową wysokość
oczu stojących uczestników, nie odczyt kierunku z dema ani dowód celowania
w gracza przed kontaktem. Dostępne kąty pozostają zachowane; kąty gracza
nie są zgadywane. Brak pozycji, nieprawidłowe kąty i nieokreślony kierunek
nadal wykluczają sytuację. Ta sama reguła dotyczy porównywalnych wygranych;
grupy z przybliżeniem są oddzielone od grup z kompletem kątów z dema.
Wersja reguł tej analizy to `damage-window-v3`; nowe raporty mają format v3,
a kontrakt scenariuszy v1.

Grupy są prostą heurystyką: komórki 256 jednostek na każdej osi dla obu pozycji,
strona gracza, obie bronie i identyczny zestaw oznaczeń ograniczeń. Znane oślepienie
i nieznany stan efektu nie są mieszane z potwierdzonym brakiem oślepienia.
Wygrane są oglądane z perspektywy wybranego gracza, nie ofiary zdarzenia.
Te same filtry, okno obrażeń i wymagania migawki obowiązują dla obu wyników.

Grupy są nadal sortowane według **liczby przegranych**, nie według win rate.
Mianownik win rate to tylko zakwalifikowane rozstrzygnięte starcia w danej grupie,
nie wszystkie spotkania, ekspozycja na pozycji czy ogólna skuteczność gracza.
Podajemy rozmiar próby, bez ocen umiejętności z małej liczby obserwacji.
Wyniki grup liczymy przed ograniczeniem liczby scenariuszy. Grupy samych wygranych
nie generują scenariuszy treningowych, a `no_eligible_duels` oznacza brak
przegranych kandydatów, nawet gdy raport zawiera wygrane. Raport nie rekonstruuje
ruchu, pancerza, zdrowia, zachowania bota ani zasłonięcia przez smoke.
Rewizja `unverified-demo-build-*` oznacza **niepotwierdzoną zgodność mapy**.

### Eksport Yprac i paczki treningowe — prototyp

Oba polecenia przyjmują raport analizy v2 albo dokument scenariuszy v1.
Identyfikatory są w `scenario_document.scenarios[].scenario_id` raportu
lub `scenarios[].scenario_id` dokumentu. Przykładowe ID zastąp rzeczywistymi:

```sh
# Jedna linia do konsoli na stdout; ostrzeżenia na stderr.
uv run cs-map-trainer export-scenario results/report.json \
  --scenario-id ID_SCENARIUSZA

# Opcjonalny CFG tej samej sytuacji, bez zmieniania bindów i autoexec.cfg.
uv run cs-map-trainer export-scenario results/report.json \
  --scenario-id ID_SCENARIUSZA --cfg --output results/scenario.cfg

# Domyślnie wszystkie dostępne scenariusze, bez CFG.
uv run cs-map-trainer build-pack results/report.json --output results/training.zip

# Jawny wybór i odrzucenie; opcje można powtarzać.
uv run cs-map-trainer build-pack results/report.json \
  --include ID_PIERWSZY --include ID_DRUGI --reject ID_ODRZUCONY \
  --include-cfg --output results/selected-training.zip
```

Wybór zachowuje kolejność dokumentu. ID nieznane, powtórzone, jednocześnie
wybrane i odrzucone oraz pusty wynik kończą się błędem. Bez `--include`
uwzględniamy wszystkie nieodrzucone sytuacje. Raport bez kandydatów nie tworzy
paczki; nieobsługiwana wybrana sytuacja powoduje błąd całego eksportu,
zamiast zostać po cichu pominięta. Można ją jawnie odrzucić.

ZIP zawiera `manifest.json`, wybrane `scenarios.json`, `README.txt`,
`console/scenario-NNNN.txt` i opcjonalnie `cfg/scenario-NNNN.cfg`.
Każdy TXT ma **jedną linię jednego scenariusza** do wklejenia po wejściu
do właściwej mapy/Sandbox z klientem Yprac. Instrukcje wskazują mapę każdego
pliku; przy paczce mieszanej Mirage/Dust2 trzeba zmieniać sesję na właściwą mapę.
Manifest zachowuje `yprac_hub_mirage_sandbox` dla Mirage, używa
`yprac_hub_dust2_sandbox` dla Dust2 i `yprac_hub_multi_map_sandbox` dla wyboru
mieszanego. Format paczki pozostaje v1; stare manifesty Mirage są obsługiwane.
Powtórzenie polega na ponownym
wklejeniu tej samej linii, nie na niepotwierdzonym zachowaniu `restart`.
Pliki są numerowane niezależnie od ID; manifest mapuje je na źródłowe sytuacje
i zapisuje wybór, odrzucenia, źródła, ograniczenia i wersję eksportera
`yprac-sandbox-prototype-v1`. Nie dołączamy dema ani assetów.
Opcjonalny CFG można skopiować bez nadpisywania plików do własnego katalogu
`game/csgo/cfg/cmt_v1` i uruchomić np. `exec cmt_v1/scenario-0001.cfg`.
Nie jest to wymagane przy kopiowaniu TXT do konsoli.
Paczki zawierają metadane uczestników — traktuj je jako prywatne.
Nowe artefakty są publikowane w całości bez nadpisywania istniejących ścieżek;
rodzic katalogu wyjściowego musi już istnieć.

Sekwencja usuwa boty, dodaje jednego właściwej strony i używa
`setpos_player 2`. Osobne, zaakceptowane założenie indeksu **encji** `2`
pozwala nadać jej `targetname` przez `ent_setname cmt_v1_bot 2`.
Pomocniczy `point_teleport` próbuje odtworzyć pozycję i orientację bota.
**Indeks gracza nie jest gwarancją indeksu encji**, a obrót modelu nie
potwierdza kierunku oczu. Obsługa broni korzysta z komend chatu Yprac.
Gotowość bota, tworzenie encji, kolejność entity I/O i chatu oraz faktycznie
aktywna broń są niezweryfikowane. Nie dodajemy `wait` ani zgadywanych opóźnień;
średniki same nie zapewniają synchronizacji.

Używaj wyłącznie w **odizolowanej lokalnej sesji treningowej** z jednym
człowiekiem. Komendy włączają `sv_cheats`, wyłączają limit/równoważenie drużyn,
zmieniają quota/stop botów, drużynę, pozycję, kąty i broń gracza oraz nazwę
encji `2`. Nie zapisują poprzednich wartości; manifest zawiera pełną listę
zmian. Po treningu opuść sesję i sprawdź ustawienia przed dalszą grą.
Nie używaj na matchmakingu ani współdzielonym serwerze.

Walidacja eksportera dopuszcza tylko `de_mirage` i `de_dust2`, jawną listę broni palnych,
skończone XYZ w zakresie ±16384 i roll `0`. Zachowuje pitch/yaw i oznaczenia
przybliżenia przeciwnika. Budżet pojedynczej linii to 1023 bajty ASCII;
to limit prototypu, nie potwierdzona pojemność konsoli w danym buildzie.
Przekroczenie limitów daje błąd, nie zaokrąglenie lub obcięcie komend.
Syntetyczny `tests/fixtures/synthetic-scenarios.json` jest celowo odrzucany.
Poprawne wygenerowanie paczki **nie zalicza G1**.

### Benchmark

```sh
uv run cs-map-trainer benchmark data/match.dem \
  --steam-id 76561198000000001 --runs 3 \
  --output results/benchmark.json
```

Każda próba uruchamia rzeczywiste `analyze` w **nowym procesie**, dzięki czemu
szczyt RSS nie przechodzi między próbami. Raport zawiera metryki każdej próby,
rozmiar JSON-a, wersje, parametry i hash wejścia. Różne wyniki analizy między
próbami kończą benchmark błędem, zamiast tworzyć mylące porównanie.
Domyślny limit pojedynczej próby to 300 sekund (`--timeout-seconds`).

`process_wall_seconds` obejmuje start interpretera, importy, pipeline i wypisanie
JSON-a; CPU wewnątrz `metrics` dotyczy samego pipeline'u, łącznie z jego wątkami.
Pierwsza próba ma etykietę `first_observed`, kolejne `repeat`. Nie czyścimy cache
systemu operacyjnego, więc **pierwsza próba nie jest gwarantowanym cold run**.
Liczniki operacji blokowych nie są pomiarem bajtów I/O i mogą być zerowe przy
odczycie z cache. Wyniki odnoszą się do uruchamiającej maszyny lub kontenera,
nie są obietnicą wydajności na VPS.

### Docker

Zamiast lokalnego Pythona i `uv` można użyć Dockera:

```sh
docker build -t cs-map-trainer .
docker run --rm cs-map-trainer
docker run --rm cs-map-trainer validate-scenarios /app/examples/synthetic-scenarios.json
docker run --rm cs-map-trainer schema
```

Pierwsze uruchomienie bez argumentów pokazuje pomoc. To CLI, nie serwer WWW:
kontener kończy pracę po wykonaniu polecenia i nie wymaga portów ani bazy danych.

Własne pliki można podpiąć z katalogu `data/` tylko do odczytu:

```sh
mkdir -p data
# Umieść dokument scenariuszy w data/scenarios.json.
docker run --rm \
  --mount "type=bind,src=$(pwd)/data,dst=/data,readonly" \
  cs-map-trainer validate-scenarios /data/scenarios.json
```

Kontener działa jako użytkownik `10001:10001`, więc podpięte pliki muszą być dla
niego czytelne. Obraz zawiera zależności wykonawcze z `uv.lock`, bez narzędzi
deweloperskich. `.dockerignore` dopuszcza wyłącznie kod, pliki budowania i jedną
syntetyczną próbkę; prywatne dema, wyniki, `.env` i lokalne środowiska nie trafiają
do kontekstu budowania. Odczyt i analiza również nie wymagają sieci: parser nie
pobiera map ani innych assetów.

Analiza dema z raportem zapisanym na hoście:

```sh
mkdir -p data results
docker run --rm \
  --mount "type=bind,src=$(pwd)/data,dst=/data,readonly" \
  cs-map-trainer players /data/match.dem
docker run --rm \
  --mount "type=bind,src=$(pwd)/data,dst=/data,readonly" \
  cs-map-trainer analyze /data/match.dem \
  --steam-id 76561198000000001 > results/report.json
```

Po zmianach kodu/zależności przebuduj obraz. Raport może zawierać SteamID
i pozycje graczy — nie publikuj go jako logu. Przy przekierowaniu sprawdź kod
wyjścia polecenia: błąd nie daje poprawnego raportu.

W tym samym poleceniu Dockera można zastąpić `analyze` przez `benchmark`
i dodać `--runs 3`, aby uzyskać raport pomiarów.

Walidator zwraca kod `0` dla poprawnego dokumentu, `1` dla błędu odczytu lub
walidacji i `2` dla błędu użycia CLI. Błędy trafiają na stderr, bez wypisywania
wartości pól dokumentu. `schema` wypisuje JSON Schema na stdout.
Polecenia dem również zwracają `1` przy błędzie i `2` przy niepoprawnych
argumentach. Poprawnie zakończona analiza bez kandydatów zwraca `0` i jawny
status `no_eligible_duels` — nie tworzy zastępczych scenariuszy.

Scenariusz zawiera identyfikatory źródła i wersji, mapę/build/rewizję,
wspólny tick migawki, uczestników, światowe XYZ, kąty, broń i jawne ograniczenia.
Pola są wymagane, dodatkowe pola i niejawna konwersja typów są odrzucane.
Wersja schematu musi być dokładnie liczbą całkowitą `1`.
Tick migawki musi poprzedzać śmierć; pierwszy kontakt może być śmiertelny.
Identyfikator rewizji mapy nie jest sam w sobie dowodem zgodności geometrii.

Próbka `tests/fixtures/synthetic-scenarios.json` jest całkowicie syntetyczna:
nie opisuje prawdziwej mapy, graczy ani dema i nie nadaje się do treningu.
Puste `limitations` oznacza wyłącznie pustą listę zgłoszeń, nie dowód braku efektów.
Eksporter ma własne ograniczenia opisane powyżej; nie są dowodem zgodności gry.

## Rozwój

Testy backendu wymagają PostgreSQL 16 z użytkownikiem mającym prawo tworzenia
bazy testowej; testy CLI/jednostkowe nie potrzebują działającej bazy.
Ustaw `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`.
`pytest` używa osobnej konfiguracji `tests/web_settings.py`, atrap R2/Stripe
i skrzynki e-mail w pamięci, bez sekretów wdrożeniowych.

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build
```

Awpy 3.1.1 jest przypiętym parserem, a `uv.lock` obejmuje jego zależności.
Domyślne testy nie pobierają dem. Test integracyjny można uruchomić na lokalnym,
dopuszczonym do przetwarzania demie Mirage lub Dust2 zawierającym kwalifikujące się starcia:

```sh
CS_MAP_TRAINER_DEMO=data/match.dem uv run pytest tests/integration
# Alternatywnie: CS_MAP_TRAINER_DEMO=data/dust2.dem
```

Pipeline oraz powtarzane przebiegi w osobnych procesach sprawdzono na publicznych
próbkach projektu
[awpy-fixtures](https://github.com/pnxenopoulos/awpy-fixtures):
`valve-de_mirage-472514809`, SHA-256
`2e0a4f9aa257af9d8e2c934dcbd6cb6a8c48483c264904ecc27218dd7d360506`.
Druga próbka to `faceit-de_mirage-6de46e85`, zawierająca dogrywkę, SHA-256
`b1295d828786d637b06c2d2accbdc219600301642bd3a2f263ccdc404689ffde`.
Nie dołączamy dema ani danych zawodników do repozytorium lub obrazu.
To próby integracyjne dwóch źródeł, nie pełny benchmark na docelowym VPS,
ręczne oznaczenie każdego kontaktu ani ocena trenera.

Na uprawnionym lokalnym demie Dust2 sprawdzono również analizę, zgodność XYZ
i kątów z migawkami, eksport paczki oraz rzeczywisty proces potomny parsera
używany przez worker. Nagłówek potwierdził `de_dust2`, build `10924`.
Nie jest to odbiór rzeczywistego R2 ani komend w CS2/Yprac.

## Aplikacja webowa i backend

Stos: Django 5.2, PostgreSQL, Django-Q2 z brokerem ORM i jeden worker.
UI to szablony Django, lokalne CSS i niewielki JavaScript, bez osobnego
frontendu/API. Ścieżki `/backend/` są
prywatnymi operacjami monolitu z sesją Django i CSRF. Obraz CLI pozostaje osobny.

### Interfejs gracza

| Strona | Ścieżka |
|---|---|
| Strona główna i upload | `/` |
| Konto, weryfikacja e-mail, podpowiedź SteamID i usunięcie konta | `/account/` |
| Prywatna historia ze stronicowaniem | `/history/` |
| Status zadania, raport i zapis wyboru/odrzuceń | `/uploads/<id>/` |
| Jedna aktywna sytuacja, kopiowanie komend i ocena | `/uploads/<id>/training/` |
| Nowe/do powtórki, nadchodzące i nietrafne | `/practice/` |

Logowanie przekierowuje do historii. Formularze allauth (rejestracja,
potwierdzenie adresu, reset hasła i wylogowanie) korzystają ze wspólnej powłoki.
Przed weryfikacją e-mail nie wysyłamy dema. Upload wymaga SteamID64 i potwierdzenia
uprawnień, pokazuje rzeczywisty postęp transferu i wysyła surowy plik prosto do R2.
UUID rezerwacji i etap transferu pozostają w pamięci sesji przeglądarki,
oddzielnie dla konta, razem z wybranym SteamID. Przy ponowieniu trzeba wybrać ten sam plik; po błędzie
potwierdzenia udanego transferu nie wysyłamy pliku drugi raz. Nie jest to retry
parsowania. Po wygaśnięciu rezerwacji wymagany jest nowy upload.

Status aktywnego zadania odświeża się co 5 sekund, maksymalnie przez 10 minut;
po błędzie sieci odświeżanie zatrzymuje się z komunikatem i ręcznym przyciskiem.
Nie pokazujemy pozorowanych procentów analizy. Raport rozdziela liczebność próby,
porażki i wygrane, ograniczenia i brak kandydatów. Nie nazywamy wyniku werdyktem
o błędzie. Nie pokazujemy niezmierzonych wyników meczu, reakcji ani mapy/radaru
bez zweryfikowanego podkładu.

Zapisz wybór przed przejściem do treningu; wybór paczki nie może być pusty.
Główna ścieżka to skopiowanie pełnej linii jednej sytuacji. Odmowa dostępu
do schowka daje komunikat i zaznacza tekst do ręcznego skopiowania. ZIP/CFG są
opcjonalne. Raporty, wybór i oceny działają bez ponownego parsowania lub dostępu do R2.

### Deklarowane oceny i powtórki

Po ćwiczeniu można samodzielnie oznaczyć sytuację: **trudne** (powtórka za 1 dzień),
**wykonane** (za 3 dni), **łatwe** (za 7 dni) lub **nietrafne** (bez terminu,
poza aktywną kolejką do ręcznego przywrócenia). Terminy są liczone na serwerze
od chwili oceny i wyświetlane w UTC. Ponowna ocena zastępuje poprzednią
i wyznacza nowy termin; nie prowadzimy historii prób ani statystyk wygranych.
Przywrócenie usuwa bieżącą ocenę i czyni sytuację ponownie nową.

`PracticeReview` przechowuje tylko bieżącą ocenę, czas i termin na parę
raport/scenariusz. Kolejka bierze wszystkie gotowe prywatne raporty, respektuje
ich aktualny wybór, sortuje po terminie (nowe po dacie raportu), a następnie
po ID raportu i scenariusza, i stronicuje wynik po 20 sytuacji. Nie ogranicza
się do ostatnich 100 raportów. Niewybrane sytuacje zachowują oceny, ale nie są
w kolejce. „Nietrafne” nie zmienia wyboru paczki; zmień go osobno w raporcie.
Usunięcie raportu lub konta usuwa również oceny i terminy.

**Ocena jest deklaracją, nie wynikiem z CS2.** Kopiowanie/pobranie nie oznacza
wykonania ćwiczenia. Nie ma automatycznego uruchamiania gry, powiadomień,
pomiaru poprawy ani potwierdzonego importu Yprac.

**Polityka:** publiczna rejestracja e-mail/hasło i potwierdzenie adresu;
bez powiązywania ani logowania Steam. Przy każdym uploadzie wymagany jest
`player_steam_id`: SteamID64 analizowanego gracza (tekst, 17 cyfr ASCII;
białe znaki na brzegach są usuwane). Jego obecność w demie jest sprawdzana,
ale własność profilu nie jest weryfikowana. Ostatnie SteamID przyjęte przy nowej
rezerwacji zapisujemy na koncie jako edytowalną podpowiedź na kolejne uploady,
także z innego urządzenia. Modal przy polu pokazuje instrukcję Steam → Account
details → Steam ID z lokalnymi ilustracjami poglądowymi, nie screenshotami;
instrukcja jest w domyślnie zamkniętym dialogu otwieranym przyciskiem, nie w sekcji
na dole strony. W przeglądarkach obsługujących `commandfor` przycisk działa też
bez JavaScript. Free obejmuje **3 przyjęte dema na
konto w miesiącu kalendarzowym UTC**, z rezerwacją przy rozpoczęciu uploadu i jednym
aktywnym zadaniem. 1 GiB jest wyłącznie technicznym limitem pojedynczego pliku.
Pro kosztuje **7,99 USD miesięcznie** i usuwa limit liczby analiz na koncie,
ale nie limit rozmiaru, jedno aktywne zadanie ani globalną wyłączność parsera.
Miesiąc Free resetuje się pierwszego dnia o 00:00 UTC. Wszystkie naliczone
analizy miesiąca, również z czasu Pro, są uwzględniane po powrocie do Free.
Zły/nieobsługiwany plik zużywa przyjęcie, błąd infrastruktury zwalnia kwotę.
Niedokończona rezerwacja wygasa bez naliczenia. Brak wskazanego gracza w demie
zużywa przyjęcie. Zmiana SteamID nie resetuje limitu ani aktywnego zadania;
różne konta mogą wskazać to samo SteamID bez współdzielenia raportów.

Demo trafia z przeglądarki do prywatnego R2 Standard, nie przez web. Backend
tworzy multipart upload z jedną częścią, podpisuje dokładny `Content-Length`,
a następnie sam listuje część i kończy upload. Przeglądarka wysyła surowy `File`
lub `Blob` przez `PUT`, nie formularz `multipart/form-data`; długość nagłówka
ustawia przeglądarka z rozmiaru ciała. Zakończenie/abort unieważnia identyfikator
uploadu, więc stary URL nie może później podmienić wejścia workera.

Worker potrzebuje tymczasowej lokalnej kopii dla Awpy. **Po pierwszej próbie,
także nieudanej, usuwa ją oraz wejście w R2. Nie ma automatycznego retry analizy.**
Nowa próba wymaga nowego uploadu; duplikat komunikatu kolejki nie parsuje drugi
raz. Metadane, raport, scenariusze i wygenerowane komendy zostają w prywatnej
historii aż do usunięcia przez użytkownika/konta. Brak kandydatów i brak możliwości
eksportu konkretnej sytuacji są jawnie rozróżniane.

Sprzątanie działa także niezależnie od workera: porzucone uploady/zadania wygasają
po 24 h, utracony worker po 900 s, nieudane usuwanie jest oznaczane i ponawiane.
Nowy upload jest blokowany do usunięcia poprzedniego wejścia, aby awaria
sprzątania nie pozwalała gromadzić kolejnych dem mimo zwalniania kwoty.
Lifecycle R2 stanowi dodatkowe zabezpieczenie; nie gwarantuje usunięcia w dokładnej
sekundzie. Po usunięciu konta minimalna ewidencja SteamID i kwoty pozostaje do końca
bieżącego miesiąca UTC i do zakończenia cleanupu. Podpowiedź SteamID jest kasowana
razem z kontem. Nie ma blokady SteamID ani kwoty między kontami; nowa rejestracja
dostaje osobny limit Free. Operacje usunięcia konta
wymagają hasła i zakończenia aktywnego zadania. Usunięcia należy uwzględnić
także w przyszłej procedurze odtwarzania backupu.

### Konfiguracja i uruchomienie

Skopiuj `.env.example` do `.env`, ustaw własne `DJANGO_SECRET_KEY` i `PGPASSWORD`
oraz dane prywatnego R2 i SMTP. Klucz Steam Web API nie jest już potrzebny;
trasy Steam login/callback i social connections są wyłączone. Sekretów nie
dodawaj do Git. Historyczna migracja `0002_minimize_steam_profiles`
usuwała nadmiarowe pola ze starszych profili. Migracja `0003_training_selection`
dodaje zapis wyboru przy wyniku; istniejące raporty domyślnie obejmują wszystkie
sytuacje i nie są przepisywane.
Migracja `0004_practicereview` dodaje bieżące oceny i terminy powtórek.
Migracja `0005_billing_accounts` dodaje konta Stripe, stan dostępu i minimalne
potwierdzenia obsłużonych webhooków. Zmiana kwoty Free na miesiąc UTC obejmuje
istniejącą, zachowaną ewidencję uploadów; nie zeruje bieżącego zużycia.
Przed uruchomieniem nowego UI zastosuj wszystkie migracje.
Migracja `0007_account_upload_players` kopiuje SteamID do istniejących uploadów
i podpowiedzi konta, usuwa `SteamIdentity` oraz przenosi limity i ograniczenia
bazodanowe na właściciela. Raporty, oceny, bieżące zużycie konta i subskrypcje
Stripe są zachowane. Jest **nieodwracalna**: wpisany identyfikator nie pozwala
odtworzyć zweryfikowanej własności. Zastosuj ją przy zatrzymanym intake i workerach,
z backupem bazy; nie cofaj samego obrazu na starszy kod po migracji.
`DJANGO_DEBUG=1` jest wyłącznie do lokalnego HTTP; produkcja wymaga HTTPS,
`DJANGO_DEBUG=0`, poprawnych hostów i originów.

```sh
docker compose build
docker compose up -d db
docker compose run --rm web cs-map-trainer-web migrate --noinput
docker compose run --rm web cs-map-trainer-web createsuperuser
# UWAGA: polecenie zastępuje CORS/lifecycle wskazanego bucketa.
# Użyj dedykowanego, prywatnego bucketa wyłącznie na wejściowe dema.
docker compose run --rm web cs-map-trainer-web configure_r2 \
  --origin http://localhost:8000
docker compose up -d web worker maintenance
```

W R2 wyłącz publiczny dostęp i publiczną domenę. Token wykonawczy ogranicz do
dedykowanego bucketa; konfiguracja CORS/lifecycle może wymagać osobnego tokena
administracyjnego, którego nie pozostawiaj workerowi. Nie korzystamy z S3 POST
policies ani wersjonowania R2. Historia jest w PostgreSQL, nie w buckecie wejść.

Compose ma prywatną bazę, web dostępny na loopback `:8000`, osobny worker
bez roota i wspólny roboczy wolumen dla workera/reapera, bez backupu dem.
Domyślne budżety to 300 s analizy, 4 GiB limitu parsera, kontener workera 5 GiB
i 2 CPU. Nadzorca egzekwuje RSS/czas i zabija proces przy przekroczeniu;
Linux dodatkowo ogranicza przestrzeń adresową, CPU i rozmiar wyniku.
Parser dziedziczy blokadę `.parser.lock` we wspólnym wolumenie roboczym:
śmierć workera nie zwalnia slotu, dopóki sam parser nie zakończy działania.
Proces parsera dostaje jawne `AWPY_DATA_DIR` wewnątrz katalogu danego uploadu.
Nie wymaga `HOME` ani wpisu użytkownika w `/etc/passwd`; ewentualne dane Awpy
są usuwane razem z katalogiem roboczym.
Nie usuwać pliku blokady podczas pracy. Linux kończy parser sygnałem
`SIGKILL` po śmierci rodzica, także podczas wykonania kodu natywnego;
pozostałe systemy POSIX używają watchdogu. Odziedziczona blokada pozostaje
ochroną wyłączności niezależnie od szybkości reakcji watchdogu i blokady PostgreSQL.
To ochronne ustawienia startowe, **nie potwierdzony sizing VPS**. Potrzebny jest
także zapas RAM dla weba/bazy i miejsce na jedno demo oraz osierocone wejścia.
Podstawowy Compose jest wariantem lokalnym. Wariant TLS opisano poniżej;
backup/odtworzenie i pełny monitoring pozostają osobnymi zadaniami.

**Pliki statyczne:** `Dockerfile.web` zbiera CSS/JS i statyki Django podczas
budowania do `/app/static`. Gunicorn ich nie serwuje. Produkcyjny reverse proxy
musi obsługiwać `/static/` z tego katalogu, niezależnie od prywatnych stron:
po uruchomieniu obrazu można skopiować gotowe pliki, np.
`docker compose cp web:/app/static ./deploy-static`, i wskazać proxy katalog
`deploy-static`. Po zmianie obrazu zaktualizuj również statyki.
Bez Dockera uruchom `STATIC_ROOT=/wybrany/katalog uv run cs-map-trainer-web collectstatic --noinput`
i skieruj tam proxy. Nie używaj `runserver --insecure` w produkcji.
Lokalny `runserver` z `DJANGO_DEBUG=1` serwuje statyki aplikacji samodzielnie.

### Lokalne testy UI bez usług zewnętrznych

`compose.ui.yml` jest wyłącznie lokalnym rozszerzeniem do testów interfejsu.
Wymaga `.env` z losowymi `DJANGO_SECRET_KEY` i `PGPASSWORD` oraz opcjonalnymi
`PGDATABASE`/`PGUSER` (domyślnie `trainer`). Plik trzymaj poza Git, z uprawnieniami
`0600`. Nie łącz tego wariantu z konfiguracją produkcyjną.

```sh
docker compose -p cs-map-trainer-ui -f compose.yml -f compose.ui.yml build web
docker compose -p cs-map-trainer-ui -f compose.yml -f compose.ui.yml up -d db mail
docker compose -p cs-map-trainer-ui -f compose.yml -f compose.ui.yml run --rm web \
  cs-map-trainer-web migrate --noinput
docker compose -p cs-map-trainer-ui -f compose.yml -f compose.ui.yml up -d web
```

Aplikacja: `http://localhost:8000`, lokalna skrzynka MailHog:
`http://localhost:8025`. Poczta nie jest wysyłana do internetu. Przeglądarka
Playwright MCP w Docker Desktop na macOS może wejść przez
`http://host.docker.internal:8000`; `localhost` w jej kontenerze oznacza sam
kontener, nie hosta. Przy korzystaniu z linków w wiadomościach używaj tego
samego hosta co podczas rejestracji/logowania.

Wariant wymusza debug i lokalny serwer Django ze statykami, zeruje konfigurację
R2/Stripe i nie wymaga Node.js na hoście. Uruchamiaj tylko wskazane usługi
`db mail web`: worker i reaper z bazowego Compose nie są częścią tej próby.
Można sprawdzić rejestrację, potwierdzanie adresu, reset hasła i nawigację.
Nie jest to pełne E2E: bez R2 nie ma rzeczywistego uploadu i analizy,
a raporty, trening i abonament wymagają osobnych danych/usług testowych.
Nie używaj prawdziwych danych ani haseł produkcyjnych.

Zatrzymanie bez usuwania bazy:

```sh
docker compose -p cs-map-trainer-ui -f compose.yml -f compose.ui.yml stop
```

`compose.upload-test.yml` jest dodatkowym, lokalnym rozszerzeniem do prób
backendu z emulatorem S3 Moto zamiast R2. Używa projektu
`cs-map-trainer-ui` i obrazu weba zbudowanego powyżej także dla workera/reapera.
Dodaj je jako trzeci plik `-f` i uruchom `storage`, `web`, `worker`,
`maintenance`. Przed pierwszym uploadem utwórz testowy bucket
`local-demo-inputs` przez API S3 emulatora i przygotuj konto z potwierdzonym e-mailem.
Backend używa `http://storage:5000` w sieci Compose, a podpisane adresy do uploadu
z przeglądarki używają `http://localhost:5001`. Port emulatora jest publikowany
wyłącznie na interfejsie loopback. Opcjonalne `R2_PUBLIC_ENDPOINT` zmienia adres
używany do podpisywania, bez zmiany endpointu backendu; adres musi być osiągalny
z przeglądarki i nie wolno podmieniać hosta w już podpisanym URL.
Przed uploadem skonfiguruj CORS dla adresu strony, np. poleceniem
`cs-map-trainer-web configure_r2 --origin http://localhost:8000` w kontenerze web.
Storage jest nietrwały: po odtworzeniu kontenera ponownie utwórz bucket i skonfiguruj CORS.
Moto nie potwierdza zabezpieczeń podpisów/CORS ani kontraktu prawdziwego R2.

### Wdrożenie z Caddy (Linux/VPS)

`compose.production.yml` rozszerza bazowy Compose o Caddy z automatycznym TLS.
Wymaga Docker Compose **2.24.4 lub nowszego** (obsługa `!reset`), docelowego
hosta Linux z zapasem zasobów opisanym wyżej i pojedynczej domeny wskazującej
DNS A/AAAA na serwer. Nie publikuj AAAA bez działającej łączności IPv6.
Udostępnij TCP 80/443 do Caddy; porty Gunicorna i PostgreSQL nie są publikowane.
Nie stawiaj dodatkowego proxy/CDN przed Caddy bez osobnego odbioru zaufania
do nagłówków i wydawania certyfikatów.

Przygotuj `.env` poza Git (uprawnienia `0600`, dostęp tylko administratora).
Oprócz danych bazy/R2/SMTP i **testowych** danych Stripe ustaw:

```dotenv
DJANGO_DEBUG=0
DJANGO_TRUST_PROXY=0
CADDY_DOMAIN=trainer.example.com
ACME_EMAIL=ops@example.com
DJANGO_ALLOWED_HOSTS=trainer.example.com
CSRF_TRUSTED_ORIGINS=https://trainer.example.com
PUBLIC_BASE_URL=https://trainer.example.com
```

Wpisz prawdziwą domenę i adres kontaktowy zamiast przykładów. `CADDY_DOMAIN`
to sam hostname, bez protokołu, portu, ścieżki, wildcarda ani listy domen.
Użyj losowego, silnego `DJANGO_SECRET_KEY` oraz hasła PostgreSQL.
Rozszerzenie produkcyjne wymusza `DEBUG=0`, host/origin i adres publiczny
na podstawie `CADDY_DOMAIN`. Włącza `DJANGO_TRUST_PROXY=1` **tylko dla weba**.
Po włączeniu tej opcji Django ufa `X-Forwarded-Proto`; nie wolno wystawiać
Gunicorna bezpośrednio. Caddy domyślnie zastępuje niezaufane nagłówki
`X-Forwarded-*` klienta, a konfiguracja nie dodaje zaufanych proxy.
Cookies pozostają secure, a HTTP przekierowuje do HTTPS.

Poniższe polecenia wykonuj z katalogu projektu. Zachowuj tę samą nazwę
projektu Compose i zestaw plików podczas każdej operacji:

```sh
docker compose -f compose.yml -f compose.production.yml config --quiet
docker compose -f compose.yml -f compose.production.yml build
docker compose -f compose.yml -f compose.production.yml up -d db
docker compose -f compose.yml -f compose.production.yml run --rm web \
  cs-map-trainer-web migrate --noinput
docker compose -f compose.yml -f compose.production.yml run --rm web \
  cs-map-trainer-web check --deploy
docker compose -f compose.yml -f compose.production.yml run --rm --no-deps proxy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose -f compose.yml -f compose.production.yml up -d web worker maintenance proxy
docker compose -f compose.yml -f compose.production.yml ps
curl --fail --head https://trainer.example.com/accounts/login/
curl --fail --head https://trainer.example.com/static/trainer/app.css
```

Kontrola `check --deploy` pozostawia jawne ostrzeżenia `security.W005` i
`security.W021`: nie włączamy automatycznie HSTS dla wszystkich subdomen
ani preload bez sprawdzenia całej domeny. HSTS dla bieżącego hosta jest
włączone. Inne ostrzeżenia/błędy wymagają wyjaśnienia przed udostępnieniem.
Nie używaj `curl -k` do odbioru publicznego TLS. Sprawdź również HTTP → HTTPS,
logowanie i CSRF, brak pętli przekierowań, CSS/JS oraz działanie po restarcie.
Samo `ps` nie potwierdza gotowości aplikacji ani działania parsera.

`Dockerfile.web` ma targety `web` i `proxy`. Oba otrzymują statyki z tego samego
etapu `collectstatic`; Caddy serwuje tylko publiczny `/static/` z obrazu,
bez katalogu wejść, raportów i listowania plików. Nie ma wolumenu statyków,
który zachowałby stare CSS/JS po przebudowaniu. Buduj i wdrażaj wszystkie
obrazy z tej samej wersji kodu. Wolumeny `database`, `scratch`, `caddy-data`
i `caddy-config` muszą przetrwać restart i aktualizację. Caddy przechowuje
w nich m.in. prywatne klucze certyfikatów; ogranicz dostęp do hosta/Dockera.
Worker i reaper używają UID/GID `10001:10001`; nowy wolumen `scratch`
otrzymuje właściciela z obrazu. Przy przeniesieniu wolumenu zweryfikuj
możliwość zapisu przez ten UID, nie stosuj `chmod 777`.
Nie usuwaj `.parser.lock` ani wolumenów podczas pracy.

Przed aktualizacją zabezpiecz bazę zgodnie z osobno odebraną procedurą backupu.
Zatrzymaj przyjmowanie ruchu i usługi używające bazy, zastosuj migracje,
potem uruchom nowe obrazy:

```sh
docker compose -f compose.yml -f compose.production.yml build
docker compose -f compose.yml -f compose.production.yml stop proxy web worker maintenance
docker compose -f compose.yml -f compose.production.yml run --rm web \
  cs-map-trainer-web migrate --noinput
docker compose -f compose.yml -f compose.production.yml run --rm web \
  cs-map-trainer-web check --deploy
docker compose -f compose.yml -f compose.production.yml up -d web worker maintenance proxy
```

To aktualizacja z przerwą, nie rolling deploy. Zatrzymanie workera może przerwać
analizę; wybierz okno bez aktywnego zadania, nie uruchamiaj automatycznie parsera
ponownie. Nie wykonuj `down --volumes` na wdrożeniu. Nie cofaj samego obrazu
po nieodwracalnej migracji bez sprawdzenia zgodności schematu.
Ponów odbiór HTTP/statyków, sprawdź logi i działanie reapera.
Polityka `unless-stopped` obejmuje wszystkie usługi produkcyjne;
po ręcznym `stop` należy ponownie wykonać `up -d`.

#### Okresowe uzgadnianie Stripe

Szablony `deploy/cs-map-trainer-billing.service` i `.timer` uruchamiają
`reconcile_subscriptions` co 15 minut niezależnie od workera i reapera.
Dotyczą systemd na docelowym VPS, **nie aktywuj ich na komputerze lokalnym**.
Przed instalacją popraw `WorkingDirectory=/opt/cs-map-trainer` i ścieżkę
`/usr/bin/docker`, jeżeli instalacja używa innych lokalizacji.
Użyj tego samego projektu Compose co przy wdrożeniu; jeśli ustawiono `-p`
lub `--env-file`, dodaj te same argumenty do `ExecStart`.

```sh
sudo install -m 0644 deploy/cs-map-trainer-billing.service \
  deploy/cs-map-trainer-billing.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cs-map-trainer-billing.timer
sudo systemctl start cs-map-trainer-billing.service
sudo systemctl status cs-map-trainer-billing.service
sudo systemctl list-timers cs-map-trainer-billing.timer
sudo journalctl -u cs-map-trainer-billing.service --since today --no-pager
```

Niezerowy wynik polecenia lub timeout pozostawia usługę w stanie błędu
i zapis w journalu; timer ponawia kolejną próbę, nie uruchamia równoległych
instancji tej samej usługi. Przy błędzie sprawdź dostępność weba/bazy/Stripe,
konfigurację test/live i kody błędów, usuń przyczynę, uruchom usługę ręcznie
i sprawdź wynik. Limit pojedynczego uruchomienia to 10 minut; przy rosnącej
liczbie kont zweryfikuj czas wykonania. Nie wklejaj do logów sekretów,
payloadów webhooków ani wyników `compose config` zawierających środowisko.
Automatyczne alarmowanie o błędzie timera pozostaje częścią zadania monitoringu.
Przed planowaną aktualizacją zatrzymaj timer i poczekaj na zakończenie
aktywnej usługi; po odbiorze ponownie włącz timer.

Ten wariant wymaga jeszcze odbioru na docelowym VPS: prawdziwego certyfikatu
ACME, usług R2/SMTP/Stripe, awarii workera, backupu i monitoringu.
Lokalny certyfikat testowy nie potwierdza publicznego wdrożenia.

Bez Dockera: wyeksportuj zmienne środowiska (Django nie wczytuje automatycznie
`.env`), uruchom `uv run cs-map-trainer-web migrate`, a następnie w osobnych
procesach `runserver`, `qcluster` oraz `maintain_uploads --loop`.
R2, SMTP i PostgreSQL są nadal wymagane. Worker wymaga systemu POSIX;
produkcyjna izolacja i twardy limit kontenera dotyczą wariantu Linux/Docker.

### Operacje używane przez UI

| Operacja | Ścieżka / dane |
|---|---|
| Rejestracja/logowanie/weryfikacja | `/accounts/signup/`, `/accounts/login/`, odnośnik z e-maila |
| Historia i cookie CSRF | `GET /backend/history/`; `last_player_steam_id` (tekst lub pusty tekst) i prywatne `uploads` |
| Rezerwacja/upload | `POST /backend/uploads/`, JSON: UUID `request_id`, `size_bytes`, tekst `player_steam_id`, `has_upload_rights: true`; odpowiedź zawiera podpisany URL `PUT` |
| Ukończenie i kolejka | `POST /backend/uploads/<id>/complete/` |
| Status/wynik/komendy | `GET /backend/uploads/<id>/` |
| Odczyt wyboru | `GET /backend/uploads/<id>/selection/` |
| Zapis całego wyboru | `POST /backend/uploads/<id>/selection/`, JSON: `include` (lista ID lub `null`) i `reject` (lista ID) |
| Komendy pojedynczej sytuacji | `GET /backend/uploads/<id>/scenarios/<scenario_id>/export/`, domyślnie JSON z `console_line` i metadanymi; opcjonalnie `?format=cfg` |
| Opcjonalna paczka wybranych sytuacji | `GET /backend/uploads/<id>/pack/`, ZIP; opcjonalnie `?include_cfg=true` |
| Usunięcie historii | `DELETE /backend/uploads/<id>/` po zakończeniu zadania |
| Usunięcie konta | `POST /backend/account/delete/`, JSON `password` |

W żądaniach modyfikujących dane wysyłaj cookie sesji i `X-CSRFToken`.
`request_id` jest kluczem idempotencji dla konta; ponowienie z innym
rozmiarem lub SteamID jest błędem. SteamID przesłany przez klienta wybiera gracza,
nie właściciela raportu. Brak/błędny identyfikator daje 400
`invalid_player_steam_id`, bez rezerwacji i naliczenia limitu. Każdy upload
w odpowiedzi zawiera `player_steam_id` i `expires_at`; pole `steam_linked` usunięto.
Przeglądarka zachowuje rezerwację w sessionStorage osobno dla konta, razem z
identyfikatorem i sygnaturą pliku. Retry wymaga oryginalnego SteamID i pliku;
zmiana podpowiedzi konta nie zmienia trwającej ani zapisanej analizy.
Po wygaśnięciu zapamiętanej rezerwacji odświeżenie formularza zwalnia lokalną
blokadę pliku i SteamID; serwer nadal egzekwuje stan zadania i cleanup.
Jednoznaczny brak konfiguracji storage przy pierwszej próbie utworzenia rezerwacji
zwalnia lokalną blokadę. Timeout lub błąd po przyjęciu rezerwacji zachowuje jej
dane do bezpiecznego ponowienia.
Upload do R2 nie wymaga cookie sesji, tylko podpisanego URL. Błędy mają jawne
kody, m.in. `monthly_demo_limit`, `unsupported_or_invalid_demo`, `worker_lost`,
`linked_player_not_in_demo`, `processing_failed`; stan sprzątania jest
oddzielony od wyniku analizy.
Nawigacja przeglądarki z `Accept: text/html` otrzymuje czytelną stronę błędu;
żądania JSON zachowują kody błędów. Brak konfiguracji R2 daje jawne 503.

Formularze UI zapisują wybór przez `POST /uploads/<id>/selection/`, a oceny przez
`POST /uploads/<id>/scenarios/<scenario_id>/review/` (`rating`: `done`, `easy`,
`hard`, `irrelevant` lub `restore`). Wymagają sesji, potwierdzonego e-maila i CSRF.
Kandydaci i własność wynikają z raportu, nie z payloadu klienta.
Nie zmieniamy stanu przez GET.

### Wybór sytuacji i eksport z zapisanego raportu

Główna ścieżka treningu to pobranie `console_line` jednej sytuacji i jedno
wklejenie do konsoli CS2/Yprac po wejściu do właściwej mapy i trybu.
ZIP jest opcjonalnym pobraniem wielu sytuacji, nie wymaganiem uruchomienia
treningu. Backend nie instaluje plików w katalogu gry.

Wybór dotyczy kandydatów w `report.scenario_document.scenarios`, a nie nowych
sytuacji przesyłanych przez klienta. Odczyt `/selection/` zwraca `include`,
`reject`, `available_scenario_ids`, `selected_scenario_ids` i `compatibility`.
Domyślnie `include: null` oraz `reject: []` uwzględniają wszystkie sytuacje.
Przykładowe ciała POST (ID zastąp rzeczywistymi):

```json
{"include": ["ID_PIERWSZY"], "reject": ["ID_ODRZUCONY"]}
```

```json
{"include": null, "reject": []}
```

Drugi przykład przywraca domyślny wybór wszystkich sytuacji. Każdy POST zastępuje
cały wybór; oba pola są wymagane. Wybór jest zapamiętany przy raporcie,
widoczny także jako `selection` w szczegółach wyniku i usuwany razem z historią
lub kontem. `selection: null` w szczegółach oznacza brak zapisanego wyboru
i zastosowanie wartości domyślnych; `/selection/` zwraca je jawnie.
Kolejność eksportu wynika z raportu, nie z kolejności ID w żądaniu.

Nieznane lub powtórzone ID, konflikt wyboru z odrzuceniem i pusty wynik dają
`400 invalid_scenario_selection`. `include: []` nie oznacza „wszystkie”.
Nieprawidłowe typy, brakujące lub nadmiarowe pola dają
`400 invalid_selection_payload`; błąd nie zmienia poprzedniego wyboru.
Zapis wyboru nie sprawdza jeszcze obsługi sytuacji przez eksporter.
Nieobsługiwana wybrana sytuacja powoduje `422 scenario_not_exportable` dla
całego ZIP, bez cichego pomijania. Można ją jawnie odrzucić.

Pojedynczy eksport działa niezależnie od wyboru do ZIP. Domyślny JSON zawiera
`console_line`, `scenario_id`, `exporter_version`, `compatibility`, `map`,
`source`, `limitations`, `assumptions` i `session_changes`. `?format=json`
jest jawnym wariantem domyślnym, a `?format=cfg` pobiera tekstowy plik CFG.
Paczka używa zapisanego wyboru i istniejącego manifestu v1; bez parametru lub
z `?include_cfg=false` nie zawiera CFG. Inne wartości, powtórzone parametry
i nieznane parametry eksportu dają `400 invalid_export_parameters`.

Operacje wymagają sesji właściciela i potwierdzonego e-maila; zapis wymaga CSRF.
Cudze, usunięte i nieistniejące wyniki zwracają `404 not_found`, nieznany kandydat
w dostępnym raporcie — `404 scenario_not_found`. Wynik inny niż `ready` daje
`409 result_not_ready`, a raport bez kandydatów — `409 no_training_candidates`.
Uszkodzone zapisane dane dają `500 invalid_saved_report` lub
`500 invalid_saved_selection`, a nie pusty lub pozornie poprawny eksport.
Nowy poprawny POST może zastąpić uszkodzony wybór.

Raport i źródła są ponownie walidowane przed eksportem. Backend nie ufa komendom
przesłanym przez klienta ani zapisanej liście `scripts`: wyprowadza je z raportu.
Nie odczytuje dema, nie uruchamia parsera ani nie korzysta z R2 podczas tych
operacji. ZIP jest generowany na żądanie, bez zapisywania dodatkowej kopii.
Odpowiedzi są prywatne i mają `Cache-Control` zabraniający przechowywania.
Każdy eksport nadal ma `unverified_in_game`; wygenerowanie go nie potwierdza
działania w CS2/Yprac.

Przed wdrożeniem wykonaj próbę rzeczywistej rejestracji i SMTP oraz
opty-in test kontraktu R2 na prywatnym buckecie. Test tworzy wyłącznie własny
syntetyczny payload i usuwa jego obiekt; nie wysyła dem z repozytorium:

```sh
CS_MAP_TRAINER_R2_CONTRACT=1 uv run pytest tests/integration/test_r2_contract.py
```

Próba sprawdza odrzucenie innego rozmiaru, poprawny upload, zakończenie, odczyt,
unieważnienie URL i usunięcie. Bez tych prób nie oznaczamy integracji jako
potwierdzonej. Selekcja i autoryzowane eksporty backendu są zaimplementowane,
tak samo jak treningowe UI, deklarowane oceny użytkownika i powtórki.
Pakiet trenera/akademii jest poza zakresem; wskazanie gracza nie zwalnia
z obowiązku posiadania praw do przesłania i analizy dema.

### Stripe Billing — abonament za serwis

Zaimplementowano **7,99 USD/miesiąc, bez limitu liczby analiz na koncie
serwisu**. Free obejmuje 3 analizy na konto na miesiąc kalendarzowy UTC.
Nie ma opłat za pojedyncze demo, okresu próbnego ani automatycznego zwrotu.
Portal i checkout są hostowane przez Stripe; aplikacja nie przechowuje kart.

Zakup, portal zarządzania i odświeżenie stanu są na `/account/`.
Wymagają zweryfikowanego e-maila, sesji oraz POST z CSRF, bez Steam.
Cena i identyfikator klienta wynikają z konfiguracji serwera, nie z formularza.
Otwarty checkout jest ponownie używany; klucze idempotencji i blokada konta
chronią przed podwójnym utworzeniem sesji przy ponowieniu lub współbieżności.
Powrót `/account/billing/return/` **nie nadaje Pro**.

Pro wynika z opłaconego okresu pozycji faktury właściwej ceny i bieżącego stanu
subskrypcji pobranego z API Stripe. `invoice.paid` nie jest ślepo kopiowane
z payloadu webhooka. Starsze zdarzenie nie może przywrócić anulowanej subskrypcji.
Podpisy webhooków mają tolerancję 300 sekund; ID obsłużonych zdarzeń są unikalne.
Nieudane uzgodnienie zwraca 503 i nie zapisuje potwierdzenia, aby Stripe mógł ponowić.

Anulowanie przez portal działa **na koniec opłaconego okresu**. Nieudane odnowienie
nie przedłuża dostępu ani nie daje okresu tolerancji; po opłaconym terminie
wraca kwota Free. Rozpoczęte zadania nie są przerywane. Przed usunięciem konta
aplikacja wygasza otwarte checkouty i natychmiast anuluje subskrypcje, bez
proraty/automatycznego zwrotu. Awaria Stripe blokuje usunięcie, zamiast pozostawiać
czynny abonament bez konta. Dotyczy to także usunięcia użytkownika przez ORM/admin.

Po usunięciu konta pozostaje zamknięta referencja klienta Stripe bez właściciela
i bez dostępu Pro, służąca do anulowania ewentualnych opóźnionych subskrypcji.
Przechowujemy ID klienta/sesji/subskrypcji, stan, terminy i ID zdarzeń, nie pełne
payloady ani dane kart. Dane rozliczeniowe u Stripe podlegają zasadom operatora.
Ręczny zwrot w panelu Stripe sam w sobie nie jest anulowaniem subskrypcji;
odebranie dostępu wymaga jej anulowania. Aplikacja nie wykonuje refundacji.

#### Konfiguracja Stripe

1. W trybie testowym Stripe utwórz stałą cenę **799 centów USD**, cyklicznie
   co miesiąc (interval `month`, interval count `1`, licensed). Bez triala
   i kodów promocyjnych. Ustaw `STRIPE_PRICE_ID`; aplikacja weryfikuje parametry
   ceny zamiast przyjmować inną kwotę lub walutę.
2. Utwórz konfigurację Billing Portal: anulowanie włączone, tryb
   **at period end**; zmiany planu/ceny wyłączone. Włącz zarządzanie metodą
   płatności i historię faktur. Ustaw `STRIPE_PORTAL_CONFIGURATION_ID`.
3. Ustaw `STRIPE_SECRET_KEY` oraz stałe `PUBLIC_BASE_URL`, np. właściwą domenę
   HTTPS bez ścieżki. HTTP jest dopuszczone tylko przy lokalnym `DEBUG=1`.
   Adresów powrotu nie wyprowadzamy z nagłówka Host przeglądarki.
4. Skonfiguruj endpoint **`POST /billing/stripe/webhook/`** i jego sekret
   `STRIPE_WEBHOOK_SECRET`. API odczytu jest przypięte do `2025-06-30.basil`.
   Wybierz zdarzenia `checkout.session.completed`,
   `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`,
   `customer.subscription.created`, `customer.subscription.updated`,
   `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`,
   `invoice.voided`, `invoice.marked_uncollectible`.
5. Zastosuj migracje i przejdź w trybie testowym zakup, webhook, odnowienie,
   nieudaną płatność, anulowanie, wygaśnięcie oraz usunięcie konta.
   Dopiero po odbiorze skonfiguruj odpowiednie klucze/cenę/portal/webhook w live.
   Nie mieszaj identyfikatorów między środowiskami i nie zapisuj sekretów w Git.

Przy lokalnym odbiorze można przekazać webhooki przez Stripe CLI:
`stripe listen --forward-to http://localhost:8000/billing/stripe/webhook/`.
Sekret tego listenera ustaw lokalnie jako `STRIPE_WEBHOOK_SECRET`.

Po utracie/opóźnieniu webhooków użytkownik może użyć przycisku odświeżenia.
Niezależnie uruchamiaj okresowo (np. co 15 minut) oraz po awarii:

```sh
uv run cs-map-trainer-web reconcile_subscriptions
```

Polecenie uzgadnia również zamknięte referencje po usunięciu konta, by anulować
opóźnione subskrypcje. Błąd daje niezerowy kod wyjścia i wymaga reakcji/ponowienia.
Nie jest to retry parsowania. Operacyjne uruchamianie i monitoring tego polecenia
trzeba skonfigurować we wdrożeniu; nie blokuje ono sprzątania dem w reaperze.

Automatyczne testy korzystają z atrap Stripe. Rzeczywista sesja Checkout,
dostarczenie webhooków i pobranie opłaty wymagają powyższej konfiguracji;
nie zostały potwierdzone prawdziwymi poświadczeniami w tej sesji.

## Kolejne bramki

Procedurę testu integracji opisuje [protokół G1](docs/integration-validation.md).
Do końcowego odbioru trzeba zweryfikować interfejs Yprac Hub/Sandbox,
wymagania klienta i konkretne rewizje map Mirage oraz Dust2. Udokumentowane `place`, `savepos`, `loadpos`
i `swap` pomagają w ustawianiu sytuacji, ale nie potwierdzają importu dowolnych
XYZ i kątów z dema. Hub nie jest sam w sobie dowodem zgodności mapy.

Aktualna kolejność: **backend z eksporterem i paczkami → UI → końcowe próby
w CS2/Yprac**. Poprawność komend przyjmujemy na potrzeby implementacji;
G1 nie blokuje BE/UI, ale pozostaje wymagane przed deklarowaniem
zweryfikowanego treningu. Testy kodu i aplikacji są wykonywane na bieżąco.
Pozostają konfiguracja i odbiór prawdziwego Stripe, wdrożenie i techniczny benchmark VPS.
Nie ma etapu oceny przez trenera, pilota biznesowego ani walidacji SaaS.
Deklarowane oceny użytkownika i kolejka powtórek pozostają.
**Aktualne zadania, statusy i instrukcję rozpoczęcia
następnego wątku zawiera [plan projektu](docs/project-plan.md).**

## Dane testowe

Prywatne `.dem`, wyniki w `data/`, `results/`, `artifacts/` i sekrety są ignorowane
przez Git. Inne pochodne dema również należy trzymać wyłącznie w tych katalogach.
Nie dodawaj prawdziwych SteamID, pseudonimów ani surowych logów do fixture'ów.
Zgoda na przetwarzanie nie oznacza zgody na publikację próbki.

Przed benchmarkiem trzeba ustalić prawo do użycia każdego dema, cel, retencję
i usunięcie; przechowywać pliki prywatnie. Referencje muszą zawierać rundę,
tick początku wymiany, wspólny tick migawki i tick śmierci, obie pozycje i kąty,
broń, strony oraz ograniczenia oznaczone przez gracza lub trenera.
W repozytorium pozostają tylko syntetyczne lub osobno dopuszczone, zminimalizowane
próbki. Nie włączamy przetwarzania voice/chatu.
