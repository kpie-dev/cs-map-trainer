# G1: protokół potwierdzenia importu scenariuszy

Status: **niezweryfikowane**. Dokument jest procedurą, nie dowodem integracji.

## Odbiór pakietu Trener

Aktualny cennik to Pro 4,99 USD/mies. i Trener 19,99 USD/mies.; wcześniejsze
wzmianki o 7,99 USD w tym protokole pozostają opisem poprzednich odbiorów.
Oprócz dotychczasowych prób sprawdzić skład 1 i 5 graczy, brak części/wszystkich
zawodników w demie, osobne wybory/eksporty i izolację kont, dostęp do historii
po wygaśnięciu Trenera oraz niezmienność składu po edycji i wznowieniu uploadu.
Statystyki meczowe i Estimated Rating 2.0 porównać z ręcznie policzonymi
zdarzeniami lokalnego uprawnionego dema; nie wymagać zgodności z oficjalnym HLTV.
W Stripe test mode odebrać obie ceny, migrację starego Pro i zmianę pakietu
dokładnie od odnowienia, bez proraty, także po opóźnionych webhookach i braku
płatności. Atrapy Stripe nie potwierdzają tej integracji.

## Aktualny kontrakt kont i uploadu

Weryfikacja i powiązywanie Steam są wyłączone. Obowiązuje konto e-mail/hasło
z potwierdzonym adresem oraz SteamID64 wskazane przy każdym demie. Free
obejmuje 3 analizy na konto w miesiącu UTC, Pro znosi limit liczby na koncie,
a aktywny upload i cleanup blokują kolejne zadanie tego konta, nie SteamID.
Ten sam identyfikator na różnych kontach nie udostępnia raportów.
Ostatni użyty SteamID jest nieweryfikowaną podpowiedzią zapisaną na koncie.
Pomoc przy polu zawiera lokalne ilustracje poglądowe, nie autentyczne screeny.

Przed wdrożeniem zastosować nieodwracalną migrację `0007_account_upload_players`
przy zatrzymanym intake/workerach i po backupie bazy. Odebrać rejestrację/SMTP,
upload z wpisanym SteamID, brak gracza, retry z niezmienionym SteamID,
limity przy zmianie gracza, izolację dwóch kont ze wspólnym SteamID,
modal (klawiatura/mobile), zapis podpowiedzi na innym urządzeniu i billing
bez Steam. Kontrakt API i procedura wdrożenia są w README.

Poniższe zapisy odbiorów i opisów starszych etapów wspominające Steam OpenID,
kwoty na SteamID, callback i minimalizację profili są historyczne; nie stanowią
aktualnych wymagań integracji. Nie wykonujemy już odbioru Steam OpenID/API.
Bieżący cel MVP to
[Yprac Hub by Yesber, Workshop ID `3070715607`](https://steamcommunity.com/sharedfiles/filedetails/?id=3070715607),
z backendem i UI aplikacji, bez własnego serwera/pluginu gry. Wynikiem ma być
jedno wklejenie do konsoli; plik CFG jest opcjonalny. Nie zaliczamy ręcznego
ustawiania botów. Ten cel zastępuje wcześniejszą próbę
integracji wyłącznie ze zwykłą lokalną sesją CS2.

## Aktualny odbiór ścieżki upload → wybór → trening

UI pozostaje po angielsku. Starsze opisy ocen i harmonogramu w zapisach
odbioru poniżej są historyczne, nie opisują bieżącego interfejsu.
Oceny `PracticeReview` pozostają w bazie i są usuwane z raportem/kontem,
lecz nie wpływają na bibliotekę `/practice/`.

Sprawdzić osobno dla Mirage i Dust2:

1. Rzeczywisty procent PUT, etap Verify file podczas `complete`, następnie
   Queued → Processing demo → Ready z serwera. `running` nie ma procentów/ETA.
   Lekki prywatny `/backend/uploads/<id>/status/` zwraca tylko stan i błąd;
   pełny odczyt nadal zwraca raport. Błąd sieci/sesji i limit 10 minut
   zatrzymują polling z jawnym komunikatem i ręcznym wznowieniem.
   Loader pokazuje tylko aktualny etap i spinner; polling co 2,5 s według
   deadline 10 minut. Retry pojawia się wyłącznie po błędzie/przerwie.
   Ponowienie potwierdzenia po udanym PUT nie wysyła dema ponownie.
2. Wszystkie sytuacje początkowo zaznaczone. Jeden checkbox obejmuje całą grupę
   podobnych scenariuszy, nie tylko reprezentanta. Odznaczyć grupę i jednym kliknięciem
   Download training (.zip) otrzymać CFG, TXT, manifest i instrukcję bez nawigacji.
   Bieżące checkboxy mają odpowiadać wszystkim plikom; równoległy zapis w drugiej
   karcie nie może zmienić odpowiedzi pierwszego POST. Open practice także
   zapisuje bieżący wybór. Standardowy formularz działa bez JS.
   Sprawdzić `training-groups.json` i komplet CFG/TXT wszystkich członków.
   Historyczny częściowy wybór musi pozostać dokładny (indeterminate i opis,
   zachowanie/wyczyszczenie bez JS); zaznaczenie grupy dodaje jawnie resztę.
3. Pusty/nieprawidłowy wybór oraz błąd eksportu: brak zapisu sukcesu, brak
   archiwum błędu HTML, zachowane checkboxy; wadliwych sytuacji nie pomijać
   automatycznie. Sprawdzić legacy include/reject i utrzymanie dawnych odrzuceń
   do ponownego zaznaczenia. Eksport ma działać z walidowanego raportu bez
   dema/R2 i bez zaufania do zapisanego pola scripts.
4. Trening: Copy commands w pierwszym widoku 1440 × 900 oraz 390 × 900,
   Previous/Next group oraz przełączanie każdego członka bez oceniania,
   poprawna mapa/lokacje/bronie w jednej linii ze stronami, schowek i ręczny
   fallback, zwinięta lista sytuacji i dane techniczne. Widoczne ostrzeżenie
   lokalnej sesji i `unverified_in_game`. Biblioteka obejmuje również starsze
   niż 100 raportów, niezależnie od ocen; stronicowanie po 20 i prywatność.
5. Zmierzyć 10 syntetycznych sytuacji z jednym ostrzeżeniem celowania:
   zwinięty wiersz ≤160 px przy 1440 px, ≤220 px przy 390 px. Bez obcinania
   treści; sprawdzić długie i nieznane etykiety, stare raporty bez lokacji
   i brak lokacji jednego gracza. Przyciski eksportu dostępne bez przewijania
   całej listy. Fokus nie może znikać pod paskiem akcji; cele minimum 44 × 44,
   obsługa klawiaturą, reduced motion i brak poziomego przepełnienia.
6. Konserwatywne grupowanie z README: zgodność każdej pary obu pozycji
   (3D ≤192, Z ≤64), kątów (yaw ≤30°, pitch ≤20°), mapy/stron/klas broni/kontekstu.
   Wspólny callout nie może połączyć odległych scenariuszy. Osobno sprawdzić
   AK/M4 w tej samej klasie, AWP, estymowane kąty, brak lokacji i nieznaną broń.
   Priorytet: własny rifle/sniper vs pistol/SMG, potem pełne bronie obu,
   neutralne zestawy, na końcu własny pistol/SMG. To preferencja treningowa,
   nie pomiar błędów/umiejętności ani zapisanej ekonomii. Statystyki raportu
   pozostają odrębne. Biblioteka pokazuje jeden wiersz na wybraną grupę.

Testy syntetyczne UI/BE nie potwierdzają działania w CS2 ani rzeczywistego
R2. G1 poniżej pozostaje osobnym odbiorem komend i CFG na obu mapach;
bez dostępu do gry wynik jest blocked, nie pass.

Historyczny lokalny odbiór uproszczonego UI sprzed grup treningowych, na izolowanej bazie i syntetycznych raportach
Mirage/Dust2: przy 10 sytuacjach z jednym ostrzeżeniem zwinięte wiersze mają
około 140 px przy szerokości 1440 px i 135 px przy 390 px. Dolna krawędź
przycisku kopiowania znajduje się odpowiednio około 399 i 439 px od góry
widoku; brak poziomego przepełnienia w tej próbce. Potwierdzono zapis wyboru
przez Open practice, ZIP z wybraną sytuacją i CFG bez zmiany strony, pobranie
przez formularz bez JS, zachowanie checkboxów po HTTP 503 zamiast archiwum
błędu, ręczny fallback schowka oraz zatrzymanie pollingu po nieznanym stanie.
Regresja webowa: 451 testów zaliczonych; po końcowych zmianach ponownie 297
testów UI/eksportu. Lint, format i brak nowych migracji potwierdzone.
Nie jest to odbiór rzeczywistego R2 ani wykonania komend w CS2.

### Odbiór grup treningowych i bieżącego loadera — 2026-10-30

Na osobnym PostgreSQL 16 zaliczono **572 testy** UI, wyboru/eksportu, uploadu,
grupowania, CLI i paczek; lint/format całego `src`/`tests` oraz brak migracji.
Python Playwright/Chromium, osobne konto i serwer 8765, Mirage i Dust2,
1440 × 900 oraz 390 × 900: 10 zachowanych scenariuszy daje 4 treningi
z 3/3/2/2 członkami. Wiersze mają 140 px na desktopie, 135–158 px na telefonie;
dolna krawędź Copy CS2 commands odpowiednio 396/436 px. Bez poziomego
przepełnienia i wyjątków JS. Uczestnicy mają spójny zapis
`CT / awp / A Site → T / tec9 / T Spawn` z wyróżnionymi lokacjami.

Potwierdzono komplet 10 członków/4 grup w ZIP, 7 członków/3 grup po odznaczeniu,
wszystkie CFG i addytywny `training-groups.json`, nawigację grup/członków,
bibliotekę bez duplikatów, HTTP 503 bez utraty checkboxów, częściowy wybór
indeterminate oraz pobranie bez JS (zachowanie 1 członka albo jawne rozszerzenie
do 3). Loader pokazuje tylko bieżący etap; zmierzone odstępy 2,503–2,504 s.
Sprawdzono retry dopiero po błędzie, reduced motion, deadline 10 minut przed
następnym żądaniem i przerwanie wiszącego żądania na deadline. Przy symulowanej
awarii `complete` ponowienie wykonało **PUT raz, complete dwa razy**.
Próby transportu/statusu były kontrolowanymi odpowiedziami przeglądarkowymi,
nie odbiorem rzeczywistego R2 ani nowym parsowaniem. Nie zmieniono parsera,
limitu zachowanych scenariuszy, historii ocen ani statusu `unverified_in_game`.

## Rozszerzenie zakresu: odbiór siedmiu map

Plan obejmuje **Cache, Dust2, Mirage, Inferno, Nuke, Ancient i Anubis**
(`de_cache`, `de_dust2`, `de_mirage`, `de_inferno`, `de_nuke`, `de_ancient`,
`de_anubis`). Parser, CLI, web i eksperymentalny eksporter obsługują wszystkie siedem
map przez wspólny katalog `maps.py`. Manifest jednej mapy używa
`yprac_hub_<map>_sandbox`, mieszany `yprac_hub_multi_map_sandbox`; każdy plik
zachowuje własną mapę/build/rewizję. Raport v3 (odczyt v2), scenariusze v1,
reguły analizy i status `unverified_in_game` pozostają bez zmian.
Regresja syntetyczna obejmuje siedem map, odrzucanie map poza zakresem,
osobne wysokości Nuke, mapy plików i grup w mieszanym ZIP oraz aliasy lokacji.
Brak lokalnych dem Cache/Inferno/Nuke/Ancient/Anubis pozostawia ich rzeczywisty
parser i worker do odbioru. Poniższe historyczne przykłady Mirage/Dust2 nie są
dowodem działania na rzeczywistych demach pozostałych map ani dostępności Yprac.

Odbiór aplikacyjny rozszerzenia: 3141 testów zaliczonych na osobnym PostgreSQL,
2 opt-in pominięte; test rzeczywistego lokalnego dema Dust2 uruchomiony osobno
i zaliczony, z porównaniem XYZ/kątów/lokacji oraz procesem potomnym workera.
Lint, format, build sdist/wheel, Django check i kontrola migracji przeszły.
Playwright na osobnym serwerze i syntetycznym koncie: 34 widoki przy
1440 × 900 i 390 × 900, home/historia/biblioteka oraz raport i trening dla
każdej mapy. Potwierdzono wybór grupy obejmującej dwóch członków, otwarcie
treningu, pobranie ZIP, dwa CFG, właściwą mapę i integrację manifestu oraz
`unverified_in_game`. Nie było poziomego przepełnienia ani wyjątków JavaScript.
Nie wykonywano rzeczywistego uploadu siedmiu dem ani próby CS2/Yprac.

Dla każdej mapy osobno potwierdzić dostępność CS2/Sandbox w Yprac Hub,
rzeczywistą rewizję i zgodność geometrii ze źródłowym demem. Przeprowadzić
opisaną poniżej próbę jednej, następnie 10 sytuacji oraz pomiary obu stron
przed i po powtórzeniu. Uwzględnić różne wysokości i nakładające się poziomy,
zwłaszcza na Nuke. Nie stosować współrzędnych ani wyników Mirage jako referencji
innej mapy.

Prowadzić macierz dowodów i status `pass`/`fail`/`blocked` osobno dla siedmiu map.
Brak uprawnionego dema blokuje odbiór parsera danej mapy; brak zgodnej mapy
w Yprac lub metody pomiaru blokuje jej odbiór w grze. Nie jest to powód do
blokowania wcześniejszej implementacji BE/UI. Nie podmieniać celu eksportu
na Mirage ani inną integrację i nie nadawać globalnego potwierdzenia po
zaliczeniu tylko jednej mapy. G1/G4 rozszerzonego zakresu wymagają odbioru
wszystkich siedmiu map.

### Etap Dust2 — osobny odbiór

CLI i aplikacja obsługują `de_dust2` przez ten sam pipeline co Mirage.
Raport v2, scenariusze v1 i reguły `damage-window-v3` nie zmieniły się.
Komendy, CFG i ZIP zachowują `unverified_in_game`; manifest Dust2 wskazuje
`yprac_hub_dust2_sandbox`, a mieszany `yprac_hub_multi_map_sandbox`.
Instrukcje przypisują mapę do każdego pliku; przed sytuacją z innej mapy
trzeba zmienić sesję. Obsługa nie potwierdza dostępności Dust2/Sandbox w Hub.

Odbiór aplikacyjny: uprawnione demo Dust2, odczyt mapy/builda z nagłówka,
skład i analiza, porównanie XYZ/kątów z migawkami oraz eksport bez ponownego
parsowania. Osobno sprawdzić prywatny upload/worker, wybór, CFG/ZIP,
etykiety historii/raportu/treningu/powtórek i deklarowane oceny.
Testy z atrapami nie zastępują próby rzeczywistych usług R2/Steam.

Odbiór w grze: ustalić rzeczywistą mapę i rewizję Dust2 w Yprac, dostęp
do Sandbox, zgodność punktów referencyjnych, indeksy i gotowość bota,
XYZ/kąty oczu, strony i broń obu uczestników. Przeprowadzić próbę jednej,
następnie 10 sytuacji oraz powtórzenie z pomiarami. Status Dust2 pozostaje
niezweryfikowany do wykonania tej procedury; wyniki Mirage nie wystarczą.

Wykonano lokalnie: **875 testów zaliczonych, 2 opt-in pominięte** w regresji
na osobnym PostgreSQL; osobno zaliczono opt-in rzeczywistego dema Dust2.
Potwierdzono nagłówek `de_dust2` / build `10924`, zgodność XYZ/kątów,
generowanie paczki i odczyt raportu rzeczywistego procesu potomnego workera.
Usunięto wykryty błąd walidacji komórek grup po serializacji JSON; nadal
odrzucane są np. ciągi znaków zamiast liczb. Lint, format, sdist/wheel,
Django checks i brak nowych migracji potwierdzone. Nie wykonano próby
komend Dust2 w grze ani rzeczywistych usług R2/Steam.

Sprawdzono także UI w Playwright na przebudowanym lokalnym obrazie Compose,
z osobnym syntetycznym kontem i raportami Dust2/Mirage. Dla szerokości
1280 i 390 px: strona główna, historia, oba raporty i treningi, kolejka
nadchodzących powtórek oraz raport oczekujący zwracają HTTP 200, pokazują
właściwe etykiety i nie powodują poziomego przewijania całej strony.
Potwierdzono przejście między sytuacjami, zapis/odrzucenie wyboru po odświeżeniu,
rzeczywiste pobrania CFG/ZIP, zgodność komend z API, mapę i wybór w manifeście,
instrukcję Dust2 oraz zapis oceny „Trudne” w nadchodzących powtórkach.
Nie stwierdzono wyjątków JavaScript. Na lokalnym HTTP `host.docker.internal`
schowek jest niedostępny; przycisk poprawnie zaznacza tekst i podaje instrukcję
ręcznego kopiowania. Przeglądarka zgłasza też ograniczenie COOP dla tego
niezaufanego originu. Test nie obejmuje uploadu dema z przeglądarki do R2,
integracji Steam ani wykonania komend w grze.

Wymagane jest samodzielne rozpoznanie[inwestycje-ai-68d30f13-b195-4b7c-810f-454e34e6e15f.json](../../../Downloads/inwestycje-ai-68d30f13-b195-4b7c-810f-454e34e6e15f.json) bota, ustawienie XYZ i kierunku patrzenia
obu uczestników oraz ponowienie. Użytkownik nie ma podawać indeksu bota.
Kod dostarcza parser, analizę i prototyp eksportera/paczek Yprac; wygenerowanie
komend nie potwierdza tej ścieżki ani działania importu.

**Aktualna kolejność:** backend → UI → próby w grze na końcu. Poprawność
komend i mechanizmu importu jest zaakceptowanym założeniem implementacyjnym,
nie uzyskanym dowodem runtime. G1 nie blokuje eksportera ani aplikacji;
niniejszy protokół służy końcowemu odbiorowi po ich zbudowaniu. Testy kodu,
uprawnień i przepływu aplikacji pozostają wymagane podczas implementacji.

## Osobny odbiór minimalnego backendu

Zaimplementowano fundament Django/PostgreSQL/Django-Q2, publiczną rejestrację
z potwierdzeniem e-mail, połączenie Steam OpenID i prywatny intake R2.
Nie jest to dowód działającej konfiguracji usług: przed udostępnieniem
sprawdzić prawdziwe SMTP, powiązanie Steam oraz kontrakt R2 opisany w README.
Testy backendu korzystają z PostgreSQL i atrap usług; opt-in próba R2
sprawdza podpisany rozmiar, ukończenie, unieważnienie URL i usunięcie.
Nie wykonywano tutaj próby z rzeczywistymi poświadczeniami ani uruchomienia Compose.

Analiza dotyczy tylko SteamID potwierdzonego przez właściciela konta, z limitem
3 przyjętych dem w miesiącu kalendarzowym UTC w Free. Pro kosztuje 7,99 USD/mies.
i nie ogranicza liczby analiz własnego SteamID. Techniczny limit pliku to 1 GiB,
a jedno aktywne zadanie na SteamID i globalna wyłączność parsera pozostają.
Po pierwszej próbie usuwane są obie kopie dema, również po błędzie; brak
automatycznego retry analizy. Sprawdzić usuwanie po awarii/timeout i ponawianie
nieudanego sprzątania niezależnie od workera. Porzucone wejścia wygasają po 24 h.
Regresje obejmują `SIGKILL` workera, dziedziczenie blokady przez nadal żywy
proces i odzyskanie slotu dopiero po jego zakończeniu. Wdrożenie wymaga
wspólnego wolumenu roboczego i zastosowania migracji minimalizującej starsze
profile Steam; callback ogranicza dane przed zapisem allauth, także przy reconnect.
W historii pozostają prywatne raporty, scenariusze i komendy do usunięcia przez
użytkownika/konto. Potwierdzić kontrolę właściciela, brak resetu kwoty przez
nowe konto aplikacji i zachowanie historii bez wejściowego dema.

Backend rozszerzono o zapis wyboru i odrzuceń przy raporcie, prywatny eksport
pojedynczej linii komend/CFG i opcjonalny ZIP generowany na żądanie.
Operacje działają po usunięciu wejścia, bez ponownego parsowania i dostępu do R2.
Wybór jest czyszczony wraz z historią/kontem. Testy obejmują kontrolę właściciela,
CSRF, cudze/usunięte wyniki, nieprawidłowy wybór i nieobsługiwany eksport.
Lokalnie zaliczono 127 testów backendu na PostgreSQL 16 w osobnym kontenerze;
pełna regresja: 421 zaliczonych, 2 pominięte (lokalne demo i prawdziwe R2).
Lint/format, build, Django checks, zastosowanie migracji
`0003_training_selection` i zgodność modeli z migracjami przeszły.
To próba bazy PostgreSQL w Dockerze, nie odbiór obrazu workera Linux/Compose.
Następnie zaimplementowano UI Tactical HUD i deklarowane powtórki opisane poniżej.
G2 nadal wymaga odbioru usług zewnętrznych; G3 odebrano lokalnie na danych
syntetycznych, ale odbiór w docelowym środowisku i G1 pozostają otwarte.
Eksport nadal ma `unverified_in_game`.

## Lokalny odbiór UI i deklarowanych powtórek

Szablony Django obejmują konto/Steam, upload R2, historię/status, raport,
zapamiętany wybór i kopiowanie pełnej linii jednej sytuacji. ZIP/CFG pozostają
opcjonalne. Nie przeniesiono fikcyjnych wyników i funkcji makiet z `design/`.

Model `PracticeReview` (migracja `0004_practicereview`) zapisuje ostatnią
deklarację użytkownika i termin: trudne +1 dzień, wykonane +3 dni, łatwe +7 dni.
Nietrafne wyłącza z powtórek do przywrócenia, bez zmieniania wyboru paczki.
Nowe/do powtórki, nadchodzące i nietrafne są osobnymi filtrami prywatnej kolejki.
Wybór jest respektowany we wszystkich gotowych raportach, nie tylko ostatnich 100.
Usunięcie raportu/konta usuwa też oceny, również przy równoległym zapisie.
Pobranie ani skopiowanie komend nie zapisuje wykonania.

Testy PostgreSQL obejmują terminy kontrolowanym zegarem, przywrócenie,
uprawnienia, CSRF, błędy, brak cache, nieprawidłowy raport, usuwanie i współbieżność.
Próba przeglądarkowa Chromium na lokalnym serwerze i syntetycznym raporcie
obejmuje allauth, zapis wyboru, zgodność pola komend z eksporterem, schowek
i odmowę dostępu, oceny/przywrócenie oraz brak przepełnienia na ekranie 390 px.
Atrapy transportu potwierdzają surowy PUT do R2 bez cookies, zachowanie UUID
przy błędzie transferu i przeładowaniu strony, brak kolejnego PUT po błędzie
potwierdzenia już przesłanego pliku oraz zatrzymanie pollingu po błędzie sieci
i ręczne wznowienie. To nie jest dowód konfiguracji R2, weryfikacji Steam
ani dostarczania SMTP.

Lokalnie zaliczono 187 testów backendu/UI na PostgreSQL 16, łącznie 481 testów
całej aplikacji; pominięto integrację lokalnego dema i prawdziwego R2.
Lint/format, build, Django checks, migracje, zawartość wheel i collectstatic
przeszły. Obraz web Linux zbudowano legacy builderem po timeout BuildKit;
w kontenerze sprawdzono Django checks i dostępność szablonów oraz zebranych
statyków. Nie uruchomiono tym samym pełnego Compose ani workera.

Przed wdrożeniem zastosować migracje, podać `/static/` przez reverse proxy
i wykonać rzeczywiste próby powyższych usług. Terminy i „wykonane” pozostają
deklaracją gracza nawet po udanym odbiorze. Nie wolno używać ich jako dowodu
automatycznego odczytu wyników ani spełnienia poniższego protokołu G1.

## Odbiór modułu Stripe

Zaimplementowano abonament 7,99 USD/mies. bez limitu liczby analiz własnego
SteamID, z darmowymi 3 analizami na miesiąc kalendarzowy UTC. Zmiana kwoty
zastępuje wcześniejszą politykę tygodniową. Migracja: `0005_billing_accounts`.
Podpisane webhooki uzgadniają aktualny stan subskrypcji i opłacony okres
faktury; redirect nie nadaje uprawnień. Błędy i duplikaty nie tworzą kolejnej
sesji ani fałszywego potwierdzenia obsłużonego eventu.

Anulowanie zwykłe jest na koniec opłaconego okresu; nieudane odnowienie
nie przedłuża Pro, a już rozpoczęta analiza nie jest przerywana. Usunięcie
konta najpierw wygasza checkouty i natychmiast anuluje subskrypcje, bez
automatycznego zwrotu; bez potwierdzenia Stripe konto nie jest usuwane.

Regresja PostgreSQL obejmuje podpisy/wygaśnięcie, ponowienia i współbieżność,
nieuporządkowane eventy, okres opłacony, kwotę UTC, brak resetu SteamID,
portal, brak podwójnych checkoutów i anulowanie przy usunięciu konta.
Atrapy API nie potwierdzają działania prawdziwego Stripe.

Zaliczone: 55 testów płatności, 242 backendu/UI i 536 w całej regresji; pominięto
lokalne demo i kontrakt prawdziwego R2. Przeszły migracje, checks, lint i build.
Syntetyczny odbiór przeglądarkowy potwierdza checkout/portal, brak nadania Pro po
redirect, nadanie po podpisanym webhooku, anulowanie/wygaśnięcie, odświeżenie
i mobilny układ. Zewnętrzny Stripe był atrapą; żadnej opłaty nie pobrano.

W skonfigurowanym test mode przejść zakup i dostarczenie webhooka, odnowienie,
nieudaną płatność, anulowanie, wygaśnięcie, usunięcie konta i ponowne uzgodnienie
po niedostarczeniu zdarzenia. Użyć właściwej ceny i portalu zgodnie z README.
Przed live powtórzyć weryfikację konfiguracji kluczy, ceny, webhooka i adresów
powrotu; ustawić okresowe `reconcile_subscriptions` i reakcję na jego błąd.
Nie wykonywano tutaj próby z rzeczywistymi poświadczeniami Stripe ani opłaty live.
To odbiór techniczny płatności, nie pilot biznesowy.

## Lokalny odbiór konfiguracji wdrożeniowej

Dodano produkcyjne rozszerzenie Compose z Caddy, automatycznym TLS i statykami
z obrazu budowanego razem z aplikacją. Tylko proxy publikuje porty; Django
ufa nagłówkowi protokołu dopiero po jawnym włączeniu w webie za proxy.
README zawiera procedurę pierwszego uruchomienia i aktualizacji oraz szablony
systemd do okresowego uzgadniania Stripe, niezależnego od reapera.

W izolowanym lokalnym projekcie Docker uruchomiono PostgreSQL, wszystkie
migracje do `0005_billing_accounts`, web, worker, maintenance i Caddy.
Lokalny CA służył wyłącznie tej próbie: klient weryfikował jego certyfikat,
nie wyłączano walidacji TLS ani nie instalowano CA w systemie użytkownika.
Sprawdzono HTTP → HTTPS, brak pętli przy podszytych `X-Forwarded-*`,
logowanie i CSRF, secure cookies, HSTS bieżącego hosta, ochronę ramek,
odmowę anonimowego dostępu do historii, zgodne hashe CSS/JS i brak
publicznych portów weba/bazy. Powtórzono próbę po restarcie usług,
a podmiana obrazu proxy faktycznie zmieniła serwowany CSS bez starego wolumenu.

Reaper korzystał z jawnej atrapy pustego bucketa R2. Brak konfiguracji R2
wcześniej powodował jawny błąd i restart reapera, nie pozorny sukces.
Nie wykonano analizy prawdziwego dema, awarii parsera ani rzeczywistych
połączeń R2/Steam/SMTP/Stripe. Timer systemd nie był instalowany/uruchamiany.
Zaliczone: 20 ukierunkowanych testów ustawień, logowania, dostępu i CSRF
na PostgreSQL, Ruff, walidacja Compose/Caddy i budowanie obrazów.
Django deploy check pozostawia W005/W021: HSTS całych subdomen i preload
nie są włączane bez odbioru docelowej domeny. Cała regresja nie była powtarzana.

`prepare-deployment` nadal wymaga VPS/domeny, publicznego ACME, instalacji
timera i odbioru po restarcie hosta. Lokalny odbiór nie zamyka G1/G2/G4
ani rzeczywistych integracji; nie zmienia `unverified_in_game`.

## Zaimplementowany prototyp do końcowej próby

Uzupełniająca próba backendu Linux: rzeczywisty upload dema Dust2
(408 650 218 B) do lokalnego S3 Moto przeszedł przez kolejkę i worker do
oczekiwanego `unsupported / unsupported_or_invalid_demo`. Naprawiono przy tym
import Awpy bez `HOME`, ustawiając `AWPY_DATA_DIR` w katalogu uploadu.
Obiekt S3 i katalog roboczy zostały usunięte; źródłowy plik pozostał bez zmian.
248 testów backendu/UI przeszło, w tym regresja procesu bez katalogu domowego.
To odbiór negatywny, bez prawdziwego R2/Steam i bez udanej analizy Mirage;
nie zamyka odbioru workera, G2 ani G1.

CLI `export-scenario` i `build-pack` używa wersji
`yprac-sandbox-prototype-v1`. Paczka zapisuje `unverified_in_game`, źródła
i ograniczenia każdej sytuacji oraz osobną listę założeń i zmian sesji.
Instrukcje użycia są w `../README.md`. Prototyp nie jest wynikiem G1.

Po usunięciu botów i dodaniu jednego przyjmujemy indeks **gracza** `2`
dla `setpos_player`. Użytkownik osobno zaakceptował jako hipotezę indeks
**encji/pawn** `2`, użyty przez `ent_setname cmt_v1_bot 2`.
Nie utożsamiamy indeksów jako faktu; nie ma dynamicznego odczytu encji.
Nazwa wyświetlana bota nie służy jako jego `targetname`.
Eksporter tworzy własny `point_teleport` z referencyjnym XYZ i kątami,
wywołuje `TeleportEntityToCurrentPos cmt_v1_bot` i kolejkuje `Kill`
wyłącznie własnej encji pomocniczej. Przed kolejnym utworzeniem usuwa
pozostałą encję o tej samej nazwie. Nie usuwa wszystkich `point_teleport`
z mapy. Przywraca XYZ/kąty gracza i wysyła `weapon`/`botweapon` przez `say`.

Dump CS2 `DumpSource2/entities/server.fgd` potwierdza `point_teleport`,
`teleport_use_current_angle` i wejście `TeleportEntityToCurrentPos`;
`commands.txt` potwierdza komendy tworzenia/nazywania encji.
To nie dowodzi kierunku oczu, składni całej sekwencji ani synchronizacji.
Rewizja pliku FGD wskazana przy rozpoznaniu:
`70b98b48a2114632e5bf79b07efebcde1a06256c`.
Źródło: [publiczny dump](https://github.com/SteamDatabase/GameTracking-CS2/blob/70b98b48a2114632e5bf79b07efebcde1a06256c/DumpSource2/entities/server.fgd).

Przed zaliczeniem próby sprawdzić osobno oba indeksy od czystej sesji,
po zmianie drużyny, ponownym wykonaniu i restarcie, gotowość po `jointeam`
i dodaniu bota, utworzenie i usunięcie własnej encji oraz kierunek oczu.
Szczególnie sprawdzić kolejność entity I/O i asynchronicznego klienta Yprac:
średniki nie potwierdzają zakończenia poprzedniej operacji. Nie dodano
`wait`, zgadywanych opóźnień ani `bot_mimic`.

Prototyp zmienia globalne ustawienia i wyrzuca istniejące boty; jest tylko
do izolowanej lokalnej sesji jednego człowieka. Nie przywraca poprzednich
wartości ustawień. Pełny wykaz jest w manifeście. Powtórka polega na ponownym
wklejeniu ustawienia; trwałość `savepos`/`loadpos` i semantyka `restart`
nie są wykorzystywane jako potwierdzony mechanizm odtworzenia.

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

1. Dla każdej mapy z uzgodnionej listy ustalić drogę od Hub `3070715607`
   do jej wspieranej wersji i trybu Sandbox.
   Zanotować identyfikator rzeczywistej mapy, plik/rewizję i warunki dostępu.
   Jeśli nie ma zgodnej wersji danej mapy, zatrzymać jej odbiór i zapisać
   `blocked`; nie zastępować mapy źródłowej inną mapą treningową.
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

Eksporter i paczki są już prototypem na zaakceptowanych założeniach.
Najbliższym krokiem jest backend, następnie UI; próba jednej referencji
należy do końcowego odbioru.
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
pliki `commands.txt`, `convars.txt`, `entities/server.fgd`. Generator prototypowy
korzysta już z części tych komend, zgodnie z opisem na początku dokumentu.
Aktualna decyzja dopuszcza implementację na
założeniach i odkłada dowód runtime na koniec; zmiana celu na vanilla CS2
nadal wymaga osobnej decyzji.
# Odbiór panelu obsługi kont

Panel `/admin/` wymaga osobnego odbioru na docelowej konfiguracji:
logowanie przez allauth z TOTP/kodem odzyskiwania, odmowa dostępu bez drugiego
czynnika, role Support/Account Operators, świeże uwierzytelnienie przy akcjach,
brak standardowego edytora użytkowników/haseł/Stripe i brak możliwości zmiany audytu.
Sprawdzić wyszukiwanie wspólnego SteamID bez łączenia kont, indywidualny limit,
wygaśnięcie ręcznego Pro, blokadę i odblokowanie bez przywrócenia starych sesji.
Blokada nie może zmienić subskrypcji; ostrzeżenie o dalszych opłatach ma być widoczne.
Potwierdzić doręczenie wiadomości SMTP oraz docelową domenę i działanie linków,
obsługę błędu wysyłki/cooldownu i odświeżania Stripe bez zmiany płatności.
Testy automatyczne z atrapami nie są dowodem odbioru produkcyjnego SMTP/Stripe.

Lokalny odbiór implementacji: 1340 testów `tests/web` na odrębnej bazie
PostgreSQL utworzonej od zera przez migracje; obejmuje panel, polityki dostępu,
MFA, współdzielone limity uwierzytelniania i ochronę TOTP między połączeniami.
Przeglądarka przeszła rzeczywiste logowanie hasłem i TOTP, listę/kartę konta,
zmianę indywidualnego limitu oraz odczyt wpisu audytowego.
To lokalna konfiguracja testowa, nie odbiór publicznego HTTPS, SMTP lub Stripe.
