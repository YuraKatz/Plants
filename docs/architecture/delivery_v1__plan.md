# План v1 — что осталось сделать после консилиума

> Дата: 2026-05-06
> Source: `delivery_v1__synthesis.md` (синтез трёх голосов: Claude, Codex, Gemini)
> Формат: чеклист для **автономной работы** Claude. Юра даёт зелёный свет блоку → Claude выполняет весь блок без переспросов до stop condition.

---

## Состояние на момент составления плана

### ✅ Уже в working tree (не закоммичено)
- `scripts/build.py` — schema fix water-groups, удалён дубль `_build_pests_diseases`, hardcoded counts → `len()`, `garden-pesticides.yaml` подключён, новый endpoint `api/pesticides.json`, `asset_root` в `_base_ctx`
- `scripts/validate.py` — новый файл, 7 категорий проверок, понимает rosetta-паттерн i18n
- `static/manifest.json` — subpath-safe `./` пути
- `static/service-worker.js` — relative paths, кэш для `api/*.json` (stale-while-revalidate), version v2
- `templates/base.html` — manifest link + SW registration на каждой странице, не только index
- `templates/pages/index.html` — убраны дубли PWA meta (теперь в base)
- `data/i18n/ru.yaml` — добавлены 11 catalog_difficulty/feeding ключей
- `data/i18n/en.yaml` — добавлены 4 rotation ключа, удалён 1 dead-key
- `data/i18n/he.yaml` — добавлены 4 rotation ключа, удалён 1 dead-key
- `CLAUDE.md` — 33→35, добавлен раздел «Дисциплина sync», упоминание validate.py
- `README.md` — убраны устаревшие counts
- `docs/llms.txt` — счётчики обновлены руками (одноразово)
- `docs/architecture/delivery_v1__audit-prompt.md` — материал консилиума
- `docs/architecture/delivery_v1__claude-position.md` — мой голос (с H9)
- `docs/architecture/delivery_v1__codex-response.md` — ответ Codex
- `docs/architecture/delivery_v1__gemini-response.md` — ответ Gemini
- `docs/architecture/delivery_v1__synthesis.md` — синтез трёх голосов
- `site/` — пересобран

### ✅ Validator: All checks passed

### ⏳ Открытые решения (требуют ответа Юры до старта блоков)
1. **H9 (AI-app с фото и журналом):** делать отдельный консилиум через Codex/Gemini или сразу декомпозировать в план?
2. **Pre-commit hook на validate.py:** ставить или нет?

### ❌ Решения, которые **не блокируют** работу
- **i18n:** уже синхронизирован (15 missing keys заполнены, 2 dead-keys убраны). Действие не нужно.
- **Obsidian как core engine:** Gemini предложил, я и Codex против. Откладываем минимум на месяц после instant search и теста PWA на телефоне.

---

## Принципы автономной работы

1. Юра даёт зелёный свет блоку → Claude выполняет **весь** блок без промежуточных подтверждений
2. Каждый блок = 1 коммит с понятным message
3. После каждого блока: `validate.py` должен возвращать **All checks passed**
4. Build должен проходить
5. Stop conditions (см. ниже) → Claude останавливается и пишет Юре

---

## Чеклист блоков

### Блок 0 — Closeout сегодняшней работы (готов к старту)
**Зачем:** закрыть всё что в working tree одним логичным коммитом, не потерять изменения.

- [ ] `git status` — обзор всех изменений
- [ ] Просмотреть diff для критичных файлов (build.py, base.html, manifest, sw)
- [ ] `git add` — добавить все осмысленные изменения (без секретов и временных файлов)
- [ ] Создать коммит с message:
  ```
  Fix systematic data drift + add validator + PWA subpath support

  - Schema mismatch in api/water-groups.json (was returning null)
  - Hardcoded counts (26 plants → len(plants), etc.)
  - Connect garden-pesticides.yaml to build (new api/pesticides.json)
  - Remove duplicate _build_pests_diseases
  - PWA paths now subpath-safe for /Plants/ on GitHub Pages
  - SW registers on every page, caches api/*.json offline
  - i18n gaps closed: 11 catalog_* keys to ru, 4 rotation_* keys to en/he
  - New scripts/validate.py catches 7 categories of regressions
  - CLAUDE.md: sync discipline rules, 33→35 plants

  See docs/architecture/delivery_v1__synthesis.md for the consilium synthesis.
  ```
- [ ] `git push` к удалённому
- [ ] Подождать GitHub Actions (если deploy on push)
- **Acceptance:** working tree clean, последний commit отражает сегодняшнюю работу, GitHub Pages обновился (можно проверить `https://yurakatz.github.io/Plants/api/water-groups.json` — должен иметь `after_calmag_ppm`)

---

### Блок 1 — Instant Search ⭐ (главный winning move)
**Зачем (value first):** ввожу `регал шилдс` или `белый пушок` или `B весна` → за 200ms карточка с ответом. Без листания вкладок. Работает оффлайн.

- [ ] Выбрать библиотеку: **MiniSearch** (5kb gzipped, fuzzy search, JS-only, без сборщика)
- [ ] `static/js/minisearch.min.js` — положить минифицированный CDN-сборкой
- [ ] `scripts/build_search_index.py` (или встроить в build.py) — генерирует `site/api/search-index.json` со всеми documenta для индексации:
  - 35 растений (id, name, latin, type, group, mix_number, lighting, risks, care_notes)
  - 17 смесей (id, name, suitable_for, components)
  - 15 продуктов (id, name, brand, type, target_pests/composition, indoor_use)
  - 3 пестицида
  - 9+ симптомов из troubleshooting
- [ ] `templates/_search_widget.html` — partial template с input + results dropdown
- [ ] Включить в `base.html` сверху или в header — на каждой странице
- [ ] `templates/js/search.js` — клиентский код:
  - При первой загрузке: fetch `api/search-index.json`, построить MiniSearch index
  - Слушать input → показать топ-5 результатов с подсветкой
  - При клике на результат → перейти на соответствующую страницу/якорь
- [ ] CSS для widget — простой dropdown
- [ ] Service Worker: добавить `api/search-index.json` в кэш
- [ ] i18n: ключи `search_placeholder`, `search_no_results`, `search_searching` в ru/en/he
- [ ] Build + validate + manual smoke test:
  - Запустить локально, открыть `site/index.html`
  - Тест: «регал шилдс», «червец», «B весна», «kf macroboost»
- [ ] Commit с message: `Add instant search (MiniSearch) over api/*.json — works offline, fuzzy match`

**Acceptance:**
- Ввожу `регал шилдс` в любой странице → за <500ms карточка алоказии регал шилдс
- Ввожу `белый пушок` → mealybug + Confidor
- Ввожу с опечаткой `kalateya` → находит калатеи
- Работает оффлайн (выключил Wi-Fi → всё равно ищет)
- На en/he тоже работает (с переведёнными именами через rosetta)

**Stop conditions:**
- MiniSearch не находит nothing — нужно проверить структуру индекса
- Index файл получается > 500kb — оптимизировать (только нужные поля)
- Юра скажет «другая lib лучше» — пересмотреть выбор

---

### Блок 2 — Auto-generate llms.txt
**Зачем (value first):** больше никогда не отстаёт от YAML. Ручную правку чисел делать не приходится. AI всегда видит актуальное состояние коллекции.

- [ ] `scripts/build_llms.py` — отдельный модуль:
  - Читает `data/*.yaml` через те же loader-ы что и build.py
  - Собирает текстовый markdown по разделам:
    - Header: имя проекта + actual counts
    - Что покрыто (numbered list)
    - System assumptions (RO + CalMag + 7 групп)
    - Canonical sources (актуальные YAML)
    - Plant collection breakdown по типам (вычисляется из `type` поля)
    - Water groups summary (PPM/pH per group)
    - Feeding groups summary
    - Pages list
  - Опциональные блоки из `docs/*.md` для нарратива (PLAN, kf-leon-vgi)
- [ ] Интеграция в `build.py` `main()`: вызвать `build_llms.py` после API generation, записать в `site/llms.txt`
- [ ] Удалить копирование `docs/llms.txt → site/llms.txt` в build.py (старая логика)
- [ ] Решить судьбу `docs/llms.txt`: либо удалить, либо превратить в README ссылающийся на site/llms.txt
- [ ] Validator: новая проверка что `site/llms.txt` существует и содержит актуальные числа
- [ ] Build + validate
- [ ] Commit: `Auto-generate llms.txt from YAML+docs in build.py`

**Acceptance:**
- Открываю `site/llms.txt` → вижу `35 plants`, `17 mixes`, `15 products` — актуальные числа
- Меняю в plants.yaml — добавляю одно растение → re-build → llms.txt отражает 36
- Validator больше не ловит hardcoded counts в `docs/llms.txt` (его нет или он не претендует на актуальность)

---

### Блок 3 — Pre-commit hook на validate.py (опционально)
**Зачем:** при попытке коммита с регрессиями (sync расходится, переводы съехали) — git блокирует commit пока не починишь.

**Условие старта:** Юра ответил «да» на pre-commit вопрос.

- [ ] Создать `.git/hooks/pre-commit` (shell script) или `.pre-commit-config.yaml` (если используется фреймворк)
- [ ] Hook выполняет: `python scripts/validate.py` → exit code 1 блокирует commit
- [ ] Документация в CLAUDE.md как обходить (`git commit --no-verify` для emergencies)
- [ ] Тест: внести регрессию (hardcoded `'26 plants'` куда-то) → попытаться commit → блокируется
- [ ] Откатить тестовую регрессию
- [ ] Commit hook setup (если в репо хранится)

**Acceptance:**
- Попытка commit с регрессией → блокируется с понятным сообщением
- `git commit --no-verify` работает как escape-hatch для аварийных случаев

---

### Блок 4 — H9 декомпозиция или консилиум
**Зачем:** AI-app с фото и журналом — твоя идея, не оценена Codex/Gemini. Решить путь.

**Условие старта:** Юра ответил один из:
- (A) «делаем консилиум» — отдельный аудит-промпт по H9, прогнать через Codex+Gemini, синтезировать
- (B) «сразу декомпозиция» — план h9_companion_app.md без второго мнения

Если **(A) консилиум:**
- [ ] `docs/architecture/h9_companion_app__audit-prompt.md` — промпт по H9: камера → Vision → запись в журнал
- [ ] Запустить через `codex exec` и `gemini --skip-trust -p`
- [ ] Сохранить ответы рядом
- [ ] Synthesis: `h9_companion_app__synthesis.md`
- [ ] Не начинать имплементацию — ждать решения Юры по synthesis

Если **(B) декомпозиция:**
- [ ] `docs/architecture/h9_companion_app__plan.md`:
  - UI: кнопка «Сделать фото» в каждой карточке растения (на plants-catalog.html и plant-problems.html)
  - `<input type="file" accept="image/*" capture="environment">` — нативная камера на Android
  - Vision API call (выбрать: Claude или Gemini Vision; нужен API key из env)
  - Структура журнала: `data/events/<plant_id>.yaml` со списком событий (date, type, photo_ref, ai_diagnosis, action_taken)
  - UI карточки растения: показать последние N событий
  - Storage фото: GitHub LFS или git binary (compress первый)
  - Offline-first: если нет сети — события в localStorage, push в git когда сеть появится
  - i18n: новые ключи интерфейса
- [ ] План — до коммита, ждать зелёный свет от Юры

**Stop:** в любом случае Юра должен подтвердить план H9 до начала имплементации.

---

### Блок 5 — Тест PWA на твоём Android (только Юра)
**Зачем:** убедиться что весь PWA-стек реально работает в твоём use case.

**Это блок Юры, не Claude.** Claude помогает только в interpretation результата.

- [ ] После Блока 0 (push) и deploy: открыть `https://yurakatz.github.io/Plants/` в Chrome на Android
- [ ] Меню (⋮) → «Установить приложение» / «Add to Home Screen»
- [ ] Иконка появилась на главном экране
- [ ] Тап → запуск в standalone (без адресной строки браузера)
- [ ] Подождать ~10 секунд для полной загрузки кэша
- [ ] **Тест оффлайна:** выключить Wi-Fi → запустить иконку → проверить что работает
- [ ] **Тест поиска (после Блока 1):** ввести `регал шилдс` → должна быть карточка
- [ ] Сообщить Claude что работает / не работает

---

## Что НЕ делать (явно, на 1-3 месяца)

- Native Android (Kotlin/Compose) — все 3 голоса против
- Capacitor поверх существующего сайта — все 3 голоса против на этом этапе
- Чат-бот как primary интерфейс — все 3 голоса против
- Локальный LLM на телефоне как core path — все 3 голоса против
- Полная миграция на Obsidian — отложено минимум до результатов теста PWA
- Multi-tenant / SaaS — преждевременно
- Переписать build.py на новый фреймворк — работает, чинится локально

## Stop conditions (когда Claude останавливается и пишет Юре)

1. **Hard blocker:** требуется решение Юры (выбор подхода, открытый вопрос плана)
2. **Validator failure после моего изменения:** значит ввёл регрессию, надо разобраться
3. **Build crashes:** ту же логика
4. **Acceptance не достигается:** значит план не работает, надо пересмотреть
5. **Я выхожу за scope блока:** найдена смежная проблема — сообщить, не лечить молча
6. **Меняю файл, который не упомянут в блоке:** аналогично, сообщить

## Порядок выполнения

```
Блок 0 (commit + push) ─┬→ ждать deploy
                        │
                        ├→ Блок 1 (instant search) ─→ Блок 5 (тест PWA, Юра)
                        │
                        ├→ Блок 2 (auto-llms) ─→ ⌛ ждать H9 решения от Юры
                        │
                        └→ Блок 3 (pre-commit) [если Юра сказал "да"]
                                  │
                                  └→ Блок 4 (H9, по выбранному пути)
```

Блоки 1, 2, 3 — параллельно-независимы по логике. Можно делать в любом порядке после 0.
Блок 4 — последний (после 0+решения).
Блок 5 — физический, делает только Юра.

---

## Что Claude НЕ делает в этом плане

- Не пишет H9 код без явного подтверждения плана
- Не удаляет en/he языки без явного «да» от Юры (даже если Gemini рекомендует)
- Не мигрирует на Obsidian / новый стек без явного решения
- Не делает force push, не амендит существующие коммиты
- Не игнорирует validator failures
