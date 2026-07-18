"""
بک‌آپ و ریستور کامل از پنل مدیر کل (فاز ۳ اسپک).
ریستور به‌عمد در دو مرحله (آپلود فایل -> تأیید صریح با /confirm_restore) طراحی
شده تا از ریستور تصادفی/اشتباه جلوگیری شود، چون این عملیات کل دیتابیس را
جایگزین می‌کند.
"""
import os
import tempfile

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, FSInputFile

from services.backup_service import (
    save_backup_to_file,
    validate_backup_file,
    perform_safe_restore,
    BackupValidationError,
)
from database.db import execute

router = Router(name="admin_backup")

SAFETY_BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "_safety_backups")


class RestoreStates(StatesGroup):
    waiting_file = State()
    waiting_confirmation = State()


@router.message(Command("backup"))
async def take_backup(message: Message):
    with tempfile.TemporaryDirectory() as tmp_dir:
        filepath = os.path.join(tmp_dir, "backup.json")
        size_bytes = await save_backup_to_file(filepath)
        await execute(
            "INSERT INTO backup_logs (taken_by_telegram_id, file_size_bytes, note) VALUES (%s, %s, %s)",
            (message.from_user.id, size_bytes, "دستی از پنل مدیر کل"),
        )
        await message.answer_document(
            FSInputFile(filepath, filename="backup.json"),
            caption=f"بک‌آپ کامل گرفته شد ✅ ({size_bytes:,} بایت)\nاین فایل را در جای امنی نگه دارید.",
        )


@router.message(Command("restore"))
async def start_restore(message: Message, state: FSMContext):
    await state.set_state(RestoreStates.waiting_file)
    await message.answer(
        "⚠️ توجه: ریستور کل دیتابیس فعلی را با محتوای فایل بک‌آپ جایگزین می‌کند.\n"
        "فایل backup.json را همینجا ارسال کنید."
    )


@router.message(RestoreStates.waiting_file, F.document)
async def receive_restore_file(message: Message, state: FSMContext):
    file = await message.bot.get_file(message.document.file_id)
    persisted_path = os.path.join(tempfile.gettempdir(), f"pending_restore_{message.from_user.id}.json")
    await message.bot.download_file(file.file_path, destination=persisted_path)

    try:
        data = validate_backup_file(persisted_path)
    except BackupValidationError as e:
        os.remove(persisted_path)
        await message.answer(f"⛔️ فایل نامعتبر: {e}\nریستور لغو شد.")
        await state.clear()
        return

    table_counts = {t: len(rows) for t, rows in data["tables"].items()}
    await state.update_data(restore_filepath=persisted_path)
    await state.set_state(RestoreStates.waiting_confirmation)

    summary = "\n".join(f"- {t}: {c} ردیف" for t, c in table_counts.items() if c > 0)
    await message.answer(
        f"فایل معتبر است ✅ خلاصه محتوا:\n{summary}\n\n"
        f"قبل از ریستور، یک بک‌آپ ایمنی از وضعیت فعلی گرفته می‌شود.\n"
        f"برای تأیید نهایی ریستور: /confirm_restore\nبرای لغو: /cancel_restore"
    )


@router.message(RestoreStates.waiting_confirmation, Command("confirm_restore"))
async def confirm_restore(message: Message, state: FSMContext):
    data = await state.get_data()
    filepath = data["restore_filepath"]

    try:
        safety_path = await perform_safe_restore(filepath, SAFETY_BACKUP_DIR)
    except BackupValidationError as e:
        await message.answer(f"⛔️ خطا: {e}")
        await state.clear()
        return
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

    await message.answer(
        f"ریستور با موفقیت انجام شد ✅\n"
        f"بک‌آپ ایمنی وضعیت قبلی در مسیر زیر روی سرور ذخیره شد:\n{safety_path}"
    )
    await state.clear()


@router.message(RestoreStates.waiting_confirmation, Command("cancel_restore"))
async def cancel_restore(message: Message, state: FSMContext):
    data = await state.get_data()
    filepath = data.get("restore_filepath")
    if filepath and os.path.exists(filepath):
        os.remove(filepath)
    await state.clear()
    await message.answer("ریستور لغو شد.")
