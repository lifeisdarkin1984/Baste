"""
بک‌آپ و ریستور کامل از پنل مدیر کل (فاز ۳ اسپک) — فاز ۲ پروژه‌ی دکمه‌ای‌سازی.
ریستور همچنان در دو مرحله (آپلود فایل -> تأیید صریح با دکمه) طراحی شده تا از
ریستور تصادفی/اشتباه جلوگیری شود، چون این عملیات کل دیتابیس را جایگزین می‌کند.
"""
import os
import tempfile

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, FSInputFile

from services.backup_service import (
    save_backup_to_file,
    validate_backup_file,
    perform_safe_restore,
    BackupValidationError,
)
from database.db import execute
from utils.keyboards import admin_backup_submenu, restore_confirm_buttons, back_to_admin_menu_button

router = Router(name="admin_backup")

SAFETY_BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "_safety_backups")


class RestoreStates(StatesGroup):
    waiting_file = State()
    waiting_confirmation = State()


@router.callback_query(F.data == "amenu:backup")
async def backup_menu(callback: CallbackQuery):
    await callback.message.edit_text("🗄 بک‌آپ و ریستور", reply_markup=admin_backup_submenu())
    await callback.answer()


@router.callback_query(F.data == "backup_take")
async def take_backup_cb(callback: CallbackQuery):
    with tempfile.TemporaryDirectory() as tmp_dir:
        filepath = os.path.join(tmp_dir, "backup.json")
        size_bytes = await save_backup_to_file(filepath)
        await execute(
            "INSERT INTO backup_logs (taken_by_telegram_id, file_size_bytes, note) VALUES (%s, %s, %s)",
            (callback.from_user.id, size_bytes, "دستی از پنل مدیر کل"),
        )
        await callback.message.answer_document(
            FSInputFile(filepath, filename="backup.json"),
            caption=f"بک‌آپ کامل گرفته شد ✅ ({size_bytes:,} بایت)\nاین فایل را در جای امنی نگه دارید.",
            reply_markup=back_to_admin_menu_button(),
        )
    await callback.answer()


@router.callback_query(F.data == "backup_restore_start")
async def start_restore_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RestoreStates.waiting_file)
    await callback.message.answer(
        "⚠️ توجه: ریستور کل دیتابیس فعلی را با محتوای فایل بک‌آپ جایگزین می‌کند.\n"
        "فایل backup.json را همینجا ارسال کنید.\n(برای انصراف /cancel)"
    )
    await callback.answer()


@router.message(RestoreStates.waiting_file, F.document)
async def receive_restore_file(message: Message, state: FSMContext):
    file = await message.bot.get_file(message.document.file_id)
    persisted_path = os.path.join(tempfile.gettempdir(), f"pending_restore_{message.from_user.id}.json")
    await message.bot.download_file(file.file_path, destination=persisted_path)

    try:
        data = validate_backup_file(persisted_path)
    except BackupValidationError as e:
        os.remove(persisted_path)
        await message.answer(f"⛔️ فایل نامعتبر: {e}\nریستور لغو شد.", reply_markup=back_to_admin_menu_button())
        await state.clear()
        return

    table_counts = {t: len(rows) for t, rows in data["tables"].items()}
    await state.update_data(restore_filepath=persisted_path)
    await state.set_state(RestoreStates.waiting_confirmation)

    summary = "\n".join(f"- {t}: {c} ردیف" for t, c in table_counts.items() if c > 0)
    await message.answer(
        f"فایل معتبر است ✅ خلاصه محتوا:\n{summary}\n\n"
        f"قبل از ریستور، یک بک‌آپ ایمنی از وضعیت فعلی گرفته می‌شود.",
        reply_markup=restore_confirm_buttons(),
    )


@router.callback_query(RestoreStates.waiting_confirmation, F.data == "restore_confirm")
async def confirm_restore_cb(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filepath = data["restore_filepath"]

    try:
        safety_path = await perform_safe_restore(filepath, SAFETY_BACKUP_DIR)
    except BackupValidationError as e:
        await callback.message.answer(f"⛔️ خطا: {e}", reply_markup=back_to_admin_menu_button())
        await state.clear()
        await callback.answer()
        return
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

    await callback.message.edit_text(
        f"ریستور با موفقیت انجام شد ✅\n"
        f"بک‌آپ ایمنی وضعیت قبلی در مسیر زیر روی سرور ذخیره شد:\n{safety_path}"
    )
    await state.clear()
    await callback.answer()


@router.callback_query(RestoreStates.waiting_confirmation, F.data == "restore_cancel")
async def cancel_restore_cb(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filepath = data.get("restore_filepath")
    if filepath and os.path.exists(filepath):
        os.remove(filepath)
    await state.clear()
    await callback.message.edit_text("ریستور لغو شد.")
    await callback.answer()
