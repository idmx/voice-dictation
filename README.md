# Voice Dictation

Офлайн-инструмент голосового ввода с активацией по глобальной горячей клавише. Нажмите комбинацию клавиш — говорите — текст появится в активном поле.

**Особенности:**

- Полностью офлайн — распознавание через [faster-whisper](https://github.com/SYSTRAN/faster-whisper), данные не покидают компьютер
- Глобальные горячие клавиши — работает поверх любого приложения
- Два режима: **Push-to-talk** (удержание) и **Toggle** (нажал/отпустил)
- Кроссплатформенный — macOS и Windows
- Системный трей — управление из меню, смена модели, языка и качества на лету
- Автоматическая пунктуация и определение тишины (VAD)
- Safety таймер записи — автоматическое завершение, если потерян key-up
- Появляется в диалоге принудительного завершения (Cmd+Option+Esc) — можно «убить» без терминала

---

## 1. Как использовать

### Первый запуск

При первом запуске приложение:

1. Создаст конфигурацию по умолчанию в `~/.voice-dictation/config.toml`
2. Скачает модель Whisper (по умолчанию `base`, ~145 МБ) в `~/.voice-dictation/models/`
3. Проверит права доступа (микрофон, Accessibility на macOS)

### Базовый сценарий

1. Запустите приложение — иконка появится в системном трее
2. Установите фокус в текстовое поле (браузер, редактор, мессенджер)
3. Нажмите и удерживайте **Cmd+Shift+1** (macOS) / **Win+Shift+1** (Windows)
4. Говорите
5. Отпустите клавишу — текст появится в поле

### Режимы активации

| Режим                           | Описание                                                        |
| ------------------------------- | --------------------------------------------------------------- |
| **push_to_talk** (по умолчанию) | Запись пока клавиша удерживается, распознавание при отпускании  |
| **toggle**                      | Первое нажатие — старт записи, повторное — стоп и распознавание |

### Меню трея

Через контекстное меню иконки в трее можно:

- **Модель** — переключить между `tiny` (быстро), `base` (баланс), `small` (качественно), `medium` (максимум)
- **Язык** — сменить язык распознавания (ru, en и др.)
- **Режим** — переключить Push-to-talk / Toggle
- **Качество** — точность распознавания: Быстро (1) / Баланс (3) / Точно (5) — меняет beam_size без перезагрузки модели
- **Макс. запись** — safety таймер: 15 / 30 / 60 / 120 / 300 секунд. Если key-up потерян, запись завершится автоматически
- **Автопунктуация** — включить/отключить расстановку заглавных и знаков препинания
- **Настройки** — открыть `config.toml` в текстовом редакторе
- **Перезапуск** — перезапустить пайплайн
- **Выход** — закрыть приложение

### Конфигурация

Файл: `~/.voice-dictation/config.toml`. Изменения подхватываются без перезапуска.

```toml
hotkey = "cmd+shift+1"          # Комбинация клавиш
mode = "push_to_talk"           # push_to_talk | toggle
whisper_model = "base"          # tiny | base | small | medium
language = "ru"                 # Код языка (ru, en, de, fr, ...)
device = "cpu"                  # cpu | cuda
compute_type = "int8"           # int8 | float16 | float32
injection_method = "clipboard"  # clipboard | typing
sound_indicators = true         # Звуковые сигналы записи
restore_clipboard = true        # Восстановить буфер после вставки
initial_prompt = ""             # Контекст для Whisper (улучшает точность)
auto_punctuation = true         # Автопунктуация
beam_size = 5                   # Качество: 1=быстро, 3=баланс, 5=точно
max_recording_seconds = 30      # Safety таймер записи: 5-300 секунд
log_level = "INFO"              # DEBUG | INFO | WARNING | ERROR
```

### Модели Whisper

| Модель  | Размер  | RAM    | Скорость (CPU) | Качество русского |
| ------- | ------- | ------ | --------------  | ----------------- |
| `tiny`  | ~75 МБ  | ~400 МБ| Очень быстро   | Базовое           |
| `base`  | ~145 МБ | ~600 МБ| Быстро          | Хорошее           |
| `small` | ~480 МБ | ~1.5 ГБ| Средне          | Отличное          |
| `medium`| ~1.5 ГБ | ~4 ГБ  | Медленно        | Превосходное      |

Рекомендация: `base` — оптимальный баланс для русского языка на слабых ПК, `medium` — максимальное качество на мощных машинах.

### Способы вставки текста

| Метод                      | Как работает                                      | Плюсы                   | Минусы                              |
| -------------------------- | ------------------------------------------------- | ----------------------- | ----------------------------------- |
| `clipboard` (по умолчанию) | Копирует текст в буфер, симулирует Cmd+V / Ctrl+V | Быстро, работает везде  | Временно заменяет содержимое буфера |
| `typing`                   | Симулирует посимвольный ввод                      | Не трогает буфер обмена | Медленнее для длинного текста       |

### Права доступа

**macOS:**

- **Accessibility** — требуется для глобального перехвата клавиш и симуляции ввода. Система → Конфиденциальность → Универсальный доступ
- **Микрофон** — запрашивается автоматически при первом запуске

**Windows:**

- **Микрофон** — запрашивается системой

---

## 2. Сборка и установка

### Установка из исходников (для использования)

```bash
# Клонировать репозиторий
git clone <repo-url>
cd voice-dictation

# Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # macOS
# .venv\Scripts\activate   # Windows

# Установить пакет
pip install .
```

Запуск:

```bash
voice-dictation
# или
python -m voice_dictation
```

### Сборка дистрибутива macOS (.app / .dmg)

```bash
cd voice-dictation
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
```

Результат:

- `dist/Voice Dictation.app` — приложение macOS (без иконки в Dock, только в трее)

Создание DMG-образа (опционально, требуется `hdiutil`):

```bash
hdiutil create -volname "Voice Dictation" \
  -srcfolder "dist/Voice Dictation.app" \
  -ov -format UDZO "dist/voice-dictation.dmg"
```

> Скрипт `build_macos.sh` автоматически создаёт DMG, если `hdiutil` доступен.
> Если DMG не появился — выполните команду вручную (см. выше).

Установка:

1. Откройте `.dmg` (или скопируйте `.app`)
2. Перетащите `Voice Dictation.app` в `/Applications/`
3. При первом запуске: ПКМ → Открыть (обход Gatekeeper для неподписанного приложения)
4. Предоставьте права Accessibility и Микрофон в Системных настройках

### Сборка дистрибутива Windows (.exe)

```powershell
cd voice-dictation
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Результат:

- `dist\voice-dictation\voice-dictation.exe` — исполняемый файл

Установка:

1. Скопируйте папку `dist\voice-dictation\` в `C:\Program Files\Voice Dictation\`
2. Запустите `voice-dictation.exe`
3. Предоставьте доступ к микрофону при запросе

### Автозапуск

**macOS** — LaunchAgent:

```bash
# Включить
python -c "from voice_dictation.platform.autostart import AutoStartManager; AutoStartManager().enable()"

# Выключить
python -c "from voice_dictation.platform.autostart import AutoStartManager; AutoStartManager().disable()"
```

**Windows** — ключ в реестре (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`):

```powershell
python -c "from voice_dictation.platform.autostart import AutoStartManager; AutoStartManager().enable()"
```

---

## 3. Разработка

### Установка среды разработки

```bash
cd voice-dictation
python -m venv .venv
source .venv/bin/activate  # macOS
pip install -e ".[dev]"
```

### Структура проекта

```
src/voice_dictation/
├── core/            # FSM (StateMachine), события, исключения
├── audio/           # Захват аудио (sounddevice)
├── recognition/     # Распознавание речи (faster-whisper)
├── hotkey/          # Глобальные хоткеи (pynput), парсер комбинаций
├── injection/       # Вставка текста: macOS (CGEvent) + Windows (SendInput)
├── config/          # Pydantic-схема, TOML-менеджер, hot-reload
├── platform/        # Детекция ОС, права, автозапуск
├── ui/              # Системный трей (pystray), звуковые индикаторы
├── utils/           # Буфер обмена, логирование
├── pipeline.py      # Оркестратор пайплайна: хоткей → аудио → распознавание → вставка
└── app.py           # Главный класс Application
```

### Запуск приложения

```bash
# Из исходников (с установленным -e ".[dev]")
python -m voice_dictation

# Или через entry point
voice-dictation
```

### Запуск тестов

```bash
# Все тесты
pytest

# Только модульные (быстро)
pytest tests/unit/

# Только интеграционные
pytest tests/integration/

# Системные E2E (требуют реальную ОС)
pytest tests/system/ -m system

# Бенчмарки производительности
pytest tests/performance/ -m performance

# Конкретный файл
pytest tests/unit/test_pipeline.py -v

# С покрытием (включено по умолчанию)
pytest --cov=voice_dictation --cov-report=term-missing

# С таймаутом (защита от зависаний)
pytest --timeout=15
```

### Линт и форматирование

```bash
# Проверка
ruff check src/ tests/

# Автоисправление
ruff check --fix src/ tests/

# Форматирование
ruff format src/ tests/

# Проверка типов (опционально)
mypy src/
```

### Генерация ассетов

```bash
# Иконки для трея (idle/recording/processing PNG)
python scripts/generate_icons.py

# Тестовые аудиофайлы (WAV: sine, silence, noise)
python scripts/generate_test_audio.py
```

### Сборка

```bash
# macOS
./scripts/build_macos.sh

# Windows
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1

# Или вручную через PyInstaller
pip install pyinstaller
pyinstaller voice_dictation.spec --noconfirm
```

### Маркеры тестов

| Маркер                     | Назначение                      |
| -------------------------- | ------------------------------- |
| `@pytest.mark.macos`       | Требует macOS                   |
| `@pytest.mark.windows`     | Требует Windows                 |
| `@pytest.mark.integration` | Интеграционный тест             |
| `@pytest.mark.system`      | Системный E2E (реальное железо) |
| `@pytest.mark.performance` | Бенчмарк                        |

Пропустить системные тесты в CI:

```bash
pytest -m "not system and not performance"
```

### Конфигурация тестов

Определена в `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=voice_dictation --cov-report=term-missing"
```

---

## Технологический стек

| Компонент                | Библиотека                   |
| ------------------------ | ---------------------------- |
| Распознавание речи       | faster-whisper (CTranslate2) |
| Захват аудио             | sounddevice + numpy          |
| Глобальные хоткеи        | pynput                       |
| Вставка текста (macOS)   | PyObjC (Quartz, AppKit)      |
| Вставка текста (Windows) | pywin32 / ctypes             |
| Системный трей           | pystray + Pillow             |
| Конфигурация             | Pydantic v2 + TOML           |
| Логирование              | loguru                       |

## Лицензия

Приватный проект.
