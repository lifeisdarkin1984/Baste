"""
نقطه‌ی ورود پنل نماینده (بخش ۷ اسپک).

باید تو handlers/reseller/__init__.py قبل از بقیه‌ی روترهای نماینده رجیستر
بشه، وگرنه هندلر /start مشتری (handlers/customer/orders.py) این پیام رو
می‌قاپه و صاحب نماینده رو هم به‌عنوان مشتری معمولی می‌بینه.

هر دکمه‌ی منو (rmenu:catalog / rmenu:orders / ...) توسط خودِ فایل مربوطه
(catalog.py / orders.py / wallet.py / ...) هندل می‌شود، نه اینجا — این فایل
فقط نقطه‌ی ورود و برگشت به منوی اصلی (rmenu:home) را مدیریت می‌کند.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import fetch_one
from utils.keyboards import reseller_main_menu

router = Router(name="reseller_start")


async def _is_reseller_owner(reseller_id: int, telegram_user_id: int) -> bool:
    row = await fetch_one(
        "SELECT id FROM resellers WHERE id = %s AND telegram_numeric_id = %s",
        (reseller_id, telegram_user_id),
    )
    return row is not None


@router.message(F.text.startswith("/start"))
async def reseller_start(message: Message, reseller_id: int):
    if not await _is_reseller_owner(reseller_id, message.from_user.id):
        return  # مشتری معمولی — بگذار روتر مشتری این پیام را بگیرد

    await message.answer(
        "👋 به پنل نماینده خوش آمدید.\n\n"
        "از دکمه‌های زیر برای مدیریت کسب‌وکارتان استفاده کنید:",
        reply_markup=reseller_main_menu(),
    )


@router.message(F.text == "/cancel")
async def reseller_cancel(message: Message, state: FSMContext, reseller_id: int):
    if not await _is_reseller_owner(reseller_id, message.from_user.id):
        return
    current = await state.get_state()
    if current is None:
        await message.answer("در حال حاضر در هیچ فرآیندی نیستید.")
        return
    await state.clear()
    await message.answer("فرآیند لغو شد.", reply_markup=reseller_main_menu())


@router.callback_query(F.data == "rmenu:home")
async def back_home(callback: CallbackQuery):
    await callback.message.edit_text(
        "👋 پنل نماینده\n\nاز دکمه‌های زیر استفاده کنید.",
        reply_markup=reseller_main_menu(),
    )
    await callback.answer()
