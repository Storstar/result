from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .config import get_settings
from .models import IntakeAnswers, IntakeRecord, SubmissionMetadata
from .orchestrator import SubmissionOrchestrator
from .services.openai_adapter import OpenAIAdapter
from .storage import SubmissionStorage


(
    APP_NAME,
    PRODUCT_SUMMARY,
    TARGET_AUDIENCE,
    CORE_PAIN,
    END_RESULT,
    CREATIVE_LANGUAGE,
    BLOCKED_ARCHETYPES,
    BLOCKED_CLAIMS,
    CTA,
    APP_ICON,
    VIDEO,
    DEMO_WALKTHROUGH,
    EXTRA_PROJECT_CONTEXT,
) = range(13)


QUESTIONS = [
    "Как называется приложение?",
    "Что делает приложение в 1-2 предложениях?",
    "Для кого оно?",
    "Какую главную боль решает?",
    "Что получает пользователь в конце главного сценария в приложении?",
    "На каком языке делать креативы и voiceover? Например: English / Russian / Spanish.",
    "Какие герои или стили точно нельзя использовать?",
    "Есть ли запрещенные claims, формулировки или юридические ограничения?",
    "Какое действие нужно предложить зрителю в конце рекламы? Например: скачать приложение, попробовать бесплатно, зайти на сайт.",
    "Опционально: пришлите иконку приложения как image или file. Ее можно использовать в финальном баннере с названием приложения. Если пока без иконки, отправьте `skip`.",
    "Пришлите demo screen recording как video или file.",
    "Опционально: если хотите, одним сообщением или voice note опишите, что происходит в demo и что вы нажимаете. Если в самом видео уже есть понятная озвучка или комментарий, можно отправить `skip`.",
    "Последнее: добавьте любую важную информацию о проекте, приложении, позиционировании, ограничениях, ссылках или нюансах. Если нечего добавить, отправьте `skip`.",
]


ANSWER_KEYS = [
    "app_name",
    "product_summary",
    "target_audience",
    "core_pain",
    "end_result",
    "creative_language",
    "blocked_archetypes",
    "blocked_claims",
    "cta",
    "app_icon_note",
    "video",
    "demo_walkthrough",
    "extra_project_context",
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _reset_conversation_state(context)
    context.user_data["state"] = APP_NAME
    sent = await _reply_with_retry(
        update,
        "Соберем заявку для demo-to-creative MVP. Можно отвечать текстом, а часть шагов и голосом. В конце я запущу обработку."
    )
    if not sent:
        return APP_NAME
    await _reply_with_retry(update, QUESTIONS[0])
    return APP_NAME


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _reset_conversation_state(context)
    await update.message.reply_text("Интейк остановлен. Можно начать заново командой /start.")
    return ConversationHandler.END


async def _reset_conversation_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    background_tasks = context.user_data.get("background_tasks", [])
    for task in background_tasks:
        if isinstance(task, asyncio.Task) and not task.done():
            task.cancel()
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)
    context.user_data.clear()


async def _reply_with_retry(update: Update, text: str, attempts: int = 3) -> bool:
    if update.message is None:
        return False
    for attempt in range(1, attempts + 1):
        try:
            await update.message.reply_text(text)
            return True
        except (TimedOut, NetworkError):
            if attempt == attempts:
                return False
            await asyncio.sleep(0.8 * attempt)
    return False


async def handle_text_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data.get("state", APP_NAME)
    key = ANSWER_KEYS[state]
    context.user_data[key] = update.message.text.strip()
    return await advance_to_next_state(update, context, state)


async def advance_to_next_state(update: Update, context: ContextTypes.DEFAULT_TYPE, state: int) -> int:
    next_state = state + 1
    sent = await _reply_with_retry(update, QUESTIONS[next_state])
    if not sent:
        if update.message is not None:
            await update.message.reply_text("Что-то подвисло на отправке следующего вопроса. Отправьте ваш ответ еще раз.")
        return state
    context.user_data["state"] = next_state
    return next_state


async def _download_voice_note(update: Update, file_stem: str) -> Optional[Path]:
    voice = update.message.voice if update.message else None
    if voice is None:
        return None
    temp_dir = Path(tempfile.mkdtemp(prefix="factorycontent_voice_"))
    temp_path = temp_dir / f"{file_stem}.ogg"
    telegram_file = await voice.get_file()
    await telegram_file.download_to_drive(custom_path=str(temp_path))
    return temp_path


async def handle_voice_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data.get("state", APP_NAME)
    if state in {APP_ICON, VIDEO, DEMO_WALKTHROUGH}:
        await update.message.reply_text("На этом шаге нужен другой тип ответа. Следуйте подсказке бота.")
        return state

    temp_path = await _download_voice_note(update, f"answer_state_{state}")
    if temp_path is None:
        await update.message.reply_text("Не удалось получить voice note. Попробуйте еще раз.")
        return state

    key = ANSWER_KEYS[state]
    context.user_data[key] = f"[voice_note_pending] {temp_path}"
    background_tasks = context.user_data.setdefault("background_tasks", [])
    background_tasks.append(asyncio.create_task(_transcribe_into_user_data(context, key, temp_path)))
    if state == EXTRA_PROJECT_CONTEXT:
        await asyncio.gather(*background_tasks, return_exceptions=True)
        context.user_data["background_tasks"] = []
        return await finalize_submission(update, context, from_voice=True)
    return await advance_to_next_state(update, context, state)


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file_obj = None
    file_name = "demo.mp4"
    if update.message.video:
        file_obj = update.message.video
        if update.message.video.file_name:
            file_name = update.message.video.file_name
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("video/"):
        file_obj = update.message.document
        file_name = update.message.document.file_name or file_name

    if file_obj is None:
        await update.message.reply_text("Нужен именно видеофайл. Пришлите `video` или `document` с video mime-type.")
        return VIDEO

    telegram_file = await file_obj.get_file()
    temp_dir = Path(tempfile.mkdtemp(prefix="factorycontent_"))
    temp_path = temp_dir / file_name
    await telegram_file.download_to_drive(custom_path=str(temp_path))

    context.user_data["video_temp_path"] = str(temp_path)
    context.user_data["video_file_name"] = file_name
    sent = await _reply_with_retry(update, QUESTIONS[DEMO_WALKTHROUGH])
    if not sent:
        await update.message.reply_text("Видео сохранил, но не смог отправить следующий вопрос. Просто пришлите следующее сообщение еще раз.")
        return VIDEO
    context.user_data["state"] = DEMO_WALKTHROUGH
    return DEMO_WALKTHROUGH


async def handle_app_icon_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text.strip()
    context.user_data["app_icon_note"] = "" if answer.lower() == "skip" else answer
    return await advance_to_next_state(update, context, APP_ICON)


async def handle_app_icon_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file_obj = None
    file_name = "app_icon.png"
    if update.message.photo:
        file_obj = update.message.photo[-1]
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"):
        file_obj = update.message.document
        file_name = update.message.document.file_name or file_name

    if file_obj is None:
        await update.message.reply_text("На этом шаге нужна картинка, image file, или `skip`.")
        return APP_ICON

    telegram_file = await file_obj.get_file()
    temp_dir = Path(tempfile.mkdtemp(prefix="factorycontent_icon_"))
    temp_path = temp_dir / file_name
    await telegram_file.download_to_drive(custom_path=str(temp_path))

    context.user_data["icon_temp_path"] = str(temp_path)
    context.user_data["icon_file_name"] = file_name
    context.user_data["app_icon_note"] = "icon_uploaded"
    return await advance_to_next_state(update, context, APP_ICON)


async def handle_demo_walkthrough_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answer = update.message.text.strip()
    context.user_data["demo_walkthrough"] = "" if answer.lower() == "skip" else answer
    return await advance_to_next_state(update, context, DEMO_WALKTHROUGH)


async def handle_demo_walkthrough_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    temp_path = await _download_voice_note(update, "demo_walkthrough")
    if temp_path is None:
        await update.message.reply_text("Пришлите voice note или текстовое описание шагов в demo.")
        return DEMO_WALKTHROUGH

    context.user_data["demo_walkthrough_voice_path"] = str(temp_path)
    context.user_data["demo_walkthrough"] = f"[voice_note_pending] {temp_path}"
    background_tasks = context.user_data.setdefault("background_tasks", [])
    background_tasks.append(asyncio.create_task(_transcribe_into_user_data(context, "demo_walkthrough", temp_path)))
    return await advance_to_next_state(update, context, DEMO_WALKTHROUGH)


async def _transcribe_into_user_data(context: ContextTypes.DEFAULT_TYPE, key: str, temp_path: Path) -> None:
    transcript = await asyncio.to_thread(OpenAIAdapter().transcribe_audio, temp_path)
    context.user_data[key] = transcript.strip() or f"[voice_note_saved] {temp_path}"


async def finalize_submission(update: Update, context: ContextTypes.DEFAULT_TYPE, from_voice: bool = False) -> int:
    if not from_voice:
        extra_context = update.message.text.strip()
        context.user_data["extra_project_context"] = "" if extra_context.lower() == "skip" else extra_context
    background_tasks = context.user_data.get("background_tasks", [])
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)
        context.user_data["background_tasks"] = []

    storage = SubmissionStorage()
    submission_id = storage.new_submission_id()
    user = update.effective_user
    chat = update.effective_chat

    answers = IntakeAnswers(
        app_name=context.user_data.get("app_name", ""),
        product_summary=context.user_data.get("product_summary", ""),
        target_audience=context.user_data.get("target_audience", ""),
        core_pain=context.user_data.get("core_pain", ""),
        end_result=context.user_data.get("end_result", ""),
        creative_language=context.user_data.get("creative_language", ""),
        blocked_archetypes=context.user_data.get("blocked_archetypes", ""),
        blocked_claims=context.user_data.get("blocked_claims", ""),
        cta=context.user_data.get("cta", ""),
        app_icon_note=context.user_data.get("app_icon_note", ""),
        demo_walkthrough=context.user_data.get("demo_walkthrough", ""),
        extra_project_context=context.user_data.get("extra_project_context", ""),
    )
    metadata = SubmissionMetadata(
        submission_id=submission_id,
        telegram_user_id=user.id if user else None,
        telegram_username=user.username if user else None,
        telegram_chat_id=chat.id if chat else None,
        uploaded_video_name=context.user_data.get("video_file_name", "demo.mp4"),
        uploaded_icon_name=context.user_data.get("icon_file_name", ""),
    )
    record = IntakeRecord(metadata=metadata, answers=answers)
    paths = storage.save_intake(submission_id, record)
    icon_temp_path = context.user_data.get("icon_temp_path")
    if icon_temp_path:
        storage.save_uploaded_icon(submission_id, Path(icon_temp_path))
    video_temp_path = Path(context.user_data["video_temp_path"])
    storage.save_uploaded_video(submission_id, video_temp_path)
    walkthrough_voice_path = context.user_data.get("demo_walkthrough_voice_path")
    if walkthrough_voice_path:
        paths.demo_walkthrough_voice.write_bytes(Path(walkthrough_voice_path).read_bytes())

    await _reply_with_retry(
        update,
        (
            f"Заявка {submission_id} сохранена.\n"
            "Начинаю обработку. Ожидайте примерно 5 минут."
        ),
    )

    orchestrator = SubmissionOrchestrator(storage=storage)
    run_summary = await asyncio.to_thread(orchestrator.run, submission_id)

    warning_count = len(run_summary.warnings)
    if run_summary.status == "completed":
        summary_text = (
            f"Готово. Заявка {submission_id} обработана.\n"
            f"Собрал пакет файлов и отправляю его сюда.\n"
            f"Warnings: {warning_count}"
        )
    else:
        error_text = run_summary.errors[0] if run_summary.errors else "unknown error"
        summary_text = (
            f"Заявка {submission_id} обработалась с ошибкой.\n"
            f"Что успел, я все равно собрал в архив.\n"
            f"Ошибка: {error_text}"
        )
    await _reply_with_retry(update, summary_text)

    bundle_path = run_summary.artifacts.get("result_bundle_zip")
    if bundle_path:
        with Path(bundle_path).open("rb") as bundle_file:
            await update.message.reply_document(
                document=bundle_file,
                filename=f"{submission_id}-result-bundle.zip",
                caption="Внутри raw intake, derived artifacts и logs.",
            )

    await asyncio.to_thread(storage.cleanup_old_submissions)

    context.user_data.clear()
    return ConversationHandler.END


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the bot.")

    application = Application.builder().token(settings.telegram_bot_token).build()
    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        allow_reentry=True,
        states={
            APP_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_step),
                MessageHandler(filters.VOICE, handle_voice_step),
            ],
            PRODUCT_SUMMARY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_step),
                MessageHandler(filters.VOICE, handle_voice_step),
            ],
            TARGET_AUDIENCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_step),
                MessageHandler(filters.VOICE, handle_voice_step),
            ],
            CORE_PAIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_step),
                MessageHandler(filters.VOICE, handle_voice_step),
            ],
            END_RESULT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_step),
                MessageHandler(filters.VOICE, handle_voice_step),
            ],
            CREATIVE_LANGUAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_step),
                MessageHandler(filters.VOICE, handle_voice_step),
            ],
            BLOCKED_ARCHETYPES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_step),
                MessageHandler(filters.VOICE, handle_voice_step),
            ],
            BLOCKED_CLAIMS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_step),
                MessageHandler(filters.VOICE, handle_voice_step),
            ],
            CTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_step),
                MessageHandler(filters.VOICE, handle_voice_step),
            ],
            APP_ICON: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_app_icon_upload),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_app_icon_text),
            ],
            VIDEO: [MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video)],
            DEMO_WALKTHROUGH: [
                MessageHandler(filters.VOICE, handle_demo_walkthrough_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_demo_walkthrough_text),
            ],
            EXTRA_PROJECT_CONTEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, finalize_submission),
                MessageHandler(filters.VOICE, handle_voice_step),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conversation)
    application.add_handler(CommandHandler("cancel", cancel))
    return application


def run_bot() -> None:
    SubmissionStorage().cleanup_old_submissions()
    application = build_application()
    application.run_polling(drop_pending_updates=True)
