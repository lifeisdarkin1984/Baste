"""
هندلرهای مدیریت کاتالوگ نماینده — افزودن دسته/بسته با Sanity Check قیمت (بخش ۵).

نکته‌ی مهم فاز ۳: قبلاً هیچ نقطه‌ی ورودی برای شروع «افزودن بسته» وجود نداشت
(state entering_price هرگز از جایی set نمی‌شد) — یعنی نماینده اصلاً راهی
برای ساختن کاتالوگ نداشت. این فایل آن نقطه‌ی ورود (افزودن دسته‌بندی + انتخاب
دسته + وارد کردن نام بسته) را اضافه می‌کند و به state entering_price موجود
وصل می‌شود.
"""
import uuid
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import execute, fetch_all, fetch_one
from services.sanity_check import is_price_suspicious
from utils.states import ResellerPackageStates, ResellerCategoryStates
from utils.keyboards import (
    sanity_check_confirm_buttons,
    catalog_submenu,
    category_pick_buttons,
    back_to_reseller_menu_button,
)

router = Router(name="reseller_catalog")

_pending_price_confirmations: dict[str, dict] = {}


@router.callback_query(F.data == "rmenu:catalog")
async def catalog_menu(callback: CallbackQuery):
    await callback.message.edit_text("📦 کاتالوگ", reply_markup=catalog_submenu())
    await callback.answer()


@router.callback_query(F.data == "catalog:view")
async def view_catalog(callback: CallbackQuery, reseller_id: int):
    categories = await fetch_all(
        "SELECT id, operator_name, title FROM categories WHERE reseller_id = %s", (reseller_id,)
    )
    if not categories:
        await callback.message.answer("هنوز هیچ دسته‌بندی‌ای اضافه نکرده‌اید.", reply_markup=back_to_reseller_menu_button())
        await callback.answer()
        return
    for c in categories:
        packages = await fetch_all(
            "SELECT name, sale_price, is_active FROM packages WHERE category_id = %s", (c["id"],)
        )
        if not packages:
            text = f"📁 {c['operator_name']} - {c['title']}\n(بسته‌ای ثبت نشده)"
        else:
            lines = [f"- {p['name']}: {p['sale_price']:,.0f} تومان {'✅' if p['is_active'] else '⛔️'}" for p in packages]
            text = f"📁 {c['operator_name']} - {c['title']}\n" + "\n".join(lines)
        await callback.message.answer(text)
    await callback.answer()


# ---------- افزودن دسته‌بندی ----------
@router.callback_query(F.data == "catalog:add_category")
async def start_add_category(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ResellerCategoryStates.entering_operator_name)
    await callback.message.answer("نام اپراتور را وارد کنید (مثال: ایرانسل):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCategoryStates.entering_operator_name)
async def receive_operator_name(message: Message, state: FSMContext):
    await state.update_data(operator_name=message.text.strip())
    await state.set_state(ResellerCategoryStates.entering_title)
    await message.answer("عنوان دسته‌بندی را وارد کنید (مثال: هفتگی):")


@router.message(ResellerCategoryStates.entering_title)
async def receive_category_title_and_save(message: Message, state: FSMContext, reseller_id: int):
    data = await state.get_data()
    await execute(
        "INSERT INTO categories (reseller_id, operator_name, title) VALUES (%s, %s, %s)",
        (reseller_id, data["operator_name"], message.text.strip()),
    )
    await message.answer(
        f"دسته‌بندی «{data['operator_name']} - {message.text.strip()}» ساخته شد ✅",
        reply_markup=catalog_submenu(),
    )
    await state.clear()


# ---------- افزودن بسته ----------
@router.callback_query(F.data == "catalog:add_package")
async def start_add_package(callback: CallbackQuery, reseller_id: int):
    categories = await fetch_all(
        "SELECT id, operator_name, title FROM categories WHERE reseller_id = %s", (reseller_id,)
    )
    if not categories:
        await callback.message.answer(
            "اول باید یک دسته‌بندی بسازید.", reply_markup=catalog_submenu()
        )
        await callback.answer()
        return
    await callback.message.answer("دسته‌بندی این بسته را انتخاب کنید:", reply_markup=category_pick_buttons(categories))
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:pick_category:"))
async def pick_category(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split(":")[2])
    category = await fetch_one("SELECT operator_name FROM categories WHERE id = %s", (category_id,))
    await state.update_data(category_id=category_id, operator_name=category["operator_name"])
    await state.set_state(ResellerPackageStates.entering_name)
    await callback.message.answer("نام بسته را وارد کنید (مثال: 7 گیگ هفتگی):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerPackageStates.entering_name)
async def receive_package_name(message: Message, state: FSMContext):
    await state.update_data(package_name=message.text.strip())
    await state.set_state(ResellerPackageStates.entering_price)
    await message.answer("قیمت فروش بسته را وارد کنید (فقط عدد، مثال: 65000):")


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
    await message.answer("بسته با موفقیت ثبت شد ✅", reply_markup=catalog_submenu())
    await state.clear()
