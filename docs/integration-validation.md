# G1: protokół potwierdzenia importu scenariuszy

Status: **niezweryfikowane**. Dokument jest procedurą, nie dowodem integracji.
Bieżący cel MVP to
[Yprac Hub by Yesber, Workshop ID `3070715607`](https://steamcommunity.com/sharedfiles/filedetails/?id=3070715607),
z backendem i UI aplikacji, bez własnego serwera/pluginu gry. Wynikiem ma być
jedno wklejenie do konsoli; plik CFG jest opcjonalny. Nie zaliczamy ręcznego
ustawiania botów. Ten cel zastępuje wcześniejszą próbę
integracji wyłącznie ze zwykłą lokalną sesją CS2.

Wymagane jest samodzielne rozpoznanie bota, ustawienie XYZ i kierunku patrzenia
obu uczestników oraz ponowienie. Użytkownik nie ma podawać indeksu bota.
Do potwierdzenia tej ścieżki kod dostarcza wyłącznie parser i analizę do JSON,
nie eksporter ani obsługę Yprac.

**Aktualna kolejność:** backend → UI → próby w grze na końcu. Poprawność
komend i mechanizmu importu jest zaakceptowanym założeniem implementacyjnym,
nie uzyskanym dowodem runtime. G1 nie blokuje eksportera ani aplikacji;
niniejszy protokół służy końcowemu odbiorowi po ich zbudowaniu. Testy kodu,
uprawnień i przepływu aplikacji pozostają wymagane podczas implementacji.

## Fakty i otwarte pytania o Yprac

Workshop wskazuje **Hub**, nie potwierdzoną kopię Mirage. Oficjalny
[poradnik Workshop](https://yprac.com/guides/cs2-workshop-maps-guide) opisuje
rejestrację do CS2 Beta, klient towarzyszący Yprac, parametr `-condebug`,
uruchomienie Hub i wybór wspieranej mapy przez chat. Przykład `cache` nie dowodzi
obsługi Mirage. Osobny poradnik komend podaje jednak `map de_mirage`, `mirage`
oraz `mode sandbox`. Potwierdza to udokumentowaną składnię, nie dostępność
konkretnej rewizji Mirage, jej geometrię ani działanie Sandbox na zwykłym koncie.

[Poradnik komend Yprac](https://yprac.com/guides/cs2-chat-commands-guide)
opisuje polecenia chatu obsługiwane z klientem, bez prefiksu `/` lub `!`.
`help` ma pokazywać aktualną listę, a `maps [prefix]` zainstalowane mapy.
Rozwijane sekcje HTML zawierają szczegóły niewidoczne w uproszczonym tekście
strony. Udokumentowane punkty zaczepienia:

| Polecenie | Udokumentowane działanie | Czego to nie dowodzi |
|---|---|---|
| `place [1-5]` | Stawia bota na bieżącej pozycji gracza, z wyborem slotu | Importu dowolnego XYZ albo odtworzenia kierunku oczu bota |
| `savepos [slot]` | Zapisuje bieżącą pozycję i kąt w nazwanym slocie | Możliwości utworzenia slotu bezpośrednio z danych dema |
| `loadpos [slot]` | Przywraca zapisany slot; `setpos` jest aliasem | Chatowe `setpos` nie oznacza natywnej komendy przyjmującej XYZ |
| `swap [1-5]` | Zamienia pozycje gracza i bota | Odtworzenia obu orientacji, broni i synchroniczności całego importu |
| `weapon <name>` | Zmienia broń gracza | Pełnego mapowania identyfikatorów broni z dema i obsługi obu stron |
| `botweapon <weaponname>` | Zmienia broń wszystkich botów | Niezależnego wyposażenia wielu botów; MVP używa jednego aktywnego bota |
| `restart` | Resetuje bieżącą trasę; aliasy `reset`, `r` | Zachowania i odtworzenia niestandardowego układu Sandbox |
| `reload` | Przeładowuje mapę i sesję; aliasy `restartmap`, `retry` | Zachowania slotów i scenariuszy po przeładowaniu |

### Klient, dostęp i granice badania publicznego

[Poradnik instalacji](https://yprac.com/aim-training-cs2-practice-maps) opisuje
klienta, `-condebug` oraz konsolowe uruchomienie
`map_workshop 3070715607 _yprac`. To komenda wejścia do Hub, nie import scenariusza.
Strona oferuje klienta Windows 10/11 i odsyła do instalatora z wydania v2.0.1.
Podczas badania 2026-10-27 API GitHub wskazało jako najnowsze
[wydanie v2.6.8](https://github.com/ypracapp/ypracapp-releases/releases/tag/v2.6.8),
z instalatorem EXE, blockmap i `latest.yml`. Rozbieżność odnośnika instalacyjnego
nie dowodzi zgodności żadnej z tych wersji z planowanym importem.
Wersję faktycznie zainstalowanego klienta trzeba odczytać przed próbą.

Główny katalog [repozytorium wydań](https://github.com/ypracapp/ypracapp-releases)
zawierał tylko README z nazwą repozytorium, bez specyfikacji API/importu.
Nie pobierano ani nie uruchamiano instalatora i nie przejrzano plików mapy.
Odczyt stron Hub i [kolekcji Workshop](https://steamcommunity.com/workshop/filedetails/?id=740795413)
nie dostarczył identyfikatora ani rewizji docelowego Mirage.
Poradniki oraz dostępny odczyt strony premium nie rozstrzygnęły
darmowego/płatnego dostępu do tej konkretnej ścieżki ani warunków jej
komercyjnej integracji.

W przejrzanych publicznych źródłach nie znaleziono specyfikacji importu
dowolnych XYZ i kątów obu stron, publicznego API scenariuszy ani potwierdzonego
mostu konsola → klient → Sandbox z sygnałem zakończenia operacji.
To **brak potwierdzenia**, nie dowód braku takich możliwości. Nie wywodzić
interfejsu z nazw plików, aliasów ani ograniczeń vanilla CS2. Dalszym źródłem
może być publiczna specyfikacja wskazana przez autora lub legalnie udostępnione
skrypty mapy; nie zakładać, że kod klienta jest dostępny w repozytorium wydań.

### Macierz zdolności i blokad

„Udokumentowane” oznacza opis źródła, nie wynik próby. Każdy wiersz wymaga
potwierdzenia runtime; brak testera obecnie blokuje końcowe G1.

| Wymaganie | Publiczny dowód | Status / brakujące potwierdzenie | Wymagany dowód w grze |
|---|---|---|---|
| Wejście do Hub i klient | Poradniki instalacji i Workshop; wydania klienta | Udokumentowane wymagania; dostęp i faktyczne wersje niepotwierdzone | Czysta instalacja na zwykłym koncie, wersje i uprawnienia |
| Mirage i Sandbox | `map de_mirage`/`mirage`, `mode sandbox` w poradniku komend | Udokumentowana składnia; mapa, rewizja i zgodność geometrii niepotwierdzone | Identyfikacja mapy oraz porównanie punktów referencyjnych z mapą dema |
| XYZ i orientacja gracza z dokumentu | `savepos`/`loadpos` zapisują i przywracają bieżący stan | Brak specyfikacji wprowadzania zewnętrznych XYZ i kątów | Import referencji bez ręcznego odwiedzania pozycji i odczyt XYZ/pitch/yaw |
| Automatyczny bot i jego XYZ | `place [1-5]`, `swap [1-5]` | Udokumentowane sloty; brak pełnego importu i gwarancji stabilnej obsługi bota | Automatyczny spawn/wybór bez indeksu encji podawanego przez gracza; pomiar pozycji |
| Kierunek oczu bota | Opis `place`/`swap` dotyczy pozycji | Brak potwierdzenia ustawiania pitch/yaw oczu | Odczyt kierunku oczu po imporcie i restarcie, nie tylko orientacji modelu |
| Broń i przeciwne strony | `weapon`, `botweapon` w poradniku; strony w kontrakcie v1 | Broń udokumentowana; mapowanie i strony niezweryfikowane | Odczyt broni obu stron i potwierdzenie przeciwnej strony bota |
| Deterministyczny import z konsoli lub natywny format | Brak specyfikacji w przejrzanych źródłach | Blokada interfejsu i kolejności wykonania | Wspierana sekwencja z potwierdzeniem zakończenia; bez zgadywanych opóźnień |
| Restart i powtórzenie | `restart` resetuje trasę, `reload` mapę | Niepotwierdzona semantyka dla własnego układu Sandbox | Ponowne odtworzenie i pomiary po restarcie każdej sytuacji |
| Pomiar i tolerancje | Poradniki nie ustalają protokołu walidacji integracji | Metoda odczytu i progi nieuzgodnione | Mierzalne wartości obu stron i progi przyjęte przed próbą |

### Pytania do autora Yprac

Pytania do przekazania przez właściciela projektu; nie wysłano wiadomości
w jego imieniu:

1. Czy CS2 Sandbox wspiera import zewnętrznych scenariuszy: XYZ, pitch/yaw,
   strony i broń gracza oraz jednego automatycznie wybranego bota?
   Gdzie jest publiczna specyfikacja, przykład i wersjonowanie interfejsu?
2. Czy istnieje wspierany import z konsoli albo natywny format bez własnego
   klienta/pluginu? Jak potwierdzić zakończenie operacji i zapewnić kolejność?
3. Czy `place`/`swap` przenoszą kierunek oczu bota, czy tylko pozycję/model?
   Jak odczytać XYZ i kąty oczu obu uczestników bez ręcznego wskazywania encji?
4. Jaka mapa Mirage i rewizja działają przez Hub `3070715607` w Sandbox?
   Czy zachowują współrzędne i geometrię standardowego `de_mirage`?
5. Jak odtwarzać własny układ po `restart` i po przeładowaniu mapy?
   Czy sloty są trwałe i czy można je utworzyć z danych zewnętrznych?
6. Jaki klient, system, uprawnienia i poziom dostępu są wymagane?
   Czy generowanie paczek dla użytkowników, także w produkcie płatnym,
   jest dozwolone i na jakich warunkach?

## Rozpoznanie przed próbą w grze

1. Ustalić drogę od Hub `3070715607` do wspieranego Mirage i trybu Sandbox.
   Zanotować identyfikator rzeczywistej mapy, plik/rewizję i warunki dostępu.
   Jeśli nie ma zgodnego Mirage, zatrzymać ten wariant; nie zmieniać mapy
   analizatora ani celu eksportu bez osobnej decyzji.
2. Sprawdzić wymagany klient, jego wersję, `-condebug`, rejestrację i dostęp
   darmowy/premium oraz warunki komercyjnego użycia. Nie dodawać własnego klienta,
   serwera ani pluginu jako ukrytego wymagania.
3. Zbadać wspierany import lub interfejs skryptowy: dokumentację, legalnie dostępne
   pliki mapy i odpowiedź autora, jeśli potrzebna. Potwierdzić możliwość podania
   XYZ, pitch/yaw i broni obu stron, a nie tylko importu ogólnych ustawień.
4. Oddzielić polecenia chatu od konsoli. Sprawdzić, czy istnieje wspierany most
   i deterministyczne wykonanie; nie zakładać, że `say` lub średniki zapewniają
   zakończenie działania klienta przed następną komendą.
5. Ustalić automatyczny wybór bota. Slot Yprac wybierany przez eksporter może
   być użyteczny, ale nie jest dowodem poprawnej obsługi encji i orientacji.
   Użytkownik nie może ręcznie szukać indeksu gracza ani ustawiać bota.

## Przygotowanie w grze

Osoba z dostępem do CS2 i zwykłego konta:

1. Subskrybuje wskazany Hub, spełnia potwierdzone wymagania Yprac, uruchamia
   właściwą wersję Mirage i Sandbox. Nie używa matchmakingu. Sprawdza uprawnienia
   oraz ewentualne wymaganie `sv_cheats 1` w tym konkretnym środowisku.
2. Potwierdza dostępność, składnię i działanie interfejsu w tej wersji gry/Yprac,
   automatyczne wskazanie jednego bota oraz kierunek jego oczu (nie tylko modelu).
   Zapisuje źródło ustaleń. Nie zakłada, że kolejność spawn/teleport jest synchroniczna.
3. Zapisuje build CS2, wersję klienta Yprac, rewizję Hub, identyfikator/rewizję
   rzeczywistej mapy treningowej i tryb. Porównuje geometrię i układ współrzędnych
   z mapą źródłową dema; wspólna nazwa Mirage nie wystarczy.
4. Przed próbą ustala mierzalne tolerancje XYZ i kątów oraz metodę ich odczytu
   w grze. Brak możliwości pomiaru zapisuje jako blokadę, nie wynik pozytywny.

### Ustalenie pomiarów przed startem

Nie nadawać arbitralnych progów po obejrzeniu wyników. Przed pierwszą próbą
zapisać tolerancję odległości XYZ w jednostkach świata, pitch i yaw w stopniach,
dokładność metody odczytu oraz chwilę pomiaru: po zakończeniu importu, zanim
gracz lub bot zacznie się poruszać. Ustalić, czy odczyt XYZ oznacza origin
uczestnika, czy punkt oczu; nie porównywać różnych punktów bez uzasadnionej,
zmierzonej konwersji. Kierunek oczu bota musi mieć niezależny od modelu odczyt.

Błąd pozycji to odległość euklidesowa od referencyjnego XYZ. Błąd pitch
to wartość bezwzględna różnicy, a błąd yaw to najmniejsza różnica kołowa
w zakresie 0–180°, aby przejście przez -180°/180° nie dawało fałszywego błędu.
Broń i strona wymagają zgodności, nie tolerancji liczbowej.
Roll w raporcie analizy jest zerem z oznaczeniem `roll_not_recorded`;
nie przedstawiać go jako odtworzonego pomiaru z dema.
Jeśli scenariusz ma `opponent_aim_inferred_toward_player`, brakujący pitch/yaw
przeciwnika wyliczono ku pozycji gracza, zakładając jednakową wysokość oczu
stojących uczestników. Zapisać to w referencji jako przybliżenie, a nie odczyt
z dema. Nadal trzeba zmierzyć, czy Yprac ustawił oczy bota zgodnie z tą
referencją; samo wyliczenie kąta nie usuwa blokady interfejsu.

Referencje muszą pochodzić ze zweryfikowanej geometrii docelowego Mirage;
syntetyczny plik testowy repozytorium nie jest referencją gry. Dla dowodu
zgodności mapy sprawdzić punkty w rozproszonych częściach mapy i na różnych
wysokościach, ich układ współrzędnych oraz otaczającą geometrię.
Sama etykieta `de_mirage` lub `unverified-demo-build-*` nie wystarczy.

## Jedna sytuacja

Przygotować referencję XYZ, kątów i broni gracza oraz jednego bota.
Uruchomić scenariusz przez ustalony interfejs Yprac na koncie zwykłego użytkownika,
preferując komendy do skopiowania do konsoli.
Porównać obie pozycje, orientację i broń, zrestartować i powtórzyć ćwiczenie.
Sprawdzić kolejność wykonania bez niepotwierdzonego `wait`, zgadywanych opóźnień
i masowego wysyłania komend chatowych.

Przed wykonaniem wskazać konkretny, wspierany mechanizm resetu dla tego
scenariusza. Udokumentowane `restart` i `reload` nie są zamienne. Zapisać,
czy powtórka przywraca układ, czy wymaga ponownego importu; ponowny import
musi być automatyczny i nie może wymagać ręcznego odtwarzania slotów.
Jeśli pierwszy przypadek nie przejdzie pomiarów, nie zaliczać go opisowo
i nie rozszerzać próby na 10 sytuacji przed wyjaśnieniem błędu.

Komendy `place`, `savepos`, `loadpos` ani import samych ustawień nie dowodzą
możliwości importu dowolnych XYZ. Uprawnienie w sesji lokalnej nie oznacza
uprawnienia na zewnętrznym serwerze.

## Paczka 10 sytuacji

Powtórzyć próbę dla 10 różnych referencji na tej samej wersji mapy, po jednej
aktywnej sytuacji. Zacząć od czystego środowiska zwykłego użytkownika:
instalacja wymaganego klienta, subskrypcja Hub, wybór mapy/trybu,
wklejenie komend lub potwierdzony import, uruchomienie sytuacji, restart i powtórka.
Nie nadpisywać `autoexec.cfg`, bindów ani ustawień użytkownika.

Zestaw powinien obejmować różne obszary i wysokości, kierunki patrzenia,
strony T/CT oraz więcej niż jeden obsługiwany rodzaj broni, w granicach
statycznego, stojącego pojedynku MVP. Każdy scenariusz musi zaczynać się
bez resztek poprzedniego bota/układu. Dla każdej referencji wykonać import,
pomiar, ćwiczenie, ustalony restart/powtórkę i drugi pomiar.
Osobno zapisać próbę ponownego wejścia po przeładowaniu mapy i wymagany
sposób odtworzenia stanu; nie zakładać trwałości nazwanych slotów.

## Zapis dowodu

W prywatnym katalogu `artifacts/` zapisać:

- źródła i potwierdzony mechanizm importu, wymagania dostępu i wersje;
- Hub `3070715607`, jego rewizję, rzeczywistą mapę treningową, tryb i wersję
  klienta Yprac, osobno od metadanych mapy źródłowego dema;
- referencje oraz pomiary XYZ/kątów/broni dla obu stron, przy pierwszym wykonaniu
  i po restarcie każdej z 10 sytuacji;
- przyjęte tolerancje, wynik każdej próby, błędy i ograniczenia;
- potwierdzenie automatycznego ustawiania botów i powtarzalności na zwykłym koncie.

Dla każdej próby zapisać co najmniej poniższe pola, w tabeli lub równoważnym
pliku danych; nie tworzyć pustego raportu sugerującego pozytywny wynik:

| Zakres | Wymagane pola |
|---|---|
| Środowisko | Build CS2, faktyczna wersja klienta, Hub/rewizja, mapa/rewizja, tryb, poziom dostępu, uprawnienia |
| Referencja | ID scenariusza, źródło/runda/tick jeśli z dema, tożsamość mapy źródłowej, XYZ/pitch/yaw/broń/strona obu uczestników |
| Mechanizm | Źródło specyfikacji, wykonana sekwencja lub import, slot i automatyczna obsługa bota, sposób potwierdzenia zakończenia, sposób resetu |
| Pomiar | ID scenariusza i etap `initial`/`repeat`, metoda odczytu, rzeczywiste XYZ/pitch/yaw/broń/strona obu uczestników |
| Ocena | Błędy pozycji/pitch/yaw osobno dla obu stron, wcześniej ustalone progi, zgodność broni/stron, wynik `pass`/`fail`/`blocked`, przyczyna i ograniczenia |

Status `blocked` dotyczy m.in. braku testera, interfejsu lub odczytu; nie
jest równoważny zaobserwowanemu błędowi mechanizmu. Odnotować, czego jeszcze
nie sprawdzono. Nagrania i logi zbierać tylko w zakresie potrzebnym do dowodu,
bez publikacji danych konta, chatu i pełnego logu `-condebug`.

Zapis dopuszczony do repozytorium nie może zawierać danych testerów ani sekretów.
Nagranie może uzupełniać pomiar, ale nie zastępuje odczytu wartości.

**Go:** wszystkie sytuacje działają w zadeklarowanym środowisku w przyjętych
tolerancjach, bez ręcznego stawiania botów i kruchych wyścigów czasowych.
Wtedy można oznaczyć wcześniej zbudowany eksporter jako zweryfikowany
dla zadeklarowanego środowiska; jego implementacja nie czeka na ten dowód.

**No-go:** brak wspieranego importu, uprawnień, zgodności mapy, pomiarów albo
powtarzalności podczas końcowego odbioru. Nie udostępniać eksportu jako
zweryfikowanego; poprawić implementację, a w razie potrzeby wybrać osobną decyzją jedną alternatywę lub
współpracę z autorem. Własny serwer nie wchodzi automatycznie do zakresu.

## Historia badania zwykłej konsoli CS2

### Nowy trop: `setpos_player` w docelowym Sandbox

Użytkownik przytoczył z
[Valve Developer Community](https://developer.valvesoftware.com/wiki/Getpos#setpos_player)
składnię `setpos_player <player_index> <x> <y> [z optional]`.
Argument oznacza indeks gracza, nie `userid` z `status`. Wcześniejsze
rozważania o resetowaniu licznika User ID nie rozstrzygają tej ścieżki.
Próba odczytu strony 2026-10-27 zwróciła ochronę Anubis zamiast artykułu;
nie przeprowadzono nowej niezależnej weryfikacji treści ani próby w grze.

Hipoteza: w odizolowanej lokalnej sesji po `bot_kick` i dodaniu dokładnie
jednego bota można przewidywalnie wybrać jego indeks, a następnie ustawić XYZ
bez teleportowania gracza. **Indeks `2` nie jest jeszcze gwarancją.**
Sprawdzić przypisanie indeksu, dostępność encji po dodaniu bota i uprawnienia
konkretnie w Yprac Sandbox, od świeżej sesji, po ponownym wykonaniu,
restarcie rundy oraz przeładowaniu mapy. Tester może odczytywać indeks
diagnostycznie; docelowy użytkownik nie ma robić tego ręcznie.

Najbliższym krokiem jest eksporter i backend na zaakceptowanych założeniach,
następnie UI; próba jednej referencji należy do końcowego odbioru.
`bot_kick` i zmiany globalnych ustawień botów ograniczyć do
zadeklarowanej, odizolowanej sesji treningowej. Jedno wklejenie musi zapewnić
gotowość bota przed `setpos_player`, pozycje, kierunki oczu i broń obu stron.
Nie przyjmować, że średniki czekają na zakończenie dołączania/spawnu;
nie nadpisywać bindu `P` ani innych ustawień użytkownika.

Zapis/odczyt pozycji jest zaakceptowanym przez użytkownika założeniem roboczym.
Poradnik podaje `savepos`/`loadpos`; nie potwierdzono dłuższych nazw
`saveposition`/`loadposition` jako aliasów. Założenie nie potwierdza jeszcze
zapisu stanu bota, kierunku jego oczu ani trwałości po przeładowaniu.
Wyniki końcowej próby aplikacji zapisać według protokołu powyżej;
do czasu pomiarów G1 otwarte, bez blokowania BE/UI.

### Pozostałe ustalenia

Poniższe ustalenia są materiałem pomocniczym, nie głównym celem eksportera i nie
dowodzą ani możliwości, ani niemożliwości importu przez Yprac:

- Publiczny dump potwierdza `setpos_exact`, `setang_exact` i `setpos_player`;
  ostatnia wymaga wskazania gracza. `bot_place` stawia bota pod celownikiem,
  nie przyjmuje dowolnego XYZ.
- `ent_setang` i `bot_mimic` nie są dowodem automatycznego rozpoznania bota
  ani odtworzenia jego kąta widzenia.
- `point_teleport` w `DumpSource2/entities/server.fgd` udostępnia
  `TeleportEntity` i `TeleportEntityToCurrentPos`. Nie sprawdzono w grze
  selekcji bota, składni tworzenia encji, kolejności ani kierunku oczu.
  `SetAbsAngles` zmieniające orientację modelu nie wystarcza.

Źródło: [publiczne dumpy CS2](https://github.com/SteamDatabase/GameTracking-CS2/tree/master/DumpSource2),
pliki `commands.txt`, `convars.txt`, `entities/server.fgd`. Nie włączono generatora
tych komend dotychczas. Aktualna decyzja dopuszcza implementację na
założeniach i odkłada dowód runtime na koniec; zmiana celu na vanilla CS2
nadal wymaga osobnej decyzji.
