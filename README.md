# Factory Content Selling MVP

Backend-first MVP, который принимает intake через Telegram, сохраняет demo screen recording и строит прозрачные артефакты для следующего сценарного/creative пайплайна.

## Что делает MVP

- ведет клиента по 12 шагам в Telegram
- сохраняет каждую заявку в `submissions/<submission-id>/`
- нормализует бриф в `client_brief.json`
- делает прагматичный анализ demo-видео в `demo_analysis.json`
- строит `voiceover_plan.json`
- собирает `scenario_prompt.txt`
- сохраняет `run_summary.json` и debug-артефакты

## Структура проекта

```text
src/factorycontentselling/
  bot.py
  cli.py
  config.py
  models.py
  orchestrator.py
  storage.py
  pipeline/
    brief_normalizer.py
    demo_analyzer.py
    scenario_prompt_builder.py
    voiceover_planner.py
  services/
    ocr.py
    openai_adapter.py
    video.py
```

## Структура submission

```text
submissions/<id>/
  raw/
    intake.json
    demo.mp4
  derived/
    client_brief.json
    demo_analysis.json
    voiceover_plan.json
    scenario_prompt.txt
    run_summary.json
  logs/
    analysis_debug.json
    frames/
    audio/
    pipeline_error.log   # только если случилась ошибка
```

## MVP assumptions

- стек выбран максимально простой: Python + Telegram Bot API + file-based storage
- без `OPENAI_API_KEY` пайплайн все равно работает, но анализ demo идет в heuristic mode
- OCR делается через `rapidocr-onnxruntime`; если модуль не поднимется или текст плохо читается, это попадет в `confidence_notes`
- транскрипция делается только если есть аудио и задан `OPENAI_API_KEY`
- видео-анализ не пытается “магически понять все”, а собирает полезный coarse breakdown для отладки и human-in-the-loop

## Быстрый запуск сегодня

### 1. Поднять окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
cp .env.example .env
```

Заполни в `.env` минимум:

```env
TELEGRAM_BOT_TOKEN=...
SUBMISSION_RETENTION_DAYS=7
```

Опционально для richer analysis:

```env
OPENAI_API_KEY=...
OPENAI_VISION_MODEL=gpt-4.1-mini
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
```

`SUBMISSION_RETENTION_DAYS` управляет автоудалением старых заявок с диска. По умолчанию это `7` дней.

### 2. Запустить Telegram bot

```bash
factorycontent run-bot
```

Если не хочется ставить пакет, есть прямой fallback:

```bash
PYTHONPATH=src python -m factorycontentselling.cli run-bot
```

### 3. Пройти intake

В Telegram:

- открыть бота
- отправить `/start`
- ответить на вопросы по одному
- загрузить demo screen recording
- при желании прислать ссылку или `skip`

После последнего шага бот:

- создаст submission
- сохранит raw intake и видео
- прогонит pipeline
- пришлет статус, warnings и список файлов

## Локальный повторный прогон pipeline

Если intake уже сохранен и хочется просто перегнать pipeline:

```bash
factorycontent run-pipeline --submission-id <submission-id>
```

Fallback без package install:

```bash
PYTHONPATH=src python -m factorycontentselling.cli run-pipeline --submission-id <submission-id>
```

## Очистка старых файлов

Старые папки в `submissions/` теперь удаляются автоматически по возрасту:

- при старте бота
- после завершения каждой новой заявки

По умолчанию хранятся `7` дней. Это настраивается через:

```env
SUBMISSION_RETENTION_DAYS=7
```

Если хочется прогнать очистку руками:

```bash
factorycontent cleanup-submissions
```

Или с явным окном хранения:

```bash
factorycontent cleanup-submissions --days 3
```

## Вынести в интернет

Если бот на ноутбуке отвечает нестабильно, это нормальный кандидат на внешний worker.

Самый простой вариант сейчас: Render background worker.

Почему подходит:

- worker может крутиться постоянно без входящего HTTP
- к worker можно прикрепить persistent disk
- без persistent disk filesystem у Render ephemeral, так что для `submissions/` диск обязателен

Официальные ссылки:

- [Render background workers](https://render.com/docs/background-workers)
- [Render persistent disks](https://render.com/docs/disks)

Что уже подготовлено в репозитории:

- [Dockerfile](/Users/nikitastarozilov/Projects/factorycontentselling/Dockerfile)
- [render.yaml](/Users/nikitastarozilov/Projects/factorycontentselling/render.yaml)

Минимальный деплой на Render:

1. Залить этот проект в GitHub
2. В Render создать сервис из `render.yaml`
3. Добавить env vars:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
4. Прикрепить persistent disk и смонтировать его в `/app/submissions`
5. Задеплоить

Альтернатива: Railway.

У Railway тоже нужен volume, иначе storage будет ephemeral:

- [Railway services](https://docs.railway.com/develop/services)

## Что лежит в артефактах

### `client_brief.json`

- нормализованный brief
- reasonable defaults
- `missing_fields` для прозрачности

### `demo_analysis.json`

- `detected_steps` по coarse таймкодам
- `key_moments`
- `candidate_voiceover_beats`
- `uncertainties`
- `confidence_notes`
- OCR text и transcript, если доступны

### `voiceover_plan.json`

- `overall_angle`
- `voice_style`
- сегменты по таймкодам
- draft lines, которые можно дальше переписывать

### `scenario_prompt.txt`

master prompt для существующего сценарного агента / content-factory:

- кто продукт
- для кого
- какой pain
- что реально видно в demo
- как синхронизировать hook и VO с экраном
- какие архетипы можно/нельзя
- какие claims заблокированы

## Риски и pragmatic ограничения

- если demo без текста и без аудио, `demo_analysis` все равно будет собран, но с большими `uncertainties`
- screen type classification сейчас heuristic, по OCR/визуальным паттернам
- для продакшн-качества потом стоит заменить `OpenAIAdapter` и `OCRAdapter` на твои существующие internal adapters
- текущий entrypoint синхронный и рассчитан именно на MVP today test, а не на многопользовательскую очередь

## Как подключить твой existing content-factory дальше

Самая удобная точка интеграции сейчас:

- читать `submissions/<id>/derived/client_brief.json`
- читать `submissions/<id>/derived/demo_analysis.json`
- читать `submissions/<id>/derived/voiceover_plan.json`
- передавать `submissions/<id>/derived/scenario_prompt.txt` в твой сценарный агент

## Следующий шаг после сегодняшнего теста

Если MVP зайдет, логично добавить:

- better scene segmentation
- richer OCR/video understanding adapter
- Telegram command `/status <id>`
- webhook mode вместо polling
- bridge в твой existing content-factory
