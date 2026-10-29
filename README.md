# CS Map Trainer

Narzędzie do przygotowania treningu własnych pojedynków z CS2. Obecnie **CLI czyta
dema `.dem` z Mirage, wyświetla graczy i analizuje porównywalne wygrane oraz
przegrane pojedynki**. Wynikiem jest raport JSON z kandydatami do treningu
przegranych sytuacji i ich ustawieniem przestrzennym. Działa też
walidator kontraktu scenariuszy v1.

**Jest prototyp eksportu do konsoli/CFG i paczek ZIP, nie ma potwierdzonego
importu do gry.** Cel to
[Yprac Hub by Yesber, Workshop `3070715607`](https://steamcommunity.com/sharedfiles/filedetails/?id=3070715607),
Mirage/Sandbox. Eksporter zakłada osobno indeks gracza bota `2` i indeks jego
encji/pawn `2` po usunięciu botów. Nie wyszukuje indeksów dynamicznie.
Pozycje, kierunek oczu, broń, kolejność wykonania i zgodność mapy nadal wymagają
potwierdzenia w grze. Wyniki mają status `unverified_in_game`.
Nie planujemy własnego serwera/pluginu.

Istnieje też **minimalny backend Django/PostgreSQL/Django-Q2**, bez treningowego
UI: konta e-mail, powiązanie Steam, prywatny upload R2, jednorazowa analiza
i prywatna historia z zapamiętywaniem wyboru sytuacji, eksportem pojedynczej
linii komend i opcjonalnymi paczkami ZIP. Integracje z rzeczywistym R2, Steam i SMTP wymagają
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
do właściwego Mirage/Sandbox z klientem Yprac. Powtórzenie polega na ponownym
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

Walidacja eksportera dopuszcza tylko `de_mirage`, jawną listę broni palnych,
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
`pytest` używa osobnej konfiguracji `tests/web_settings.py`, atrap R2/Steam
i skrzynki e-mail w pamięci, bez sekretów wdrożeniowych.

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

## Minimalny backend

Stos: Django 5.2, PostgreSQL, Django-Q2 z brokerem ORM i jeden worker.
Nie ma osobnego frontendu/API ani treningowego UI; ścieżki `/backend/` są
prywatnymi operacjami monolitu z sesją Django i CSRF. Obraz CLI pozostaje osobny.

**Polityka:** publiczna rejestracja e-mail/hasło i potwierdzenie adresu;
przed uploadem obowiązkowe Steam OpenID. Jeden SteamID64 jest przypisany do
jednego konta aplikacji, bez samodzielnego odpinania. Analiza dotyczy tylko tego
gracza; jego obecność w demie jest sprawdzana. Limit to **3 przyjęte dema na
SteamID w ruchomych 7 dniach**, z rezerwacją przy rozpoczęciu uploadu i jednym
aktywnym zadaniem. 1 GiB jest wyłącznie technicznym limitem pojedynczego pliku.
Zły/nieobsługiwany plik zużywa przyjęcie, błąd infrastruktury zwalnia kwotę.
Niedokończona rezerwacja wygasa bez naliczenia.

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
7-dniowego okna, aby nowa rejestracja nie resetowała limitu. Odzyskanie powiązania
przez administratora nie może kasować tej ewidencji. Operacje usunięcia konta
wymagają hasła i zakończenia aktywnego zadania. Usunięcia należy uwzględnić
także w przyszłej procedurze odtwarzania backupu.

### Konfiguracja i uruchomienie

Skopiuj `.env.example` do `.env`, ustaw własne `DJANGO_SECRET_KEY` i `PGPASSWORD`
oraz dane prywatnego R2, SMTP i Steam Web API. Klucz Steam jest potrzebny
providerowi allauth do pobrania profilu po weryfikacji OpenID; w bazie z tego
profilu zachowywany jest jedynie SteamID. Sekretów nie dodawaj do Git.
Callback ogranicza dane przed lookup/zapisem allauth, również przy ponownym
lub odrzuconym połączeniu Steam. Migracja `0002_minimize_steam_profiles`
usuwa nadmiarowe pola ze starszych zapisanych profili; wdrożenie wymaga
uruchomienia `cs-map-trainer-web migrate`. Migracja `0003_training_selection`
dodaje zapis wyboru przy wyniku; istniejące raporty domyślnie obejmują wszystkie
sytuacje i nie są przepisywane.
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
Nie usuwać pliku blokady podczas pracy. Linux kończy parser sygnałem
`SIGKILL` po śmierci rodzica, także podczas wykonania kodu natywnego;
pozostałe systemy POSIX używają watchdogu. Odziedziczona blokada pozostaje
ochroną wyłączności niezależnie od szybkości reakcji watchdogu i blokady PostgreSQL.
To ochronne ustawienia startowe, **nie potwierdzony sizing VPS**. Potrzebny jest
także zapas RAM dla weba/bazy i miejsce na jedno demo oraz osierocone wejścia.
Compose nie jest jeszcze kompletnym wdrożeniem TLS/backup/monitoring.

Bez Dockera: wyeksportuj zmienne środowiska (Django nie wczytuje automatycznie
`.env`), uruchom `uv run cs-map-trainer-web migrate`, a następnie w osobnych
procesach `runserver`, `qcluster` oraz `maintain_uploads --loop`.
R2, SMTP i PostgreSQL są nadal wymagane. Worker wymaga systemu POSIX;
produkcyjna izolacja i twardy limit kontenera dotyczą wariantu Linux/Docker.

### Operacje do podłączenia UI

| Operacja | Ścieżka / dane |
|---|---|
| Rejestracja/logowanie/weryfikacja | `/accounts/signup/`, `/accounts/login/`, odnośnik z e-maila |
| Powiązanie Steam | `POST /accounts/steam/login/`, formularz `process=connect`, CSRF |
| Historia i cookie CSRF | `GET /backend/history/` |
| Rezerwacja/upload | `POST /backend/uploads/`, JSON: UUID `request_id`, `size_bytes`, `has_upload_rights: true`; odpowiedź zawiera podpisany URL `PUT` |
| Ukończenie i kolejka | `POST /backend/uploads/<id>/complete/` |
| Status/wynik/komendy | `GET /backend/uploads/<id>/` |
| Odczyt wyboru | `GET /backend/uploads/<id>/selection/` |
| Zapis całego wyboru | `POST /backend/uploads/<id>/selection/`, JSON: `include` (lista ID lub `null`) i `reject` (lista ID) |
| Komendy pojedynczej sytuacji | `GET /backend/uploads/<id>/scenarios/<scenario_id>/export/`, domyślnie JSON z `console_line` i metadanymi; opcjonalnie `?format=cfg` |
| Opcjonalna paczka wybranych sytuacji | `GET /backend/uploads/<id>/pack/`, ZIP; opcjonalnie `?include_cfg=true` |
| Usunięcie historii | `DELETE /backend/uploads/<id>/` po zakończeniu zadania |
| Usunięcie konta | `POST /backend/account/delete/`, JSON `password` |

W żądaniach modyfikujących dane wysyłaj cookie sesji i `X-CSRFToken`.
`request_id` jest kluczem idempotencji dla jednego SteamID; ponowienie z innym
rozmiarem jest błędem. SteamID przesłany przez klienta nie wybiera gracza.
Upload do R2 nie wymaga cookie sesji, tylko podpisanego URL. Błędy mają jawne
kody, m.in. `weekly_demo_limit`, `unsupported_or_invalid_demo`, `worker_lost`,
`linked_player_not_in_demo`, `processing_failed`; stan sprzątania jest
oddzielony od wyniku analizy.

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

Przed wdrożeniem wykonaj próbę rzeczywistej rejestracji, SMTP i Steam oraz
opty-in test kontraktu R2 na prywatnym buckecie. Test tworzy wyłącznie własny
syntetyczny payload i usuwa jego obiekt; nie wysyła dem z repozytorium:

```sh
CS_MAP_TRAINER_R2_CONTRACT=1 uv run pytest tests/integration/test_r2_contract.py
```

Próba sprawdza odrzucenie innego rozmiaru, poprawny upload, zakończenie, odczyt,
unieważnienie URL i usunięcie. Bez tych prób nie oznaczamy integracji jako
potwierdzonej. Selekcja i autoryzowane eksporty backendu są zaimplementowane,
ale treningowe UI pozostaje kolejnym etapem. Pakiet trenera/akademii
z analizą innych zawodników wymaga osobnego uprawnienia
i polityki kwot, nie jest teraz dostępnym obejściem SteamID.

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
