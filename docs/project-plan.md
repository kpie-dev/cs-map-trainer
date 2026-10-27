# CS2: od przegranego pojedynku do własnego treningu

## Kontekst do dalszej pracy

Ten dokument jest trwałym punktem odniesienia dla kolejnych prac nad projektem. Zawiera uzgodniony zakres, rekomendowaną architekturę, ryzyka, założenia kosztowe, źródła i zależności zadań.

Status: część CLI jest zaimplementowana; pełny przepływ demo → trening nie jest
jeszcze gotowy. Ten dokument zawiera aktualny stan, zadania do kontynuacji oraz
przyszłą architekturę SaaS. Uzgodnienia są oddzielone od rekomendacji i hipotez.
Import scenariuszy do Yprac nie jest potwierdzony próbą w grze, a koszty i ceny
wymagają weryfikacji.

**Aktualna decyzja o kolejności prac:** backend (BE) → UI → końcowe próby
w CS2/Yprac. Na potrzeby implementacji przyjmujemy poprawność komend
i mechanizmu ustawiania scenariuszy. Próba w grze (G1) nie blokuje eksportera,
backendu ani UI; jest częścią końcowego odbioru przed udostępnieniem
zweryfikowanego treningu. Ta decyzja zastępuje wcześniejszy plan „najpierw
G1 i płatny pilot, dopiero potem Django/UI”. Testy jednostkowe, integracyjne
backendu i UI oraz walidacja bezpieczeństwa pozostają w każdym etapie.
Docelową grą pozostaje CS2, nie starsze CS:GO.

Stan implementacji: pakiet Python, kontrakt scenariuszy v1, walidator i CLI
`players`/`analyze`/`benchmark` z przypiętym Awpy 3.1.1. Czytamy dema CS2 Mirage
i generujemy raport JSON v2 z migawkami sprzed wymiany obrażeń, grupowaniem oraz
wykluczeniami. Grupy rozdzielają liczbę porażek od win rate w porównywalnych,
przefiltrowanych wygranych i przegranych starciach. Dokument scenariuszy nadal ma v1.
Reguły `damage-window-v3` zachowują dostępne kąty przeciwnika, a brakujący
pitch/yaw przybliżają kierunkiem ku graczowi z jawnym oznaczeniem; kąty gracza
nie są zgadywane. Ta sama reguła obowiązuje dla porównywalnych wygranych.
Benchmark uruchamia każdą próbę w nowym procesie i nie deklaruje wyczyszczenia cache.
Pipeline sprawdzono na publicznych demach Valve i FACEIT z dogrywką;
pełny benchmark na docelowym VPS i ocena trenera
pozostają otwarte. Nie ma eksportera ani portalu. Uruchomienie opisuje
`../README.md`, a wymaganą próbę w grze `integration-validation.md`.
Poprawność dokumentu JSON nie potwierdza importu.

**Aktualny cel eksportu:** wskazany przez użytkownika
[Yprac Hub by Yesber, Workshop ID `3070715607`](https://steamcommunity.com/sharedfiles/filedetails/?id=3070715607).
Ta decyzja zastępuje wcześniejszy kierunek eksportu wyłącznie do czystego CS2.
Interfejs Yprac Sandbox i wymagania klienta są podstawą założeń eksportera;
ograniczeń zwykłej konsoli nie przenosimy automatycznie na Yprac. Hub jest punktem wejścia;
nie potwierdzono jeszcze konkretnej mapy Mirage uruchamianej przez Hub ani
zgodności jej geometrii ze źródłowym demem.

Aktualny etap integracji: **implementacja na zaakceptowanych założeniach,
próby w grze po backendzie i UI**. Poradnik Yprac opisuje `mirage` i
`mode sandbox`, lecz nie znaleziono w przejrzanych źródłach specyfikacji importu
dowolnych XYZ i kątów obu stron. Nie potwierdzono kierunku oczu bota,
deterministycznej sekwencji ani konkretnej rewizji mapy. Macierz źródeł,
pytania do autora i przekazanie dla przyszłego testera są w
`integration-validation.md`. Brak potwierdzenia nie oznacza niemożliwości
integracji; G1 pozostaje otwarte, ale nie jest zależnością prac implementacyjnych.

Nowy trop do próby: `setpos_player <player_index> <x> <y> [z]`.
Użytkownik wskazał składnię z Valve Developer Community; chodzi o indeks
gracza, nie `userid` z `status`. Usunięcie botów i dodanie jednego może
ułatwić przewidywalny wybór indeksu, ale indeks `2`, gotowość bota oraz
działanie w Yprac nie są potwierdzone. Szczegóły próby i pochodzenie
ustalenia są w `integration-validation.md`.

Przed rozpoczęciem zadania przeczytać właściwe sekcje i sprawdzić jego zależności. Dokument aktualizować przy zmianach zakresu, decyzjach technicznych oraz potwierdzeniu lub odrzuceniu hipotez. Nie traktować proponowanego rozwiązania jako działającego bez dowodu opisanego w kryteriach przejścia.

## Przekazanie prac do następnego wątku

Skrócony plan wykonawczy z todos, zależnościami i wiadomością startową
do nowej sesji: [implementation-todos.md](implementation-todos.md).

Ten plik jest źródłem prawdy do kontynuacji, niezależnym od historii rozmowy
i sesyjnej bazy zadań. Nie zaczynać implementacji od nowa: dokończyć backend
na istniejącym parserze i kontrakcie, następnie zbudować UI.

### Gotowe

| Obszar | Co działa | Miejsce |
|---|---|---|
| Fundament projektu | Python 3.11+, pakiet, `uv`, lockfile, przypięty Awpy 3.1.1 | `pyproject.toml`, `uv.lock`, `src/cs_map_trainer/` |
| Kontrakt scenariuszy | Wersja 1, walidacja typów, pozycji, kątów, ticków, stron i uczestników; syntetyczny przykład | `scenarios.py`, `tests/fixtures/synthetic-scenarios.json` |
| CLI | `players`, `analyze`, `benchmark`, `validate-scenarios`, `schema`; JSON na stdout lub do nowego pliku bez nadpisywania | `cli.py` |
| Parser | Nieskompresowane CS2 `.dem` do 1 GiB, tylko `de_mirage`; skład, rundy, zgony, obrażenia i zbiorcze migawki; hash wejścia i jawne błędy | `parsing.py` |
| Analiza | Wspólny tick sprzed obrażeń, pozycje i dostępne kąty obu stron; brakujący pitch/yaw przeciwnika przybliżany kierunkiem ku graczowi z jawnym oznaczeniem; wykluczenia i grupowanie z kontekstem | `analysis.py` |
| Statystyki | Raport `analysis_version: 2`; porównywalne wygrane i przegrane, liczebność próby, win rate tylko w przefiltrowanych rozstrzygniętych starciach; ranking według liczby porażek | `analysis.py` |
| Benchmark | Każdy przebieg w nowym procesie; czas, CPU, RSS, operacje blokowe I/O, rozmiar JSON, timeout i kontrola identyczności wyników; bez fałszywej deklaracji cold cache | `benchmark.py` |
| Docker | Wieloetapowy obraz CLI, użytkownik bez roota, zależności wykonawcze z lockfile, dane przez bind mount; bez serwera WWW | `Dockerfile`, `.dockerignore`, `README.md` |
| Testy i CI | Testy jednostkowe, opt-in integracja na lokalnym demie, workflow lint/format/test/build; zdalny wynik GitHub Actions nie był tu potwierdzany | `tests/`, `.github/workflows/ci.yml` |

Ścieżki modułów w tabeli odnoszą się do `src/cs_map_trainer/`.
Lokalnie sprawdzono pipeline na publicznych, zweryfikowanych checksumami demach
Valve oraz FACEIT Mirage, w tym demie obejmującym dogrywkę, a także w Dockerze.
Źródła i hashe są w `README.md`. Pobierane do prób dema zostały usunięte:
nie są częścią repozytorium ani obrazu. Test integracyjny wymaga ponownego
wskazania uprawnionej lokalnej próbki przez `CS_MAP_TRAINER_DEMO`.
To nie jest ręczna weryfikacja każdego kontaktu ani benchmark docelowego VPS.

### Ostatnio wykonane kroki

| Krok | Status i rezultat |
|---|---|
| Badanie publicznych interfejsów Yprac | Zakończono przegląd wskazanych poradników, rozwijanych sekcji komend i repozytorium wydań. Udokumentowano możliwości i niewiadome; nie znaleziono specyfikacji pełnego importu w przejrzanych źródłach |
| Dokumentacja blokad i przekazanie dla testera | Gotowe w `integration-validation.md`: macierz zdolności, pytania do autora, próba jednej i 10 sytuacji, pomiary obu stron, restart, sposób liczenia błędów i pola dowodu. Pytania nie zostały wysłane; tolerancje i metoda odczytu wymagają uzgodnienia przed próbą |
| Awaryjna orientacja przeciwnika | Zaimplementowana w `analysis.py`, reguły `damage-window-v3`: tylko brakujący pitch/yaw jest wyliczany ku pozycji gracza ze wspólnej migawki; dostępne kąty są zachowane |
| Jawność przybliżenia i porównywalność | Scenariusz i kontekst grupy zawierają `opponent_aim_inferred_toward_player`; grupy przybliżone są oddzielone od kompletnych. Identyczne zasady dla wygranych i przegranych; raport pozostaje v2, scenariusze v1 |
| Regresja i dokumentacja orientacji | Dodano testy brakujących pól i częściowych kątów, osi i wysokości, zachowania oryginalnego celowania, błędnych danych, nieokreślonego kierunku oraz grupowania wygranych/przegranych. Dostosowano test integracyjny, README i protokół G1; testy jednostkowe i lint/format przeszły, integrację na demie pominięto z powodu braku lokalnej próbki |

Przybliżenie kierunku zakłada jednakową wysokość oczu stojących uczestników.
Nie zastępuje brakującej pozycji, nie naprawia nieprawidłowych kątów i nie
potwierdza możliwości ustawienia oczu bota w Yprac. **G1 pozostaje otwarte**:
brakuje potwierdzonego interfejsu oraz pomiarów w grze. Zgodnie z aktualną
decyzją nie blokuje to backendu i UI; weryfikacja nastąpi na końcu.

### Czego jeszcze nie ma

Nie ma eksportera komend/CFG, działającego importu do Yprac, wyboru i odrzucania
sytuacji w osobnym przepływie CLI, paczek z instrukcjami i manifestem zgodności,
ocen treningu ani kolejki powtórek. Nie ma też portalu, kont, uploadu, bazy danych,
kolejki zadań, produkcyjnego workera i płatności. Raport JSON nie jest skryptem
treningowym i nie należy go przedstawiać jako gotowego produktu.

### Od czego zacząć następny wątek

1. Przeczytać ten dokument, `README.md` oraz `docs/integration-validation.md`.
   Obejrzeć istniejący kod i stan Git; nie usuwać zastanych zmian.
2. Zaimplementować jeden eksporter Yprac i składanie paczek na zaakceptowanych
   założeniach komend: automatyczne ustawienie obu stron po jednym wklejeniu,
   walidacja danych, manifest, jawny status zgodności i testy generowanego wyjścia.
3. Ustalić polityki minimalnego backendu i zbudować Django/PostgreSQL:
   prywatny upload, wybór gracza, asynchroniczna analiza, wyniki, wybór/odrzucanie
   sytuacji, paczki i autoryzowany dostęp. Wykorzystać istniejące moduły CLI.
4. Po backendzie zbudować UI na szablonach Django: upload, status zadania,
   wybór gracza, raport, wybór sytuacji i kopiowanie komend jednym przyciskiem.
5. Sprawdzić aplikację automatycznie, następnie wykonać końcowe próby w CS2/Yprac:
   jedna sytuacja, potem 10, orientacja obu stron, broń, restart i jedno wklejenie.
   Brak próby oznacza „niezweryfikowane w grze”, nie zakaz implementacji.
6. Przed udostępnieniem potwierdzić zgodność mapy i komend, zasoby oraz
   uprawnienia. Pilot płatny i decyzja o dalszym skalowaniu następują później,
   nie są warunkiem rozpoczęcia backendu/UI.

Polecenia lokalne są opisane w `README.md`; projekt nadal obsługuje uruchomienie
przez skrypty i Docker, bez potrzeby UI. Szczegółowe statusy i zależności
pozostałych etapów są w sekcji „Todos i zależności”.

## Rekomendacja

Warunkowe TAK dla wąskiego produktu: użytkownik przesyła demo, wybiera siebie, dostaje powtarzające się przegrane pojedynki i paczkę treningową odtwarzającą ich ustawienie przestrzenne. NIE dla obietnicy automatycznego wykrywania wszystkich największych błędów i wiernego odtwarzania całych akcji.

Zgodnie z decyzją właściciela najpierw powstają backend i UI, przy założeniu
poprawności komend, a próby importu do Yprac Hub/Sandbox odbywają się na końcu.
To świadome ryzyko późniejszych poprawek eksportera i przepływu aplikacji.
Potwierdzony trening i płatności nadal są podstawą decyzji o skalowaniu
produktu, ale nie blokują budowy aplikacji. Python pozostaje wybranym stosem.

## Uzgodniony zakres

- Pierwszy odbiorca: gracz indywidualny, model freemium z niedrogą subskrypcją. Równolegle kontakt z trenerami słabszych drużyn i akademii jako partnerami walidującymi i kanałem sprzedaży.
- Użytkownik podał 3 dema tygodniowo jako przykładowy darmowy limit, nie jako zatwierdzony wymóg.
- Rdzeń MVP łączy prostą analizę i odtworzenie pozycji z konkretnych przegranych pojedynków. Same ogólne zalecenia lub dobór gotowego ćwiczenia nie wystarczą.
- Użytkownik akceptuje istniejący klient Yprac. Preferuje skopiowanie komend
  do konsoli zamiast umieszczania pobranych plików w katalogu klienta; `.cfg`
  pozostaje opcją dodatkową, nie obowiązkowym sposobem instalacji.
- Automatyczne ustawienie botów jest wymaganiem. Ręczna instrukcja ustawiania botów nie jest równoważnym wykonaniem tego wymagania.
- Po wejściu do właściwej mapy i trybu użytkownik ma wkleić ustawienie
  scenariusza **raz do konsoli**, bez ręcznego odczytywania indeksu bota,
  wpisywania kolejnych komend i obowiązkowego zapisywania pliku CFG.
  Bindy użytkownika nie mogą być nadpisywane.
- Na życzenie użytkownika zapis/odczyt pozycji przyjmujemy jako założenie
  robocze, nie dowód runtime. Poradnik Yprac opisuje `savepos`/`loadpos`;
  nazwy `saveposition`/`loadposition` z rozmowy nie są potwierdzonymi aliasami.
  Założenie nie dowodzi zapisu bota, trwałości slotów ani synchroniczności.
- Docelowy config ma działać ze wskazanym Yprac Hub, Workshop ID `3070715607`.
  Nie implementować równolegle Yprac, Grindhouse i Refrag.
- Kolejność realizacji: backend z eksporterem i paczkami, następnie UI,
  na końcu próby w CS2/Yprac. Poprawność komend jest założeniem roboczym;
  testy aplikacji trwają przez cały rozwój. Płatny pilot nie blokuje Django/UI.
- Liczby testerów, aktywacji, powrotów i płatności są metrykami pomocniczymi,
  nie progami automatycznie blokującymi przejście do SaaS.
- Bieżący kod jest bez UI, ale planowane MVP obejmuje backend i UI aplikacji
  oraz lokalny CS2 z Yprac Hub i wymaganymi komponentami Yprac. Czysty CS2
  z `sv_cheats 1` nie zastępuje domyślnie tej integracji.
- Skrypt ma sam rozpoznawać bota i odtwarzać także jego orientację. Ręczne podanie
  indeksu bota ani pominięcie jego kąta widzenia nie spełnia tego zakresu.
- Nie zaakceptowano własnego serwera/pluginu. Eksporter powstaje teraz na
  zaakceptowanych założeniach, z oznaczeniem braku próby w grze. Badanie
  skryptów i kontakt z autorem pozostają opcją w razie niepowodzenia odbioru.

## Krytyka biznesowa

| Ryzyko | Dlaczego ma znaczenie | Najtańsza odpowiedź |
|---|---|---|
| Kolejny dashboard statystyk | Leetify i SCOPE już adresują analizę, a Yprac i Refrag trening. Sam parser, heatmapa czy opis AI są łatwe do skopiowania. | Sprzedawać konkretny rezultat: własne pojedynki gotowe do ćwiczenia i kolejkę powtórek. Zweryfikować dokładne nakładanie się funkcji konkurencji przed deklarowaniem unikalności. |
| „Najczęściej tam giniesz” nie oznacza „tam grasz najgorzej” | Popularna pozycja generuje więcej zdarzeń; zgony zależą od roli, ekonomii, przeciwników i ekspozycji. | Oddzielić liczbę zgonów od skuteczności pojedynków. Przy małej próbie pokazywać liczbę obserwacji i brak podstaw do silnego wniosku. |
| Śmierć nie zawsze jest błędem | Dobry entry, poświęcenie pod trade, zła komunikacja lub cel zespołowy nie wynikają jednoznacznie z dema. | Nazywać wynik kandydatem do treningu, nie werdyktem. Umożliwić odrzucenie sytuacji i ocenę przez trenera. |
| Gracz czyta raport, ale nie ćwiczy | Upload, instalacja, import i uruchomienie mogą zabić aktywację. | Mierzyć przejście od analizy do rzeczywistego treningu, nie liczbę wysłanych dem i pobrań ZIP. |
| 3 darmowe dema tygodniowo mogą wystarczyć | Wtedy większy limit nie daje wystarczającej motywacji do abonamentu. | Testować limity zamiast je utrwalać. Płatna wartość: historia problemów, zapisane paczki, własny wybór pojedynków i kolejka powtórek. |
| Drugi abonament | Gracz może dodatkowo potrzebować płatnego dostępu do map lub trybów dostawcy. Yprac opisuje darmową rotację i premium. | Sprawdzić prawa dostępu do wybranego trybu; pokazać całkowity koszt przed zakupem. Preferować ścieżkę niewymagającą dodatkowej płatności. |
| Zbyt szeroki start B2C i B2B | Panel drużyn, role, rozliczenia i raportowanie trenerów to drugi produkt. | Początkowo trener ocenia paczki poza aplikacją. Funkcje drużynowe dopiero po potwierdzonym zainteresowaniu płatnym. |
| Zależność od cudzych aktualizacji | Zmiana CS2, parsera, mapy albo komend partnera może zepsuć eksport. | Jedna wspierana integracja i mapa, przypięte wersje, testy regresji oraz możliwość jawnego wyłączenia niedziałającego eksportu. |

Przewaga, jeśli powstanie, będzie wynikała z jakości wybranych sytuacji, bezproblemowego uruchomienia treningu oraz danych o tym, które ćwiczenia pomagają. Nie z użycia Pythona ani LLM.

Analogia do Chessable jest użyteczna dla powtórek i zapamiętywania sytuacji. Nie jest trafna jako obietnica obiektywnego silnika oceny decyzji: CS2 zawiera niepełną informację, komunikację głosową i intencje zespołu niewidoczne w standardowej analizie.

## Co potwierdzają źródła, a czego jeszcze nie wiadomo

| Obszar | Potwierdzone | Niepotwierdzone / konsekwencja |
|---|---|---|
| Awpy | Dokumentacja `latest` i README opisują parser Rust, API Python, Polars, zdarzenia, migawki stanu i licencję MIT kodu. Obecnie opisany rdzeń to pbdems2. | Nie zakładać, że aktualne Awpy jest tylko wrapperem demoparser2. Sprawdzić wybrane opublikowane wydanie, przypiąć je i zmierzyć na własnych demach. |
| Wskazany Workshop `3070715607` | Strona identyfikuje pozycję jako **Yprac Hub by Yesber**. Poradnik Yprac opisuje Hub jako punkt wejścia do treningu na wspieranych mapach. | Nie przejrzano plików tej mapy ani jej skryptów. Hub nie jest dowodem zgodności z geometrią Mirage z dema ani obsługi importu XYZ/kątów. |
| Widoczność Awpy | Test geometrii statycznej nie modeluje smoke'ów, ruchomych drzwi ani penetracji; pozycja gracza nie jest pozycją oczu. | Wynik raycastu nie jest dowodem, że gracz faktycznie widział przeciwnika. |
| Yprac Sandbox | Poradnik komend opisuje `mirage`, `mode sandbox`, `place [1-5]`, `savepos`, `loadpos`, `swap`, `weapon`, `botweapon`; ostatnie zmienia broń wszystkich botów. | Nie znaleziono w przejrzanych źródłach specyfikacji importu dowolnych XYZ i kątów obu stron. Chatowe `setpos` jest aliasem `loadpos`. `restart` opisuje reset trasy, nie potwierdzoną trwałość własnego układu Sandbox. |
| Yprac i Workshop | Oficjalny poradnik opisuje klient Yprac, Hub oraz określony zbiór wspieranych map Workshop. | Nie zakładać, że stara mapa CS:GO działa tak samo w CS2 ani że każda mapa Workshop jest wspierana. |
| Klient i publiczne wydania Yprac | Poradnik oferuje klienta Windows i link instalacyjny v2.0.1; podczas badania 2026-10-27 API GitHub wskazało latest v2.6.8. Główny katalog repozytorium wydań zawierał tylko README, bez specyfikacji API. | Żadna wersja nie jest zweryfikowaną wersją integracji. Nie przejrzano binariów ani skryptów mapy; brak publicznej specyfikacji nie dowodzi braku interfejsu. Dostęp do Sandbox/Mirage i warunki komercyjne wymagają potwierdzenia. |
| Refrag Creator Studio | Udokumentowane tworzenie aren, spawnów, botów, zapis i publikacja zestawu. `.importsettings` importuje ustawienia ze stringa. | Import ustawień nie dowodzi importu spawnów, ścieżek i całych scenariuszy. API/import przestrzenny wymaga osobnego potwierdzenia. |
| Grindhouse | Użytkownik wskazał `grindhouse.online` i komendy `.bot`, `.start`, `.save`. | Strona zwróciła HTTP 401; nie zweryfikowano składni, importu ani uprawnień. Nie utożsamiać Grindhouse z Refrag. |
| Licencje | Kod Awpy i skrypty awpy-data mają MIT. Repozytorium awpy-data wyraźnie oddziela to od własności assetów Valve. | MIT parsera nie daje automatycznie praw do redystrybucji map, radarów ani cudzych treści treningowych. Zweryfikować zasady komercyjnego użycia integracji. |

Nie udało się wiarygodnie zestawić aktualnych cen i wszystkich limitów konkurencji. Nie podawać niezweryfikowanych cen jako faktów ani twierdzić, że nikt nie oferuje podobnych funkcji.

## Kolejność realizacji: backend → UI → odbiór w grze

Bieżącą próbę Yprac Hub/Sandbox opisuje `integration-validation.md`.
To jedyny planowany cel eksportera. Nie należy przenosić ograniczeń zwykłej
konsoli CS2 na interfejs Yprac bez sprawdzenia jego możliwości.

### Etap BE — następna implementacja

1. Eksporter jednego scenariusza i paczek: inicjalizacja jednego bota,
   `setpos_player` z indeksem gracza, pozycje/kąty i broń obu stron,
   zapis/odczyt oraz jedno wklejenie do konsoli. Poprawność mechanizmu,
   w tym przyjętego indeksu bota, traktować jako założenie do końcowej próby,
   nie jako już uzyskany dowód. Szczegóły komend utrzymać w jednym module.
2. Selekcja i odrzucanie sytuacji, manifest paczki, instrukcja i wersjonowanie
   eksportera. Walidować liczby, broń, mapę i dozwolone komendy; nie emitować
   nazw/tekstu z dema jako kodu. Nie nadpisywać bindów ani `autoexec.cfg`.
3. Wybrać polityki storage/auth/limitów/retencji i zbudować backend Django,
   PostgreSQL, Django-Q2 ORM oraz izolowany worker. Obsłużyć prywatny upload,
   skład, wybór gracza, analizę, raporty i autoryzowane paczki.
4. Dodać testy kontraktów, eksportera, zadań, uprawnień, retry i limitów.
   G2 oznacza gotowość backendu, nie potwierdzenie treningu w grze.

### Etap UI — po backendzie

Szablony Django, opcjonalnie HTMX: upload i błędy wejścia, status zadania,
wybór gracza, raport z ograniczeniami i przybliżonymi kątami, wybór/odrzucanie
sytuacji, zapis paczki i przycisk kopiowania pełnego ustawienia scenariusza.
Jeden scenariusz aktywny naraz; bez ręcznego indeksu bota i przepisywania
wielu komend. Dodać deklarowane oceny/powtórki i testy przepływu aplikacji.
Do odbioru w grze UI i manifest wskazują „niezweryfikowane w grze”.
G3 oznacza gotowość aplikacji do końcowych prób, nie decyzję biznesową.

### Końcowy etap — próby CS2/Yprac (G1 i G4)

Po ukończeniu backendu i UI wykonać poniższą procedurę. Brak testera odracza
odbiór w grze, ale nie blokuje wcześniejszej implementacji.

1. Zacząć od wskazanego Hub `3070715607`. Ustalić konkretną wspieraną wersję Mirage i tryb Sandbox, wymagany klient oraz dostęp. Parser obsługuje `de_mirage`, ale zgodność docelowej mapy pozostaje niepotwierdzona.
2. Na ręcznie przygotowanej sytuacji sprawdzić: ustawienie XYZ i kąta gracza, ustawienie XYZ i kąta jednego bota, broń, restart i ponowne wykonanie ćwiczenia.
3. Ustalić rzeczywisty mechanizm importu: natywny format scenariusza, oficjalny interfejs albo komendy dostępne w wybranym trybie. W razie braku dokumentacji zapytać autora Yprac o wspierany import i zgodę na integrację.
4. Jeżeli proponowany mechanizm to `.cfg`, wykonać próbę od czystej instalacji użytkownika: kopiowanie paczki, wejście do właściwego trybu i `exec`. Samo wygenerowanie syntaktycznie poprawnego pliku nie jest dowodem działania.
5. Osobno sprawdzić kolejność wykonania. Sekwencja teleport -> komenda chat -> teleport nie musi być synchroniczna. Nie opierać produktu na zgadywanych opóźnieniach, masowym spamowaniu chatu ani niepotwierdzonym `wait`.
6. Zweryfikować uprawnienia. Komenda lokalna nie oznacza uprawnienia do teleportowania się na zewnętrznym serwerze. Yprac, czysta sesja lokalna i serwer Grindhouse to różne środowiska.
7. Potwierdzić zgodność współrzędnych oraz geometrii konkretnej wersji mapy z demem. Wspólna nazwa mapy nie wystarczy.
8. Przeprowadzić próbę paczki 10 różnych pojedynków, po jednym aktywnym scenariuszu naraz. Porównać pozycje, orientację, broń i możliwość powtórki z referencją; zapisać ograniczenia oraz wyniki.

Kryterium końcowego odbioru: automatyczne ustawienie i powtórzenie scenariuszy działa od początku do końca na koncie zwykłego użytkownika, w zadeklarowanym środowisku, bez ręcznego stawiania botów i bez kruchych wyścigów czasowych. G1 jest wykonywane po G2 i G3, mimo zachowania historycznej numeracji.

Jeśli Yprac nie zapewnia tej ścieżki, udokumentować wynik i uzyskać współpracę
autora albo osobną decyzję o alternatywie. Nie przełączać configu samodzielnie
na inną mapę, czysty CS2 lub własny serwer i nie implementować równolegle
trzech niedokumentowanych adapterów.

Własny serwer z pluginem CounterStrikeSharp może zapewnić kontrolę nad spawnami i wynikami, ale dodaje C#/.NET, administrację CS2 i koszty serwerów. To plan awaryjny wymagający osobnej decyzji, nie automatyczny zakres MVP. Plugin serwerowy nie jest plikiem do skopiowania do zwykłego klienta gry.

Jeżeli żaden tani mechanizm nie spełnia wymogu automatycznego ustawiania, jawnie zatrzymać tę wersję produktu i zdecydować o zmianie zakresu. Nie przedstawiać instrukcji ręcznego ustawiania jako działającego eksportu.

## MVP: dokładny przepływ i granice

1. Użytkownik przesyła `.dem` i po odczytaniu składu wskazuje swój SteamID. Trener może wskazać innego uprawnionego zawodnika.
2. System wybiera bezpośrednie przegrane pojedynki i pokazuje dowody: mapa, runda, uczestnicy, pozycje, broń oraz kontekst zdarzenia.
3. Powtarzające się podobne sytuacje tworzą małe grupy. Ranking rozdziela częstość od skuteczności i wskazuje rozmiar próby.
4. Użytkownik dostaje małą paczkę scenariuszy: jego punkt startu i bot w pozycji przeciwnika z tej samej chwili. Opcjonalnie dobierany jest gotowy drill dla mierzalnego problemu.
5. Paczka trafia do jednej sprawdzonej integracji. Pobranie zawiera instrukcję uruchomienia i informacje o wspieranej mapie, wersji i wymaganiach.
6. Gracz wykonuje scenariusze i może oznaczyć je jako wykonane, łatwe, trudne lub nietrafne. Na tej podstawie powstaje prosta kolejka powtórek.

Bez integracji zwrotnej wykonanie i trudność są deklaracją użytkownika, nie automatycznie zmierzonym wynikiem. Nie obiecywać pomiaru poprawy celowania z samego pobrania `.cfg`.

### Ważne szczegóły rekonstrukcji

- Nie używać wyłącznie pozycji w chwili śmierci. Pobierać wspólną migawkę gracza i przeciwnika sprzed rozstrzygnięcia starcia, powiązaną z początkiem kontaktu lub wymianą obrażeń.
- Zaczynać od jednego przeciwnika i statycznego odtworzenia ustawienia. Bot w pozycji z dema nie odtwarza ruchu, reakcji, peeka i taktyki człowieka.
- Odtworzyć orientację gracza sprzed kontaktu, zamiast automatycznie ustawiać celownik na głowie bota.
- Zachować dostępne kąty przeciwnika z dema. Jeśli brakuje pitch lub yaw,
  uzupełnić tylko brakującą składową kierunkiem ku pozycji gracza ze wspólnej
  migawki, z oznaczeniem `opponent_aim_inferred_toward_player`. Jest to
  przybliżenie z założeniem jednakowej wysokości oczu stojących uczestników,
  nie pomiar z dema. Reguła `damage-window-v3` działa tak samo dla wygranych
  i przegranych, a grupowanie rozdziela dane przybliżone od kompletnych.
  Nie zastępuje wymogu rzeczywistego ustawienia kierunku oczu bota w Yprac.
- Wstępnie odrzucać zgony od świata, samobójstwa, teamkille, granaty i sytuacje nieobsługiwane przez eksport. Flash, smoke, penetrację i brakujące dane oznaczać jako ograniczenia; brak pola nie oznacza braku takiego efektu.
- Nie składać wszystkich zgonów w jeden jednocześnie aktywny układ botów. Każdy pojedynek jest osobnym scenariuszem.
- Grupować z uwzględnieniem pozycji obu stron, strony T/CT i kontekstu. Sama heatmapa miejsc śmierci nie identyfikuje tego samego pojedynku.
- Umożliwić odrzucenie nietrafnej sytuacji. Nie mnożyć reguł analizy przed oceną pierwszych wyników przez graczy i trenerów.

Poza MVP: pełne odtwarzanie akcji 5v5, dynamiczne ścieżki wszystkich botów, automatyczna ocena strategii, własny aim trainer, własny klient desktopowy, renderowanie filmów, analiza voice comms, scraping dem z kont graczy oraz rozbudowany panel organizacji.

## Wybrany kierunek backendu i UI — jeszcze niezaimplementowany

```text
Przeglądarka
  -> Django: sesja, upload, wybór gracza, raport, pobranie
  -> prywatny storage S3/R2: upload dema

Django -> PostgreSQL: użytkownicy, uprawnienia, zadania, wyniki, powtórki
       -> kolejka Django-Q2 z brokerem ORM w tym samym PostgreSQL
       -> osobny proces/container workera Python
            -> Awpy + Polars
            -> wybór pojedynków i proste reguły
            -> wewnętrzny dokument scenariuszy
            -> jeden sprawdzony eksporter
```

- Django z szablonami; HTMX tylko tam, gdzie upraszcza status zadania lub interakcję. Auth, sesje, ORM i panel administracyjny w jednym stosie. Nie dokładać Next.js i osobnego API bez potrzeby produktu.
- PostgreSQL od wdrożenia współdzielonego przez web i workera. Bez osobnego Redis/Celery na start: Django-Q2 dokumentuje broker ORM jako dogodny dla umiarkowanej liczby zadań.
- Jeden mały VPS w UE, Docker Compose, reverse proxy z TLS i jeden worker parsujący na początku. Przed zakupem dobrać RAM na podstawie pomiarów, nie samej wielkości pliku.
- Pliki poza bazą. R2 jest kandydatem dzięki zgodności S3 i brakowi opłat za egress z samego R2. Na ściśle zamknięty pilot można użyć lokalnego dysku VPS z twardą kwotą, jeśli potwierdzono pojemność i zaakceptowano ryzyko utraty odtwarzalnych plików.
- Nie utrzymywać dwóch wariantów storage w pierwszej implementacji: wybrać jeden po pomiarze pilota.
- FastAPI ma sens, jeśli wykonawca już ma gotowy frontend i infrastrukturę auth/admin. W pustym projekcie oznacza więcej elementów do samodzielnego złożenia.
- Brak LLM, GPU, Kubernetes, ClickHouse, wektorowej bazy i własnej infrastruktury gry w podstawowym wariancie.
- Do pilota wystarczy zewnętrzny link płatniczy i ręczne nadanie dostępu. Automatyczny abonament i webhooki dopiero po potwierdzeniu płatności.

### Minimalny model danych i moduły

- `uploads`: właściciel, rozmiar, prywatny klucz pliku, checksum, rozpoznana mapa/build i stan retencji.
- `analysis_jobs`: status, wersje parsera i reguł, identyfikator zadania, błąd, próby, zużyte zasoby.
- `duels`: referencja do rundy i ticków, uczestnicy, wspólne migawki, kategoria i ograniczenia.
- `training_packs`: wybrane scenariusze, format i wersja eksportera oraz zgodność mapy.
- `practice_reviews`: deklaracja wykonania/trudności, odrzucenie oraz następna powtórka.
- Konta i uprawnienia przez Django; uprawnienia do płatnej funkcji jako prosty, jawny stan.

Wewnętrzny scenariusz przechowuje: `schema_version`, źródło/rundę/ticki, mapę i jej identyfikatory wersji, punkt oraz orientację gracza, punkt oraz orientację bota, broń, obsługiwane parametry i ograniczenia. Pozycje to światowe XYZ, nie piksele radaru.

To niewielki kontrakt danych oddzielający analizę od jednego eksportera, nie rozbudowany framework pluginów. Pozwala później dodać drugi format bez przepisywania parsera i całej aplikacji.

### Parsowanie, poprawność i odporność

- Zacząć od Awpy; porównywać z demoparser2 tylko jeśli pomiary lub brakujące pola ujawnią konkretną potrzebę. Nie utrzymywać od razu dwóch parserów produkcyjnych.
- Przypiąć opublikowane wydanie i lockfile. Zestaw testowy powinien zawierać różne wspierane źródła dem, zmiany stron i dogrywki.
- Czytać potrzebne zdarzenia i wybrane właściwości. Zbierać migawki kandydatów zbiorczo, nie uruchamiać pełnego parsowania osobno dla każdego pojedynku.
- Nie utrwalać całego tick-by-tick stanu wszystkich graczy, jeśli produkt potrzebuje kilkunastu sytuacji. Selekcja wyjścia zmniejsza wynik i RAM, ale nie gwarantuje proporcjonalnego spadku czasu dekodowania.
- Mierzyć czas ścienny, łączne CPU-sekundy procesu i wątków, szczyt RSS, I/O i rozmiar wyników na docelowej klasie VPS. Odróżniać pierwszy przebieg od cache.
- Osobny worker nie może wyczerpać pamięci weba i bazy. Limit procesów, pamięci i wątków parsera/Polars dobrać po pomiarach.
- Stany zadań muszą być jawne: przyjęte, oczekujące, przetwarzane, gotowe, nieobsługiwane, błędne. Ograniczyć ponowienia i pokazywać przyczynę użytkownikowi.
- Dostarczenie zadania może nastąpić ponownie. Przetwarzanie i naliczanie limitu muszą być idempotentne. W Django-Q2 `retry` musi uwzględniać timeout i oczekiwanie wewnątrz kolejki.
- Cache po hashu i wersjach jest optymalizacją wewnętrzną, nie publicznym identyfikatorem wyniku. Nie ujawniać cudzych dem ani raportów przez deduplikację.
- Niezgodność mapy, brak danych lub brak możliwości eksportu mają kończyć się czytelnym statusem, nie pozornie poprawną paczką.

### Instalacja po stronie gracza

Cel: subskrypcja wskazanego Yprac Hub i spełnienie potwierdzonych wymagań klienta.
Preferowany rezultat eksportu to przejrzyste komendy do skopiowania do konsoli,
korzystające ze wspieranego interfejsu Yprac. Natywny import albo `.cfg` mogą być
opcją dodatkową po potwierdzeniu; nie wymagać domyślnie instalowania losowego
pliku w katalogu gry. Nie zakładać, że komendy chatu Yprac można bezpiecznie
połączyć w jedną synchroniczną linię konsoli.

Przeglądarka nie zapisze samodzielnie plików do dowolnego katalogu gry.
Bez wspieranego importu odnośnikiem/protokołem albo aplikacji lokalnej nie obiecywać
automatycznej instalacji. Na tym etapie wystarcza jawna instrukcja uruchomienia
Hub, właściwej mapy i trybu oraz wklejenia wygenerowanych komend.

Nie nadpisywać `autoexec.cfg`, istniejących bindów ani ustawień użytkownika. Używać własnej przestrzeni nazw i tylko dozwolonych komend. Nazwy i tekst z dema nie mogą trafiać jako surowe polecenia do eksportu. Nie stosować wstrzykiwania kodu do gry ani automatyzacji wejścia w celu obchodzenia ograniczeń integracji.

## Koszty: model zamiast obietnicy

Poniższe liczby są założeniami do rachunku, NIE benchmarkiem ani ofertą dostawcy:

- Średni upload: 0,25 GB na demo.
- 3 dema na tydzień to w przybliżeniu 13 dem miesięcznie na aktywnego gracza.
- Przykładowy pełny pipeline: 60 CPU-sekund na demo. Należy zmierzyć sumę pracy wszystkich wątków; to niekoniecznie 60 sekund oczekiwania użytkownika.
- Surowe pliki usuwane po analizie, z buforem na retry nieprzekraczającym 24 godzin. Wyniki i scenariusze mają osobną politykę retencji.

| Aktywni darmowi gracze | Dema/miesiąc | Upload/miesiąc | CPU przy przyjętym założeniu | Średni stan surowych plików przy retencji 24 h i równym napływie |
|---|---:|---:|---:|---:|
| 100 | 1 300 | 325 GB | ok. 21,7 CPU-h | ok. 10,8 GB |
| 1 000 | 13 000 | 3 250 GB | ok. 216,7 CPU-h | ok. 108,3 GB |

Wniosek: liczba darmowych użytkowników ma znaczenie nawet przy niedrogim parserze. Równe miesięczne obciążenie nie gwarantuje obsługi szczytów, odpowiedniego RAM ani akceptowalnej kolejki.

R2 Standard ma w sprawdzonym cenniku 10 GB-miesiąca bezpłatnej przestrzeni, potem 0,015 USD/GB-miesiąc; operacje są rozliczane osobno z własnymi pulami. Dla przykładowych 108,3 GB koszt samej przestrzeni wynosi około 1,5 USD ponad pulę. Przy retencji 30 dni w stanie ustalonym byłoby to około 3 250 GB, czyli około 48,6 USD samej przestrzeni ponad pulę. Retencja robi większą różnicę niż przedwczesna optymalizacja kilku zapytań.

Orientacyjny budżet infrastruktury małego pilota: 80-200 zł miesięcznie na VPS, niewielki storage, backup bazy i podstawowe usługi, plus prowizje płatnicze i ewentualny dostęp do narzędzia treningowego. To budżet planistyczny do potwierdzenia po benchmarku i wyborze ofert, nie gwarancja obsługi 1 000 graczy. Nie obejmuje pracy, wsparcia, księgowości, podatków ani akwizycji.

Przy hipotetycznej cenie 29 zł brutto i stawce VAT 23%, jeżeli taka stawka ma zastosowanie, zostaje około 23,58 zł przed prowizjami i innymi kosztami. 50 abonentów to około 1 179 zł przed tymi kosztami, nie utrzymanie pełnoetatowego twórcy. Nie mylić taniego hostingu z rentownym biznesem.

Ograniczenia kosztowe: zamknięty nabór pilota, limity uploadu i liczby zadań, jedna aktywna analiza na użytkownika, mała globalna współbieżność oraz alarmy na zajętość dysku, błędy i długość kolejki. Nie wprowadzać nielimitowanego planu.

## Walidacja produktu i monetyzacji

- Backend i UI powstają przed próbami w grze i płatnym pilotem. Po końcowym
  odbiorze przygotować zweryfikowane paczki na własnych demach testerów;
  nie rozszerzać portalu o funkcje spoza minimalnego przepływu.
- Trenerów wykorzystać do oznaczania: użyteczny drill, nietrafna diagnoza, brakujący kontekst, niemożliwe odtworzenie. Powstaje materiał do ulepszania reguł.
- Sprawdzać płatność za faktyczny pakiet i doświadczenie treningu, nie tylko deklarację „fajny pomysł”. Pierwszą ofertą może być jednorazowa paczka zamiast abonamentu.
- Pomocnicze punkty odniesienia pilota: 20 testerów, połowa uruchamia pierwszy trening, 30% wraca do kolejnej sesji i 5 niezależnych osób płaci docelową cenę. Nie są to zatwierdzone progi go/no-go ani benchmarki rynku. Decyzję o skalowaniu i komercyjnym uruchomieniu podejmuje właściciel na podstawie potwierdzonego treningu, rzeczywistych płatności, kosztów i potrzebnego wsparcia; nie blokuje to implementacji BE/UI.
- W pilocie potwierdzać uruchomienie treningu obserwacją lub dobrowolnym potwierdzeniem; nie uznawać pobrania pliku za wykonanie ćwiczenia.
- Hipotezy cennika: Free z 1 albo 3 pełnymi analizami tygodniowo; Pro około 19-29 zł z uczciwym limitem, np. 40 analiz miesięcznie, historią, zapisanymi zestawami i kolejką powtórek. To propozycje do eksperymentu, nie zatwierdzone limity produktu.
- Nie uzależniać pierwszego pełnego doświadczenia z automatycznym ustawieniem botów od płatności. Darmowa próba musi pozwolić ocenić główną wartość.
- Jeśli gracz nie wraca do treningu, dodatkowy dashboard, LLM czy panel drużyny nie rozwiążą problemu.

## Minimalna eksploatacja, dane i uprawnienia

- Prywatne pliki, krótkotrwałe autoryzowane linki i kontrola dostępu do każdego raportu.
- Podpisane uploady z egzekwowanym limitem, kontrolą ukończenia i weryfikacją faktycznego rozmiaru. Sama deklaracja rozmiaru lub rozszerzenie `.dem` nie wystarczy.
- Walidacja formatu, limit rozmiaru i zasobów parsera. Na początek bez archiwów i pobierania dowolnych URL-i.
- Domyślnie nie przetwarzać voice ani chatu. SteamID i pseudonimy traktować jako potencjalne dane osobowe; wyjaśnić cel, retencję, usunięcie i uprawnienie do przesyłania dem. Nie dodawać zbiorczych publicznych profili bez osobnego uzasadnienia.
- Jasne zasady usuwania dem i wyników, także kopii zapasowych. Brak opt-in na trenowanie modeli z przesłanych danych nie może oznaczać domyślnej zgody.
- Minimalne logi operacyjne bez treści dema, sekretów i pełnych payloadów. Monitorować błędy parsowania/eksportu, wiek zadań, RAM, miejsce i koszt na zakończoną analizę.
- Kopia bazy poza VPS oraz sprawdzony proces odtworzenia. Surowe, krótkotrwałe dema nie wymagają kosztownego backupu.
- Rezerwacja limitu przy przyjęciu zadania i zwolnienie przy błędzie systemowym; ponowienie nie może naliczać drugiego użycia.
- Sprawdzić warunki Valve, dostawców integracji i płatności. Prawo użycia parsera nie zastępuje zgody na komercyjne korzystanie z usług partnera.

## Todos i zależności

Statusy odnoszą się do rzeczywistego wykonania, nie do samego istnienia planu.
Zadania bez zależności mogą postępować niezależnie; kolejność w tabeli nie dodaje
ukrytych zależności.

| Zadanie | Status | Pozostały zakres / warunek odbioru | Zależności |
|---|---|---|---|
| `bootstrap-cli` | Gotowe | Fundament, kontrakt, walidator, testy, CI i Docker są opisane powyżej | Brak |
| `benchmark-demo-pipeline` | Częściowo gotowe | Kod i pomiary lokalne gotowe; pozostały ręczne referencje/ocena trenera, przypadki z docelowych dem i benchmark na docelowej klasie VPS wraz z doborem limitów | `bootstrap-cli`; niezależne od eksportera |
| `build-training-exporter` | Nierozpoczęte; następny krok BE | Jeden eksporter Yprac na zaakceptowanych założeniach: pozycje, kąty, broń, automatyczny bot, jedno wklejenie, walidacja i regresja; jawny status „niezweryfikowane w grze” | `bootstrap-cli`; bez G1 |
| `assemble-training-packs` | Nierozpoczęte; etap BE | Wybór/odrzucanie sytuacji, paczka osobnych scenariuszy, manifest zgodności i instrukcje; logika współdzielona z CLI i backendem | `build-training-exporter` |
| `define-saas-policies` | Nierozpoczęte; etap BE | Wybrać jeden storage, auth, limity, retencję i budżety zasobów dla minimalnej aplikacji; płatności nie blokują prac | `bootstrap-cli` |
| `build-minimal-web` | Nierozpoczęte; backend przed UI | Django, PostgreSQL, prywatny upload, kontrola dostępu, Django-Q2 ORM, idempotencja, rezerwacje i izolowany worker; testy backendu | `define-saas-policies` |
| `complete-training-backend` | Nierozpoczęte; G2 | Połączyć skład i wybór gracza, analizę, raport, wybór sytuacji, paczki oraz autoryzowany eksport w backendzie; testy przepływu bez uruchamiania gry | `build-minimal-web`, `assemble-training-packs` |
| `build-training-ui` | Nierozpoczęte; po BE | Szablony Django, opcjonalnie HTMX: upload, status, wybór gracza, raport, selekcja scenariuszy, kopiowanie całego ustawienia jednym przyciskiem, obsługa błędów | `complete-training-backend` |
| `wire-personal-training` | Nierozpoczęte; G3 | Połączyć UI z backendem, bezpiecznymi paczkami i deklarowanymi ocenami/powtórkami; automatyczne testy aplikacji | `build-training-ui` |
| `add-operations-and-billing` | Po aplikacji, przed odbiorem | Compose/TLS, retencja i usuwanie, backup/odtworzenie, monitoring i limity zasobów; automatyczny abonament nadal tylko po osobnej decyzji | `wire-personal-training` |
| `verify-end-to-end-pilot` | Końcowy etap aplikacyjny | Test upload → raport → paczka → kopiowanie, błędy/retry/limity, uprawnienia, usuwanie, odtworzenie bazy i koszty; bez deklarowania wyniku w grze | `wire-personal-training`, `add-operations-and-billing` |
| `prove-scenario-import` | Odłożone na końcowy odbiór; G1 otwarte | Po BE i UI wykonać próbę jednej i 10 sytuacji w CS2/Yprac: indeks/gotowość bota, XYZ, oczy, broń, mapa, restart i jedno wklejenie; poprawić wykryte problemy; G1 i końcowy G4 | `verify-end-to-end-pilot` |
| `validate-paid-training` | Po końcowym odbiorze | Prywatny pilot: potwierdzone treningi, powroty, płatności, opinie i koszt obsługi; liczby pomocnicze nie są sztywnymi progami | `prove-scenario-import`, `benchmark-demo-pipeline` |
| `approve-saas` | Decyzja o uruchomieniu/skalowaniu, nie o rozpoczęciu kodowania | Jawna decyzja właściciela na podstawie treningu, płatności i kosztów | `validate-paid-training` |
| `launch-controlled-saas` | Po końcowym odbiorze i decyzji biznesowej | Zamknięty nabór z limitami, zweryfikowaną integracją i procedurą wyłączenia wadliwego eksportu | `approve-saas` |

Bieżące MVP obejmuje backend i UI, następnie końcowy odbiór w grze.
CLI pozostaje narzędziem deweloperskim i alternatywnym sposobem użycia
wspólnej logiki. Oceny i prosta kolejka powtórek nie są jeszcze zaimplementowane.

### Bramki przejścia

| Bramka | Wymagany dowód | Obecny stan |
|---|---|---|
| G2: backend | Eksporter, paczki, upload, wybór gracza, analiza i prywatne wyniki połączone; automatyczne testy BE i jawny status zgodności | Parser/analiza gotowe; reszta do implementacji bez czekania na G1 |
| G3: UI i aplikacja | Przepływ od uploadu do kopiowania komend, wybór/odrzucanie sytuacji, deklarowane oceny/powtórki i testy UI | Do wykonania po BE; nie wymaga wcześniejszych płatności ani próby w grze |
| G1: integracja w grze — po G2/G3 | Jedno wklejenie automatycznie ustawia i powtarza 10 sytuacji w CS2/Yprac; pozycje, oczy, broń i mapa zgodne z protokołem | Odłożone na koniec; poprawność komend przyjęta roboczo, brak dowodu runtime |
| G4: końcowy odbiór MVP | G2, G3, aplikacyjne E2E i pozytywne G1; sprawdzone błędy/retry, limity, uprawnienia, retencja, odtworzenie bazy i zasoby | Do wykonania po BE/UI; przed deklarowaniem zweryfikowanego treningu |

Historyczne numery G1–G4 zachowano dla odnośników. Aktualna kolejność to
G2 → G3 → końcowe próby G1 → G4. Płatny pilot i decyzja o skalowaniu
są osobnymi zadaniami po odbiorze, nie wcześniejszą bramką implementacji.

Nie planować odrębnych implementacji trzech integracji ani panelu drużynowego, dopóki pierwszy przepływ nie spełnia kryteriów.

## Źródła

- Wybrany cel configu: Yprac Hub by Yesber, Workshop `3070715607`: https://steamcommunity.com/sharedfiles/filedetails/?id=3070715607
- Uruchamianie Hub, klient i wymagania: https://yprac.com/guides/cs2-workshop-maps-guide
- Awpy: https://awpy.readthedocs.io/en/latest/ oraz https://github.com/pnxenopoulos/awpy
- Awpy FAQ: https://awpy.readthedocs.io/en/latest/faq.html
- Ograniczenia widoczności: https://awpy.readthedocs.io/en/latest/visibility.html
- Dane map i oddzielne prawa do assetów: https://github.com/pnxenopoulos/awpy-data#licensing
- Alternatywny parser i ograniczony zakres jego benchmarku: https://github.com/LaihoE/demoparser
- Yprac: https://yprac.com/guides/cs2-chat-commands-guide — szczegóły komend odczytane również z treści HTML rozwijanych sekcji.
- Yprac i Workshop: https://yprac.com/guides/cs2-workshop-maps-guide
- Instalacja Yprac CS2: https://yprac.com/guides/aim-training-cs2-practice-maps
- Bieżący poradnik instalacji Yprac CS2: https://yprac.com/aim-training-cs2-practice-maps
- Publiczne wydania klienta (nie specyfikacja API): https://github.com/ypracapp/ypracapp-releases
- Wydanie wskazane przez API latest podczas badania: https://github.com/ypracapp/ypracapp-releases/releases/tag/v2.6.8
- Refrag Creator Studio: https://wiki.refrag.gg/en/creator-studio — szczegóły odczytane z treści HTML artykułu.
- Grindhouse: https://grindhouse.online/ — dostęp do strony niezweryfikowany z powodu HTTP 401.
- Django-Q2, broker ORM i semantyka ponowień: https://django-q2.readthedocs.io/en/master/brokers.html
- Cennik R2: https://developers.cloudflare.com/r2/pricing/
- Alternatywa serwerowa: https://docs.cssharp.dev/docs/guides/hello-world-plugin.html
- Składnia `setpos_player` przytoczona przez użytkownika z Valve Developer Community; odczyt podczas aktualizacji blokowany przez Anubis, bez nowej niezależnej weryfikacji treści: https://developer.valvesoftware.com/wiki/Getpos#setpos_player
- Analiza konkurencji: https://leetify.com/, https://scope.gg/, https://refrag.gg/, https://yprac.com/

## Decyzja architektoniczna w jednym zdaniu

Jeden Pythonowy monolit Django z workerem, jedna mapa i jedna integracja Yprac:
najpierw backend na zaakceptowanych założeniach komend, potem UI, a na końcu
próby w CS2/Yprac i poprawki przed udostępnieniem zweryfikowanego treningu.
