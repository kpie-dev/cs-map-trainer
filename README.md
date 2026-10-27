# CS Map Trainer

Narzędzie do przygotowania treningu własnych pojedynków z CS2. Obecnie **CLI czyta
dema `.dem` z Mirage, wyświetla graczy i analizuje porównywalne wygrane oraz
przegrane pojedynki**. Wynikiem jest raport JSON z kandydatami do treningu
przegranych sytuacji i ich ustawieniem przestrzennym. Działa też
walidator kontraktu scenariuszy v1.

**Nie ma jeszcze eksportu do konsoli/CFG ani importu do gry.** Planowany config
ma działać z [Yprac Hub by Yesber, Workshop `3070715607`](https://steamcommunity.com/sharedfiles/filedetails/?id=3070715607),
z preferencją kopiowania komend do konsoli. Istniejący kod nie integruje się
jeszcze z Yprac. Automatyczne ustawienie pozycji, kierunku patrzenia i broni
obu stron oraz zgodność właściwej mapy Mirage wymagają potwierdzenia w grze.
Nie planujemy własnego serwera/pluginu.

## Uruchomienie

Wymagany [uv](https://docs.astral.sh/uv/) i Python 3.11 lub nowszy.
`uv` może pobrać zgodny interpreter.

```sh
uv sync --locked
uv run cs-map-trainer validate-scenarios tests/fixtures/synthetic-scenarios.json
uv run cs-map-trainer schema
```

### Własne demo

Obsługiwane są nieskompresowane dema CS2 `.dem`, do 1 GiB, z mapy `de_mirage`.
Pliki CS:GO, archiwa i pozostałe mapy są jawnie odrzucane.

```sh
mkdir -p data results
# Umieść swoje demo w data/match.dem.
uv run cs-map-trainer players data/match.dem
uv run cs-map-trainer analyze data/match.dem \
  --steam-id 76561198000000001 \
  --output results/report.json
```

SteamID w przykładzie jest syntetyczny: zastąp go identyfikatorem z polecenia
`players`. Skład może zawierać obie strony i zmiany drużyn; pokazywana strona
gracza jest ostatnią zaobserwowaną, a analiza używa stron z chwili pojedynku.
Boty bez SteamID nie są oferowane do wyboru.

Bez `--output` JSON trafia na stdout, a diagnostyka na stderr. `--output` wymaga
istniejącego katalogu i **nie nadpisuje istniejącego pliku**.

Raport analizy ma teraz **`analysis_version: 2`**. Kontrakt dokumentu scenariuszy
pozostaje w wersji `schema_version: 1`; to dwa różne formaty. Nowa wersja raportu
rozszerza statystyki o wygrane i zmienia `groups[].observations` z liczby samych
porażek na liczbę porównywalnych wygranych i porażek łącznie.

Raport zawiera:

- `status`: `candidates_ready` albo `no_eligible_duels`;
- `scenario_document`: dokument v1 ze scenariuszami lub `null`, gdy brak kandydatów;
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
Wersja reguł tej analizy to `damage-window-v3`; format raportu pozostaje v2,
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
Zakres parametrów konkretnej integracji sprawdzi dopiero potwierdzony eksporter.

## Rozwój

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build
```

Awpy 3.1.1 jest przypiętym parserem, a `uv.lock` obejmuje jego zależności.
Domyślne testy nie pobierają dem. Test integracyjny można uruchomić na lokalnym,
dopuszczonym do przetwarzania demie Mirage zawierającym kwalifikujące się starcia:

```sh
CS_MAP_TRAINER_DEMO=data/match.dem uv run pytest tests/integration
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

## Kolejne bramki

Procedurę testu integracji opisuje [protokół G1](docs/integration-validation.md).
Do końcowego odbioru trzeba zweryfikować interfejs Yprac Hub/Sandbox,
wymagania klienta i konkretną mapę Mirage. Udokumentowane `place`, `savepos`, `loadpos`
i `swap` pomagają w ustawianiu sytuacji, ale nie potwierdzają importu dowolnych
XYZ i kątów z dema. Hub nie jest sam w sobie dowodem zgodności mapy.

Aktualna kolejność: **backend z eksporterem i paczkami → UI → końcowe próby
w CS2/Yprac**. Poprawność komend przyjmujemy na potrzeby implementacji;
G1 nie blokuje BE/UI, ale pozostaje wymagane przed deklarowaniem
zweryfikowanego treningu. Testy kodu i aplikacji są wykonywane na bieżąco.
Płatny pilot i decyzja o skalowaniu następują po końcowym odbiorze.
Równolegle pozostają ręczne referencje, ocena trenera i benchmark VPS.
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
