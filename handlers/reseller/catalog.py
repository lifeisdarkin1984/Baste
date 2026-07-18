"""
هندلرهای مدیریت کاتالوگ نماینده — افزودن بسته با Sanity Check قیمت (بخش ۵).
"""
import uuid
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import execute
from services.sanity_check import is_price_suspicious
from utils.states import ResellerPackageStates
from utils.keyboards import sanity_check_confirm_buttons

router = Router(name="reseller_catalog")

# نگه‌داری موقت اطلاعات بسته در حال ثبت که هشدار قیمت گرفته (در حافظه؛ برای
# مقیاس کوچک فاز ۱ کافی است. جایگزین: ذخیره در FSM state).
_pending_price_confirmations: dict[str, dict] = {}


@router.message(ResellerPackageStates.entering_price)
async def receive_price(message: Message, state: FSMContext):
    try:
        sale_price = Decimal(message.text.replace(",", "").strip())
    except InvalidOperation:
        await message.answer("لطفاً فقط عدد وارد کنید. مثال درست: 100000")
        return

    data = await state.get_data()
    operator_name = data["operator_name"]

    if await is_price_suspicious(operator_name, sale_price):
        token = uuid.uuid4().hex[:8]
        _pending_price_confirmations[token] = {**data, "sale_price": sale_price}
        await state.set_state(ResellerPackageStates.confirming_suspicious_price)
        await message.answer(
            f"⚠️ این قیمت غیرعادی به نظر می‌رسه، مطمئنی؟\n"
            f"مبلغ واردشده: {sale_price:,.0f} تومان",
            reply_markup=sanity_check_confirm_buttons(token),
        )
        return

    await state.update_data(sale_price=str(sale_price))
    await state.set_state(ResellerPackageStates.entering_cost_price)
    await message.answer("قیمت تمام‌شده/خرید بسته را وارد کنید (فقط برای گزارش سود؛ به مشتری نشان داده نمی‌شود):")


@router.callback_query(F.data.startswith("price_confirm:"))
async def confirm_suspicious_price(callback: CallbackQuery, state: FSMContext):
    token = callback.data.split(":")[1]
    pending = _pending_price_confirmations.pop(token, None)
    if pending is None:
        await callback.answer("این درخواست منقضی شده، دوباره تلاش کنید.", show_alert=True)
        return

    await state.update_data(sale_price=str(pending["sale_price"]))
    await state.set_state(ResellerPackageStates.entering_cost_price)
    await callback.message.answer("قیمت تمام‌شده/خرید بسته را وارد کنید:")
    await callback.answer()


@router.callback_query(F.data.startswith("price_edit:"))
async def edit_suspicious_price(callback: CallbackQuery, state: FSMContext):
    token = callback.data.split(":")[1]
    _pending_price_confirmations.pop(token, None)
    await state.set_state(ResellerPackageStates.entering_price)
    await callback.message.answer("قیمت صحیح را دوباره وارد کنید:")
    await callback.answer()


@router.message(ResellerPackageStates.entering_cost_price)
async def receive_cost_price_and_save(message: Message, state: FSMContext, reseller_id: int):
    try:
        cost_price = Decimal(message.text.replace(",", "").strip())
    except InvalidOperation:
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return

    data = await state.get_data()
    await execute(
        "INSERT INTO packages (reseller_id, category_id, name, sale_price, cost_price, is_active) "
        "VALUES (%s, %s, %s, %s, %s, TRUE)",
        (reseller_id, data["category_id"], data["package_name"], data["sale_price"], cost_price),
    )
    await message.answer("بسته با موفقیت ثبت شد ✅")
    await state.clear()
