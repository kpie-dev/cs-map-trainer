# Plan wykonawczy i todos do kontynuacji w nowej sesji

## Aktualizacja: pakiet Trener i cennik

Bieżący zakres i instrukcje wdrożenia opisuje README: Pro 4,99 USD/mies.,
Trener 19,99 USD/mies., jeden zespół do 5 graczy, raporty i trening per zawodnik.
Przed wdrożeniem należy przejść odbiór obu cen i harmonogramów w Stripe test mode
oraz migracje wyników przy zatrzymanym intake i opróżnionej kolejce.
Wpisy o 7,99 USD poniżej są historyczne i nie określają nowej konfiguracji.

## Aktualizacja: uproszczony przepływ i treningi grupowe

**Zaimplementowane i odebrane lokalnie:** upload → aktualny etap → wybór grup →
ZIP z CFG jednym kliknięciem lub trening z nawigacją grup/członków.
Loader pokazuje jeden etap i spinner; polling co 2,5 s, deadline 10 minut,
retry widoczne dopiero po błędzie/przerwie. Nie wracać do listy wszystkich etapów.

Jeden checkbox obejmuje **wszystkich członków grupy**, nie reprezentatywny
setup. Grupowanie jest przestrzenne, z kontrolą kątów, stron, klas broni
i ograniczeń; szczegółowa reguła w README i `training_groups.py`.
Priorytet treningu: rifle/sniper vs pistol/SMG, następnie pełne bronie obu,
inne/nieznane zestawy i własny pistol/SMG. To preferencja oparta na broni,
nie odczyt pieniędzy/pancerza ani zmiana statystyk analizy.
Uczestnicy mają wspólny zapis `CT / awp / lokacja → T / tec9 / lokacja`.
ZIP zachowuje wszystkie wybrane CFG/TXT i dodaje `training-groups.json`.
Częściowe wybory legacy są jawne i nie są samoczynnie rozszerzane.

Oceny i terminy **usunięto z aktywnego UI**; historyczne `PracticeReview`
i zgodność operacji legacy pozostają. Biblioteka pokazuje grupy zgodnie
z wyborem, niezależnie od ocen. Duży panel ograniczeń zastąpiły zamknięte
szczegóły techniczne; krytyczne ostrzeżenia są nadal widoczne.
Starsze opisy ocen/powtórek w zapisach wykonanych iteracji są historią,
nie zadaniem do przywrócenia funkcji.

Ostatni odbiór: 572 testy ukierunkowane na zmienione obszary, lint/format,
brak migracji oraz Playwright dla Mirage/Dust2 przy 1440 × 900 i 390 × 900.
Wiersze 140 px desktop i 135–158 px mobile; kopiowanie w pierwszym widoku.
Przebudowano web/worker/maintenance i potwierdzono HTTP 200/statyki, bez
restartu db/storage/mail. Nie jest to dowód działania rzeczywistego R2 ani
CS2/Yprac. Pełny protokół: [odbiór UI](integration-validation.md#aktualny-odbiór-ścieżki-upload--wybór--trening).

## Aktualizacja: upload bez powiązania Steam

Obowiązuje konto e-mail/hasło z potwierdzonym adresem, bez Steam OpenID/API.
Wymagane SteamID64 wskazuje gracza każdego dema; ostatnia przyjęta wartość
jest zapisana na koncie jako edytowalna podpowiedź, nie dowód tożsamości.
Pomoc przy polu używa instrukcji i lokalnych ilustracji, nie screenshotów.
Free, Pro, aktywne zadania i cleanup są przypisane do konta serwisu;
3 analizy/miesiąc UTC, Pro 7,99 USD/mies., bez zmian limitów technicznych.
Identyczne SteamID mogą wystąpić na różnych kontach bez dostępu do cudzych wyników.
Tworzenie nowych kont daje osobne limity Free; nie ma blokady SteamID.

Przed wdrożeniem zastosować wszystkie migracje, w tym nieodwracalną
`0007_account_upload_players`, przy zatrzymanym intake/workerach i po backupie.
Zachować istniejące raporty, oceny, zużycie kont i referencje Stripe.
Powtórzyć odbiór SMTP/R2/Stripe, formularza i instrukcji SteamID, retry,
izolacji kont i limitów po zmianie gracza. Starsze zapisy o Steam OpenID,
minimalizacji profili i limitach per SteamID poniżej są historyczne.

## Aktualny punkt kontynuacji — obsługa siedmiu map

Zakończone w kodzie i lokalnym odbiorze: parser/analiza, eksporter i paczki,
backend, UI z grupami treningowymi oraz Stripe Billing. Oceny/powtórki
pozostają wyłącznie jako zachowane dane i operacje historyczne.
**Free: 3 analizy na konto w miesiącu kalendarzowym UTC.
Pro: 7,99 USD/miesiąc bez limitu liczby analiz na koncie.**
Limity techniczne pozostają. Nie wracamy do limitu tygodniowego.

**Zakres zaimplementowany w aplikacji:** Cache, Dust2, Mirage, Inferno, Nuke,
Ancient i Anubis. Wspólny katalog obejmuje parser, analizę, CLI, eksperymentalny
eksport, paczki i UI. Testy syntetyczne obejmują siedem map; rzeczywiste dema
Cache/Inferno/Nuke/Ancient/Anubis nadal wymagają osobnego odbioru parsera/workera.
Zadania `support-tournament-maps` i `adapt-multi-map-training` są zakończone w kodzie.
`verify-tournament-maps` pozostaje częściowe do odbioru rzeczywistych dem pięciu
nowych map i pełnego uploadu. Ten odbiór oraz przygotowanie docelowego środowiska
poprzedzają końcowe aplikacyjne E2E. Każda mapa wymaga osobnego odbioru Yprac.

Odbiór rozszerzenia: **3141 testów zaliczonych, 2 opt-in pominięte** na osobnym
PostgreSQL; rzeczywiste lokalne demo Dust2 zaliczone osobno (parser i proces
potomny workera). Lint, format, build, Django check i brak nowych migracji potwierdzone.
Playwright: siedem syntetycznych raportów, 34 widoki przy 1440 × 900 i 390 × 900,
wybór grup, trening dwóch członków oraz ZIP z CFG/TXT i właściwą mapą/integracją;
bez poziomego przepełnienia i wyjątków JavaScript. Użyto osobnego serwera i bazy,
bez zmian danych działającego środowiska. Nie jest to odbiór rzeczywistych dem
pięciu nowych map, zewnętrznych usług ani CS2/Yprac.

Review bieżących zmian zakończone bez istotnych błędów ani regresji wymagających
poprawek. Zakres: katalog map, analiza/eksport, manifesty, grupowanie, wybór
scenariuszy i przepływ raport → trening. Nie zamyka to odbioru rzeczywistych dem
ani bramek integracji w grze.

Następne zadanie: **docelowy odbiór `prepare-deployment`**. Konfiguracja Caddy,
HTTPS/proxy, statyków i harmonogramu Stripe jest już przygotowana; opis
lokalnego odbioru znajduje się poniżej. Na VPS zastosować wszystkie migracje
do `0007_account_upload_players`, odebrać publiczny TLS, a następnie
rzeczywiste usługi oraz workera. Stripe wymaga konfiguracji kluczy,
ceny, portalu, webhooka i okresowego `reconcile_subscriptions`, nie ponownej
implementacji modułu. Potem techniczne E2E i końcowe próby CS2/Yprac.
Bez ocen trenerów, pilota biznesowego ani walidacji SaaS.

## Decyzja obowiązująca

**Backend → UI → końcowe próby w CS2/Yprac.**

Przyjmujemy poprawność komend jako założenie implementacyjne. Nie czekamy
z eksporterem, backendem ani UI na próby w grze, odpowiedź autora Yprac
ani biznesową walidację. Testy kodu i aplikacji wykonujemy na bieżąco.
Nie oznaczamy integracji jako sprawdzonej, dopóki nie przejdzie końcowych prób.

Ten plik jest skróconym planem wykonawczym. Pełny zakres, decyzje i ryzyka
opisuje [plan projektu](project-plan.md), a końcowe próby
[protokół integracji](integration-validation.md).
Przy zmianie zakresu lub statusów aktualizować oba plany. Nie polegać na
historii rozmowy ani sesyjnej bazie todos.

## Stan kodu — nie implementować od nowa

Etap Dust2 jest zaimplementowany. Regresja obu map: **875 testów zaliczonych,
2 opt-in pominięte**; osobno zaliczono test rzeczywistego, uprawnionego dema
Dust2 (build `10924`), także przez proces potomny workera.
Lint, format, build sdist/wheel, Django checks i kontrola migracji przeszły.
Próba rzeczywistego raportu wykryła i usunęła błąd walidacji krotek komórek:
raport z procesu potomnego jest teraz walidowany w trybie JSON, nadal ściśle.
Nie oznacza to odbioru prawdziwego R2/Steam ani CS2/Yprac.

Odbiór Playwright Mirage/Dust2 również zakończony: na aktualnym lokalnym
obrazie Compose sprawdzono 8 stron przy 1280 i 390 px, bez poziomego
przepełnienia i wyjątków JavaScript. Potwierdzono mapy, nawigację sytuacji,
trwały wybór/odrzucenie, pobrania i zawartość CFG/ZIP oraz ocenę „Trudne”
w nadchodzących powtórkach. Dane były syntetyczne i zostały usunięte.
Na lokalnym HTTP działa ręczne zaznaczenie zamiast niedostępnego schowka;
kopiowanie przez API schowka pozostaje do próby na docelowym HTTPS.
Pełny upload dema przez przeglądarkę oraz prawdziwe usługi nadal do odbioru.
Szczegóły: [etap Dust2](integration-validation.md#etap-dust2--osobny-odbiór).

- Python 3.11+, `uv`, Awpy 3.1.1, kontrakt scenariuszy v1 i raport analizy v2.
- CLI: `players`, `analyze`, `benchmark`, `validate-scenarios`, `schema`,
  `export-scenario`, `build-pack`.
- Parser nieskompresowanych dem CS2 siedmiu map z `maps.py` do 1 GiB, zbiorcze migawki
  sprzed obrażeń, wykluczenia i grupowanie porównywalnych wygranych/przegranych.
- Reguły `damage-window-v3`: zachowują dostępne kąty przeciwnika, a brakujący
  pitch/yaw wyliczają ku pozycji gracza, z oznaczeniem
  `opponent_aim_inferred_toward_player`. Kąty gracza nie są zgadywane.
  Grupy przybliżone i kompletne są rozdzielone.
- Benchmark w osobnych procesach, Docker CLI, testy i workflow CI.
- Jest eksporter `yprac-sandbox-prototype-v1` i wybór/odrzucanie scenariuszy
  oraz paczki ZIP z manifestem, instrukcją, osobnymi liniami komend i opcjonalnym
  CFG. Wspólne moduły dla CLI i backendu: `exporting.py`, `packs.py`.
  Jest aplikacja w `src/cs_map_trainer/web/` z responsywnym UI Tactical HUD,
  zapamiętanym wyborem sytuacji, prywatnym eksportem komend/CFG i opcjonalnym ZIP.
  Nie wykonano próby Yprac; eksport pozostaje
  `unverified_in_game`. Biblioteka grup treningowych zastąpiła kolejkę ocen/powtórek.

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

## Zakończony backend treningowy

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
- Następnie zrealizowano `build-training-ui` i `wire-personal-training`:
  szablony Django korzystają z istniejących operacji, bez kolejnej warstwy API
  i bez przepisywania backendu.
- W skonfigurowanym środowisku osobno odebrać R2/Steam/SMTP oraz kontener
  Linux, zastosować migracje `0002_minimize_steam_profiles` oraz
  `0003_training_selection` i sprawdzić awarię workera. Brak tego środowiska
  nie oznacza pozytywnego odbioru ani potrzeby przepisywania działającej logiki.

Kod backendu treningowego jest gotowy; G2 pozostaje otwarte do odbiorów zewnętrznych.
Kontener PostgreSQL użyty w testach nie potwierdza działania kontenera workera.
Pakiet trenera/akademii, płatności i próby CS2/Yprac nie były częścią iteracji UI.

### Zrealizowane: `build-training-ui` i `wire-personal-training`

1. Responsywne szablony Django i lokalne CSS/JS na podstawie `design/`:
   strona główna, allauth, konto/Steam, prywatna historia, status, raport i trening.
   Makiety są wzorcem wyglądu; nie przeniesiono fikcyjnych statystyk, radaru
   ani obietnic automatycznego pomiaru treningu.
2. Upload z potwierdzeniem uprawnień, rzeczywistym postępem PUT do R2,
   zachowaniem UUID rezerwacji i etapu przy ponowieniu; bez retry analizy.
   Ograniczony polling i jawne błędy transportu/statusu/konfiguracji.
3. Raport pokazuje próbę, ograniczenia i przybliżone kąty; brak kandydatów
   nie jest błędem, ale uszkodzony raport nie jest przedstawiany jako pusty sukces.
   Zapis wyboru/odrzuceń, jedna aktywna sytuacja, kopiowanie pełnej linii,
   fallback ręcznego kopiowania i opcjonalne ZIP/CFG.
4. `PracticeReview` i migracja `0004_practicereview`: trudne +1 dzień,
   wykonane +3 dni, łatwe +7 dni, nietrafne poza kolejką do przywrócenia.
   Jedna bieżąca deklaracja na sytuację, bez historii prób i telemetrii gry.
   Kolejka respektuje zapisany wybór ze wszystkich gotowych prywatnych raportów,
   ma filtry i stronicowanie. Usunięcie raportu/konta usuwa też oceny,
   również przy równoległym zapisie oceny.
5. Testy PostgreSQL i przeglądarkowy odbiór na syntetycznych danych obejmują
   dostęp, CSRF, błędy, terminy, wybór, schowek, surowy PUT i ponawianie UUID,
   a także układ mobilny, wznowienie po przeładowaniu strony i zatrzymanie/
   ręczne wznowienie odświeżania statusu. Usługi zewnętrzne są atrapami,
   nie odebraną integracją.
6. Odbiór lokalny: 187 testów backendu/UI na PostgreSQL 16; cała regresja
   481 zaliczonych, 2 pominięte (lokalne demo i prawdziwe R2).
   Lint/format, build sdist/wheel, Django checks, zastosowanie migracji
   i zgodność modeli przeszły. Potwierdzono szablony i CSS/JS w wheel,
   collectstatic oraz budowanie obrazu web Linux i jego checks/szablony/statyki.
   BuildKit przekroczył czas; obraz zbudowano lokalnym legacy builderem Dockera.
   To nie jest odbiór uruchomienia Compose, workera Linux ani prawdziwych usług.

Przed uruchomieniem na istniejącej bazie wykonać wszystkie migracje, w tym
`0005_billing_accounts`, oraz udostępnić `/static/` przez reverse proxy.
Dockerfile zbiera statyki w obrazie; Gunicorn ich nie serwuje.
Kolejny etap: operacyjna część `add-operations-and-billing` (TLS, backup/
odtworzenie, monitoring i limity), konfiguracja i rzeczywisty odbiór Stripe;
następnie odbiór aplikacji i próby CS2/Yprac. `build-subscriptions` ma kod
i lokalny odbiór na atrapach operatora, nie wymaga implementacji od nowa.

**Historyczny zakres tej iteracji:** aplikacja generuje trening z dema. Nie ma oceny przez
trenera, pilota biznesowego ani walidacji SaaS. Dodane wtedy oceny użytkownika
i powtórki usunięto później z UI; dane zachowano. Ówczesne ustalenia: **Free 3 analizy
na SteamID w miesiącu kalendarzowym UTC**, **Pro 7,99 USD/miesiąc bez limitu
liczby analiz własnego SteamID**. Zastępuje to wcześniejszy limit 3/7 dni.
Ograniczenia 1 GiB/pliku i jednego aktywnego zadania obowiązują również w Pro.

### Zrealizowane: `build-subscriptions`

- Stripe Checkout i Billing Portal na koncie, z walidacją ceny 799 centów USD
  za miesiąc i konfiguracji anulowania na koniec okresu, bez zmiany planu/ceny.
- Podpisane i idempotentne webhooki oraz uzgodnienie bieżącego stanu Stripe
  i opłaconego okresu z faktury. Starszy event/redirect nie nadaje dostępu.
- Pro wygasa po opłaconym okresie bez grace period. Nieudane odnowienie nie
  przerywa już rozpoczętych analiz. Free resetuje się pierwszego dnia miesiąca
  o 00:00 UTC; zmiana konta nie resetuje kwoty tego SteamID.
- Usunięcie konta najpierw wygasza checkouty i natychmiast anuluje abonament,
  bez automatycznego zwrotu. Awaria Stripe zatrzymuje usunięcie.
- `BillingAccount`, `BillingEvent`, migracja `0005_billing_accounts`, przycisk
  odświeżenia i polecenie `reconcile_subscriptions` do odzyskiwania po utracie
  webhooków, również dla zamkniętych referencji po usunięciu konta.
- Testy wykorzystują atrapy Stripe. Sekrety, cena i portal muszą być skonfigurowane
  w środowisku; wymagany odbiór rzeczywistego Stripe w test mode i potem live.
- Odbiór lokalny: 55 testów modułu płatności, łącznie 242 backendu/UI na PostgreSQL;
  cała regresja 536 zaliczonych, 2 pominięte (lokalne demo i prawdziwe R2).
  Migracje, Django checks, Ruff i build przeszły. Przeglądarkowa próba syntetyczna
  obejmuje checkout/portal, brak dostępu po samym redirect, nadanie Pro po webhooku,
  anulowanie, wygaśnięcie, ręczne uzgodnienie i widok mobilny. Nie wykonano
  prawdziwej płatności ani odbioru poświadczeń Stripe.

## Co jeszcze brakuje — wdrożenie i odbiory

### Dodatkowy odbiór negatywny workera Linux

Rzeczywisty upload dema Dust2 (408 650 218 B) do lokalnego emulatora S3 Moto
ujawnił błąd importu Awpy bez katalogu domowego numerycznego użytkownika.
Parser otrzymuje teraz `AWPY_DATA_DIR` wewnątrz katalogu uploadu.
Po poprawce HTTP upload → kolejka → worker → `unsupported` przeszedł;
potwierdzono brak ponownej analizy przy powtórzeniu ukończenia oraz usunięcie
obiektu i katalogu roboczego. Regresja backendu/UI: 248 zaliczonych testów.
To próba odrzucenia nieobsługiwanej mapy, nie udana analiza Mirage ani odbiór
prawdziwych R2/Steam; `verify-linux-worker` i G2 pozostają otwarte.

### Zrealizowane lokalnie: konfiguracja `prepare-deployment`

- Dodano `compose.production.yml` i Caddy z automatycznym TLS dla jednej domeny;
  tylko proxy publikuje porty. Lokalny Compose zachowuje loopback Gunicorna.
- Targety `web`/`proxy` w `Dockerfile.web` biorą statyki z tego samego etapu
  budowania, bez trwałego wolumenu starych CSS/JS. Naprawiono również
  whitelistę `.dockerignore`, aby obejmowała Dockerfile weba i konfigurację proxy.
- Django jawnie ufa `X-Forwarded-Proto` wyłącznie w produkcyjnym webie za Caddy;
  dodano ochronę ramek. Produkcyjny Compose wymusza `DEBUG=0`, host i origin
  domeny. README opisuje migracje, aktualizację, wolumeny i granice zaufania.
- Szablony systemd uruchamiają uzgodnienie Stripe co 15 minut, niezależnie
  od reapera, z błędem widocznym w statusie/journalu. Nie instalowano ich
  na obecnej maszynie; wymagają instalacji i odbioru na docelowym Linuxie.
- Zbudowano obrazy i uruchomiono izolowany Compose z PostgreSQL, wszystkimi
  migracjami, webem, workerem, reaperem i Caddy. HTTPS sprawdzono certyfikatem
  lokalnego CA, bez wyłączania weryfikacji TLS. Potwierdzono logowanie/CSRF,
  secure cookies, prywatną historię, HTTP → HTTPS, odporność na podstawione
  nagłówki, zgodne hashe CSS/JS, 404 i brak publicznych portów weba/bazy.
  Próby powtórzono po restarcie; podmiana obrazu proxy podała nowy CSS.
- R2 było jawną atrapą pustego bucketa do cyklu reapera; bez konfiguracji
  usługi reaper poprawnie zgłaszał błąd zamiast udawać sukces.
  Nie potwierdzono prawdziwego R2 ani analizy dema.
- Odbiór kodu: 20 ukierunkowanych testów ustawień, logowania, dostępu i CSRF
  na PostgreSQL; Ruff i walidacja Compose/Caddy przeszły. Django deploy check
  pozostawia jawne W005/W021: bez zgody na HSTS całych subdomen i preload.
  Nie powtarzano całej regresji ani nie wydawano publicznego certyfikatu.

**`prepare-deployment` nie jest zamknięte:** pozostaje docelowy VPS/domena,
publiczny ACME, instalacja timera i odbiór po restarcie hosta.

**Rdzeń aplikacji i abonament są zaimplementowane, ale nie ma jeszcze odebranego
wdrożenia produkcyjnego ani potwierdzonego treningu w grze.** Nie rozpoczynać ponownie
backendu, UI, treningów grupowych ani Stripe Billing. Nie przywracać ocen/powtórek.
Poniższe pozycje są pozostałą pracą, nie deklaracją
wykonania. Nie uruchomiono ich podczas aktualizacji planu.

| Zadanie wykonawcze | Rodzaj braków | Zakres i dowód zakończenia |
|---|---|---|
| `prepare-deployment` | Konfiguracja w kodzie i lokalny odbiór gotowe; VPS do odbioru | Caddy/TLS/statyki, hosty/originy/cookies, migracje i Compose sprawdzone lokalnie z testowym CA i atrapą R2. Na VPS: sekrety poza Git, publiczny certyfikat, instalacja timera Stripe i działanie po restarcie hosta |
| `verify-live-services` | Konfiguracja i próby rzeczywistych usług | SMTP: rejestracja, potwierdzenie i reset hasła; Steam: poprawne powiązanie i odmowa nieprawidłowego/duplikowanego; prywatne R2: CORS, limit rozmiaru, ukończenie, wygaśnięcie URL i usunięcie. Odbiór: zapisane wyniki prób bez sekretów; atrapy nie wystarczą |
| `verify-linux-worker` | Odbiór istniejącego kodu w runtime | Pełny Compose i uprawnione demo, jeden parser globalnie, limity, utrata workera/timeout/restart, reaper i usuwanie obu kopii. Odbiór: brak drugiej analizy i osieroconych wejść po przećwiczonych awariach |
| `implement-backup-restore` | Implementacja procedury i próba | Kopia PostgreSQL poza VPS, retencja, odtworzenie do osobnego środowiska oraz respektowanie usunięć kont/raportów. Odbiór: działający odtworzony system i udokumentowana procedura, nie sam plik backupu |
| `implement-monitoring` | Implementacja i konfiguracja | Healthchecki, alerty błędów i wieku kolejki, kontrola workera/reapera, RAM/dysku, minimalne logi bez danych dem i sekretów. Odbiór: celowo wywołana awaria jest wykryta i ma instrukcję reakcji |
| `benchmark-target-vps` | Pomiar i dostrojenie istniejących limitów | Uprawnione dema na docelowej klasie VPS: czas, CPU, RSS, dysk i koszt analizy. Odbiór: limity dobrane z zapasem dla weba/bazy; obecne 4/5 GiB i 2 CPU nie są potwierdzonym sizingiem |
| `verify-live-stripe` | Konfiguracja i próby rzeczywistego operatora | Moduł Stripe jest zaimplementowany. Skonfigurować cenę 7,99 USD/mies., klucze, portal i webhook; przejść rzeczywisty checkout, odnowienie, brak płatności, anulowanie, wygaszenie i usunięcie. Odbiór test mode przed live; atrapy nie wystarczą |
| `verify-application-e2e` | Odbiór aplikacji w skonfigurowanym środowisku | Prawdziwy upload → worker → raport → wybór grup → ZIP/CFG → trening członków; zakup/odnowienie/utrata abonamentu i kwoty, błędy, uprawnienia, usuwanie i odtworzenie. Bez ocen/harmonogramu ani pilota biznesowego |
| `prove-scenario-import` | Najważniejsza niewiadoma integracji | Końcowa próba jednej, następnie 10 sytuacji na każdej z siedmiu map w CS2/Yprac: właściwa mapa/Sandbox, indeksy i gotowość bota, XYZ, oczy, broń, powtórzenie i jedno wklejenie. Odbiór według `integration-validation.md`; samo wygenerowanie komend nie wystarcza |

`prepare-deployment`, backup/odtworzenie, monitoring i dobór limitów rozwijają
pozostałą część `add-operations-and-billing`; moduł `build-subscriptions` jest w kodzie.
**Abonament miesięczny jest zatwierdzonym zakresem.**
Odbiór usług i workera domyka zaległy zakres G2.
Odbiór pełnego przepływu w docelowym środowisku uzupełnia lokalny odbiór G3.
G1 pozostaje otwarte do pomiarów w grze, a G4 wymaga wszystkich tych dowodów.

Zależności wykonawcze: najpierw przygotowanie środowiska; następnie niezależnie
odbiór usług, Stripe, backup, monitoring i pomiary VPS. Odbiór workera na
prawdziwym wejściu wymaga usług. Aplikacyjne E2E wymaga zakończenia tych prac
i odbioru modułu opłat; próby CS2/Yprac następują po E2E.
Nie wprowadzać ukrytej kwoty liczby analiz Pro. Pomiary i monitoring muszą
uwzględniać tę świadomie przyjętą politykę.

**Najbliższy krok:** docelowy odbiór `prepare-deployment` według README,
bez ponownej implementacji Caddy/statyków. Potrzebne będą docelowy serwer/domena,
konfiguracja prywatnego R2, Steam i SMTP oraz uprawnione demo; sekrety przekazywać
wyłącznie przez konfigurację środowiska, nie przez plany ani repozytorium.
Do G1 potrzebny jest również tester z dostępem do CS2 i właściwego Yprac.

## Polityki minimalnego backendu

- Jeden prywatny R2 Standard, upload bezpośrednio do bucketa; lokalna kopia
  tylko na czas pracy izolowanego parsera. Po pierwszej próbie usuwamy obie
  kopie, także po błędzie; nowa analiza wymaga nowego uploadu. Automatyczny
  retry dotyczy tylko usuwania i dostarczenia komunikatu, nie parsowania.
- Publiczna rejestracja e-mail/hasło z potwierdzeniem adresu oraz obowiązkowe,
  unikalne powiązanie Steam OpenID przed uploadem. Analizujemy tylko tego gracza.
- Free: 3 przyjęte dema na SteamID w miesiącu kalendarzowym UTC.
  Pro: 7,99 USD/miesiąc bez limitu liczby analiz własnego SteamID.
  W obu planach jedno aktywne zadanie na SteamID i jeden worker globalnie.
  1 GiB to limit techniczny pliku, nie kwota.
  Błędy wejścia zużywają przyjęcie; błędy infrastruktury zwalniają kwotę.
- Historia raportów, scenariuszy i komend zostaje do usunięcia przez użytkownika
  lub usunięcia konta. Ewidencja kwoty po usunięciu konta wygasa z końcem miesiąca UTC;
  nowe konto nie resetuje kwoty ani aktywnego powiązania Steam.
- Porzucone uploady wygasają po 24 h. Reaper obsługuje utracone zadania,
  osierocone obiekty i multipart uploady. Szczegóły uruchomienia są w README.
- Pakiet trenera/akademii i zewnętrzne oceny są poza zakresem. Abonament
  znosi limit liczby analiz własnego powiązanego SteamID, nie pozwala
  analizować dowolnych zawodników ani resetować kwoty po zmianie konta.

## Wymagania, których trzeba pilnować

- Jedna integracja: Yprac Hub `3070715607`, docelowo Sandbox dla Cache,
  Dust2, Mirage, Inferno, Nuke, Ancient i Anubis. Lista jest jawna, niezależna
  od aktualnej rotacji Active Duty. Kod obsługuje wszystkie siedem map.
  Dostępność i zgodność każdej mapy w Yprac
  wymagają osobnego dowodu.
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
  frontendu/API, Redis/Celery ani LLM. Moduł miesięcznych opłat jest zatwierdzony.

## Todos i zależności

Status „planowane” nie oznacza implementacji. Zadania bez wspólnej zależności
mogą postępować niezależnie; UI zaczyna się po gotowym backendzie.

| ID | Status | Zakres i warunek odbioru | Zależności |
|---|---|---|---|
| `bootstrap-cli` | Gotowe | Istniejący parser, analiza, kontrakt, CLI, benchmark, Docker i testy | Brak |
| `build-training-exporter` | Gotowy prototyp; bez odbioru w grze | Bot, XYZ, hipoteza orientacji przez `point_teleport`, broń, jedna linia, walidacja i testy; indeksy/gotowość/oczy/synchronizacja do G1 | `bootstrap-cli` |
| `assemble-training-packs` | Gotowe — CLI/logika BE | Wybór/odrzucanie, ZIP, wersjonowany manifest, instrukcja, TXT/CFG; raport v2 lub dokument v1, bez nadpisywania | `build-training-exporter` |
| `define-saas-policies` | Gotowe; kwota zaktualizowana | R2, e-mail + Steam, Free 3/miesiąc UTC, Pro 7,99 USD/mies. bez limitu liczby, brak retry analizy i usuwanie wejść po próbie | `bootstrap-cli` |
| `build-minimal-web` | Kod, poprawki i review gotowe; integracje zewnętrzne do odbioru | Django/PostgreSQL, prywatny intake R2, Q2, jednorazowy worker, historia i reaper; wymagane prawdziwe R2/Steam/SMTP, migracja profili i odbiór kontenera Linux/Compose | `define-saas-policies` |
| `complete-training-backend` | Kod i lokalny odbiór gotowe | Zapis wyboru, prywatny ZIP na żądanie i komendy/CFG z raportu, bez ponownej analizy; migracja `0003_training_selection`; zewnętrzny odbiór fundamentu G2 nadal otwarty | `build-minimal-web`, `assemble-training-packs` |
| `build-training-ui` | Kod i lokalny odbiór gotowe | Tactical HUD w szablonach Django: konta/Steam, upload/status, raport, wybór, kopiowanie i opcjonalne ZIP/CFG; usługi zewnętrzne do odbioru | `complete-training-backend` |
| `wire-personal-training` | Gotowe; UI uproszczone | Biblioteka grup według wyboru, bez ocen i harmonogramu; historyczne dane i operacje legacy zachowane | `build-training-ui` |
| `refine-group-training` | Kod i lokalny odbiór gotowe | Loader jednego etapu/2,5 s, grupy wszystkich członków, priorytet broni, wspólny opis lokacji, ZIP z CFG jednym POST i zamknięte szczegóły techniczne | `complete-training-backend`, `build-training-ui`, `wire-personal-training` |
| `support-tournament-maps` | Kod gotowy: siedem map | Wspólny katalog i pipeline Cache/Dust2/Mirage/Inferno/Nuke/Ancient/Anubis, zachowane limity, reguły i kontrakty; inne mapy odrzucane | `bootstrap-cli` |
| `adapt-multi-map-training` | Kod gotowy: siedem map | Rzeczywiste mapy w historii, raportach, bibliotece i instrukcjach, eksport siedmiu map i paczki mieszane; zgodność starszych raportów i manifestów | `support-tournament-maps`, `complete-training-backend`, `wire-personal-training` |
| `verify-tournament-maps` | Częściowe | Regresja syntetyczna siedmiu map; historyczne próby Mirage/Dust2 nie zastępują rzeczywistych dem pięciu nowych map ani pełnego uploadu z prawdziwymi usługami | `adapt-multi-map-training` |
| `add-operations-and-billing` | Częściowo gotowe — billing i konfiguracja wdrożeniowa w kodzie | Pozostałe: odbiór VPS/publicznego TLS i Stripe, backup/odtworzenie, monitoring i dobór limitów | `wire-personal-training` |
| `prepare-deployment` | Konfiguracja i lokalny odbiór gotowe; VPS do odbioru | Istnieją Caddy/statyki, konfiguracja Django, procedura i szablony timera; odebrać domenę/ACME, instalację timera i restart hosta | `wire-personal-training` |
| `build-subscriptions` | Kod i lokalny odbiór; prawdziwy Stripe do odbioru | 7,99 USD/mies., Pro bez limitu liczby analiz własnego SteamID, Free 3/miesiąc UTC; checkout/portal, podpisane webhooki, uzgodnienie i usuwanie; migracja `0005_billing_accounts` | `wire-personal-training` |
| `verify-live-stripe` | Planowane — konfiguracja i odbiór | Prawdziwy Checkout/portal/webhook i cykl abonamentu w test mode przed live; okresowe uzgodnienie i reakcja na błędy | `build-subscriptions`, `prepare-deployment` |
| `verify-application-e2e` | Planowane — techniczne E2E | Upload → raport → wybór grup → ZIP/CFG → trening członków dla siedmiu map; abonament, kwoty, błędy, uprawnienia, usuwanie i odtworzenie | `verify-tournament-maps`, `refine-group-training`, `add-operations-and-billing`, `build-subscriptions` |
| `prove-scenario-import` | Końcowe próby — G1/G4 | Jedna i 10 sytuacji na każdej z siedmiu map w CS2/Yprac: indeks/gotowość, XYZ, oczy, broń, geometria, powtórzenie i jedno wklejenie; `blocked` i dowody osobno per mapa | `verify-application-e2e` |
| `benchmark-demo-pipeline` | Częściowo gotowe | Pozostał techniczny benchmark na docelowym VPS i dobór zasobów; bez oceny trenera | `bootstrap-cli` |

Historyczne numery bramek zachowano: **G2 (BE) → G3 (UI) → G1 (gra) → G4
(końcowy odbiór)**. Abonament jest częścią aplikacji przed końcowym odbiorem;
pilot biznesowy i oceny trenerów nie są etapami planu.

## Jak rozpocząć nową sesję

1. Przeczytać ten plik, `project-plan.md`, `../README.md` i odpowiednią część
   `integration-validation.md`. Sprawdzić stan Git, zachować zastane zmiany;
   w momencie przekazania wiele plików było nieśledzonych.
2. Kontynuować operacyjną część `add-operations-and-billing` i rzeczywisty
   odbiór Stripe/R2/Steam/SMTP oraz workera Linux. Nie przepisywać gotowego
   modułu `build-subscriptions`. Nie dodawać ocen trenerów ani pilota biznesowego.
   Backend, UI i treningi grupowe są zrealizowane; nie zaczynać ich od nowa.
   Nie przywracać ocen/harmonogramu ani nie usuwać zachowanych danych legacy.
   Na docelowym VPS zastosować `0005_billing_accounts` i odebrać istniejący
   wariant `compose.production.yml` z Caddy/statykami według README.
   Obejrzeć istniejące moduły `exporting.py`, `packs.py`, `cli.py` i ich testy.
   Nie przepisywać parsera, reguły orientacji ani gotowego składania paczek.
   Django i polityki już istnieją; nie dodawać drugiego storage ani retry analizy.
   Przeczytać również `web/pages.py`, `web/practice.py` i `tests/web/test_ui.py`.
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
> Kontynuuj operacyjną część add-operations-and-billing i odbiór prawdziwych usług.
> Moduł Stripe jest w kodzie: 7,99 USD/mies., bez limitu liczby analiz własnego
> SteamID; Free 3 analizy/miesiąc kalendarzowy UTC. Zastosuj 0005_billing_accounts,
> skonfiguruj Stripe i okresowe reconcile_subscriptions według README.
> Bez oceny trenerów, pilota biznesowego i bramek walidacji SaaS.
> Fundament, backend treningowy, UI Tactical HUD
> i treningi grupowe już istnieją. Nie przywracaj ocen ani harmonogramu.
> Caddy/TLS/statyki i szablony timera są
> przygotowane oraz odebrane lokalnie; kontynuuj odbiór na VPS według README,
> nie przepisuj gotowego przepływu ani abonamentu.
> R2/Steam/SMTP wymagają odbioru z prawdziwą konfiguracją. Eksporter i paczki
> są gotowym prototypem, bez próby w grze. Obowiązuje kolejność BE → UI →
> końcowe próby CS2/Yprac; komendy przyjmujemy jako założenie implementacyjne.
> Zachowaj istniejący kod i zastane zmiany.
# Panel obsługi kont — zakres odbioru

Implementacja obejmuje ograniczony Django Admin, MFA, role obsługowe, politykę
indywidualnych limitów i czasowego Pro, blokady/sesje, maile allauth,
snapshot/odświeżanie Stripe i audyt. Bez migracji tożsamości na SteamID,
refundacji, anulowania subskrypcji lub ręcznej edycji danych płatności.
Procedura konfiguracji i semantyka operacji są w README.
Przed produkcyjnym udostępnieniem wykonać odbiór MFA/ról, wysyłki przez docelowy
SMTP, synchronizacji z właściwym środowiskiem Stripe i konfiguracji HTTPS.
Nie utożsamiać testów z atrapami z odbiorem tych usług.
