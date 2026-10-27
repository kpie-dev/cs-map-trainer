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
- CLI: `players`, `analyze`, `benchmark`, `validate-scenarios`, `schema`.
- Parser nieskompresowanych dem CS2 `de_mirage` do 1 GiB, zbiorcze migawki
  sprzed obrażeń, wykluczenia i grupowanie porównywalnych wygranych/przegranych.
- Reguły `damage-window-v3`: zachowują dostępne kąty przeciwnika, a brakujący
  pitch/yaw wyliczają ku pozycji gracza, z oznaczeniem
  `opponent_aim_inferred_toward_player`. Kąty gracza nie są zgadywane.
  Grupy przybliżone i kompletne są rozdzielone.
- Benchmark w osobnych procesach, Docker CLI, testy i workflow CI.
- Nie ma eksportera, paczek, backendu WWW ani UI. Nie wykonano próby Yprac.
  Nie ma automatycznych ocen treningu ani kolejki powtórek.

## Wymagania, których trzeba pilnować

- Jedna integracja: Yprac Hub `3070715607`, docelowo Mirage/Sandbox.
  Nie przełączać samodzielnie na vanilla CS2, własny serwer/plugin ani inną usługę.
- Po wejściu do mapy/trybu użytkownik raz wkleja ustawienie scenariusza
  do konsoli. Bot, pozycje, kierunki oczu i broń obu stron mają ustawić się
  automatycznie, bez ręcznego indeksu bota i przepisywania kolejnych komend.
- Jeden aktywny pojedynek i bot naraz. Nie nadpisywać bindów ani `autoexec.cfg`.
  CFG jest opcjonalny; UI ma przycisk kopiowania pełnego ustawienia.
- `setpos_player <player_index> <x> <y> [z]` używa indeksu gracza, nie `userid`.
  Przyjmowany mechanizm inicjalizacji jednego bota, jego indeks i gotowość
  przed teleportacją podlegają końcowej próbie, nie są już potwierdzonym faktem.
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
  Wybrać jeden storage przed jego implementacją. Nie dodawać osobnego
  frontendu/API, Redis/Celery, LLM ani płatności bez potrzeby lub decyzji.

## Todos i zależności

Status „planowane” nie oznacza implementacji. Zadania bez wspólnej zależności
mogą postępować niezależnie; UI zaczyna się po gotowym backendzie.

| ID | Status | Zakres i warunek odbioru | Zależności |
|---|---|---|---|
| `bootstrap-cli` | Gotowe | Istniejący parser, analiza, kontrakt, CLI, benchmark, Docker i testy | Brak |
| `build-training-exporter` | Planowane — następny krok | Jeden eksporter na założeniach komend: bot, XYZ, kąty, broń, jedno wklejenie; walidacja, jawne ograniczenia i testy wyjścia | `bootstrap-cli` |
| `assemble-training-packs` | Planowane — BE | Wybór/odrzucanie scenariuszy, manifest, instrukcje i paczki; wspólna logika dla CLI i aplikacji | `build-training-exporter` |
| `define-saas-policies` | Planowane — BE | Wybrać storage, auth, limity, retencję i budżety zasobów; nie czekać na płatności | `bootstrap-cli` |
| `build-minimal-web` | Planowane — BE | Django/PostgreSQL, prywatny upload, uprawnienia, Django-Q2, worker, idempotencja, retry i limity; testy backendu | `define-saas-policies` |
| `complete-training-backend` | Planowane — G2 | Połączyć skład i wybór gracza, analizę, raport, selekcję oraz autoryzowane paczki/eksport; testy bez uruchamiania gry | `build-minimal-web`, `assemble-training-packs` |
| `build-training-ui` | Planowane — po BE | Upload, status zadania, wybór gracza, raport z ograniczeniami, selekcja sytuacji, paczki i kopiowanie komend | `complete-training-backend` |
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
2. Zacząć od `build-training-exporter`. Obejrzeć `src/cs_map_trainer/scenarios.py`,
   `analysis.py`, `cli.py` oraz istniejące testy. Nie przepisywać parsera ani
   gotowej reguły orientacji.
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
> Kontynuuj od build-training-exporter. Obowiązuje kolejność BE → UI →
> końcowe próby CS2/Yprac; komendy przyjmujemy jako założenie implementacyjne.
> Zachowaj istniejący kod i zastane zmiany.
