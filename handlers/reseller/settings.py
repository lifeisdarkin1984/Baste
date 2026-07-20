"""
تنظیمات نماینده: کدهای تخفیف، رفرال، جوین اجباری، درخواست فروش شارژ/VPN.
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import execute
from services.referral_service import set_referral_enabled, set_referral_profit_percent, get_referral_settings
from services.forced_join_service import add_forced_channel, get_forced_channels
from utils.states import ResellerSettingsStates
from utils.keyboards import settings_submenu, back_to_reseller_menu_button

router = Router(name="reseller_settings")


@router.callback_query(F.data == "rmenu:settings")
async def settings_menu(callback: CallbackQuery, reseller_id: int):
    settings = await get_referral_settings(reseller_id)
    channels = await get_forced_channels(reseller_id)
    channels_text = "، ".join(c["channel_id"] for c in channels) if channels else "تنظیم نشده"
    await callback.message.edit_text(
        f"⚙️ تنظیمات\n\n"
        f"رفرال: {'فعال' if settings['is_enabled'] else 'غیرفعال'} ({settings['profit_percent']}٪)\n"
        f"کانال‌های جوین اجباری: {channels_text}",
        reply_markup=settings_submenu(settings["is_enabled"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:referral_set:"))
async def toggle_referral(callback: CallbackQuery, reseller_id: int):
    enable = callback.data.split(":")[2] == "on"
    await set_referral_enabled(reseller_id, enable)
    settings = await get_referral_settings(reseller_id)
    await callback.message.edit_text(
        f"رفرال {'فعال شد ✅' if enable else 'غیرفعال شد'}",
        reply_markup=settings_submenu(settings["is_enabled"]),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:referral_percent")
async def start_referral_percent(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ResellerSettingsStates.entering_referral_percent)
    await callback.message.answer("درصد سود رفرال را وارد کنید (مثال: 5):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerSettingsStates.entering_referral_percent)
async def receive_referral_percent(message: Message, state: FSMContext, reseller_id: int):
    try:
        percent = Decimal(message.text.strip())
    except InvalidOperation:
        await message.answer("فقط عدد وارد کنید.")
        return
    await set_referral_profit_percent(reseller_id, percent)
    await message.answer(f"درصد سود رفرال روی {percent}٪ تنظیم شد ✅", reply_markup=back_to_reseller_menu_button())
    await state.clear()


@router.callback_query(F.data == "settings:add_channel")
async def start_add_channel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ResellerSettingsStates.entering_channel_id)
    await callback.message.answer("آیدی کانال را وارد کنید (مثال: @mychannel):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerSettingsStates.entering_channel_id)
async def receive_channel_id(message: Message, state: FSMContext, reseller_id: int):
    channel_id = message.text.strip()
    await add_forced_channel(reseller_id, channel_id, set_by="reseller")
    await message.answer(f"کانال {channel_id} به لیست جوین اجباری اضافه شد ✅", reply_markup=back_to_reseller_menu_button())
    await state.clear()


# ---------- کد تخفیف (سه مرحله) ----------
@router.callback_query(F.data == "settings:add_discount")
async def start_add_discount(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ResellerSettingsStates.entering_discount_code)
    await callback.message.answer("کد تخفیف را وارد کنید (مثال: EID10):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerSettingsStates.entering_discount_code)
async def receive_discount_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip().upper())
    await state.set_state(ResellerSettingsStates.entering_discount_percent)
    await message.answer("درصد تخفیف را وارد کنید:")


@router.message(ResellerSettingsStates.entering_discount_percent)
async def receive_discount_percent(message: Message, state: FSMContext):
    try:
        percent = Decimal(message.text.strip())
    except InvalidOperation:
        await message.answer("فقط عدد وارد کنید.")
        return
    await state.update_data(percent=str(percent))
    await state.set_state(ResellerSettingsStates.entering_discount_usage_limit)
    await message.answer("سقف تعداد استفاده از این کد را وارد کنید:")


@router.message(ResellerSettingsStates.entering_discount_usage_limit)
async def receive_discount_usage_limit_and_save(message: Message, state: FSMContext, reseller_id: int):
    try:
        usage_limit = int(message.text.strip())
    except ValueError:
        await message.answer("فقط عدد وارد کنید.")
        return
    data = await state.get_data()
    await execute(
        "INSERT INTO discount_codes (reseller_id, code, percent, usage_limit) VALUES (%s, %s, %s, %s)",
        (reseller_id, data["code"], data["percent"], usage_limit),
    )
    await message.answer(f"کد تخفیف {data['code']} با {data['percent']}٪ تخفیف ثبت شد ✅", reply_markup=back_to_reseller_menu_button())
    await state.clear()


# ---------- آیدی پشتیبانی ----------
@router.callback_query(F.data == "settings:set_support_contact")
async def start_set_support_contact(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ResellerSettingsStates.entering_support_contact)
    await callback.message.answer(
        "آیدی/شماره پشتیبانی را وارد کنید (مثال: @my_support یا 09120000000):\n"
        "این دقیقاً همانی است که با دکمه‌ی «پشتیبانی» به مشتری نشان داده می‌شود.\n(برای انصراف /cancel)"
    )
    await callback.answer()


@router.message(ResellerSettingsStates.entering_support_contact)
async def receive_support_contact(message: Message, state: FSMContext, reseller_id: int):
    contact = message.text.strip()
    await execute("UPDATE resellers SET support_contact = %s WHERE id = %s", (contact, reseller_id))
    await message.answer(f"آیدی پشتیبانی روی «{contact}» تنظیم شد ✅", reply_markup=back_to_reseller_menu_button())
    await state.clear()
