"""
هندلرهای مدیریت کاتالوگ نماینده — افزودن دسته/بسته با Sanity Check قیمت (بخش ۵).

طبق آپدیت جدید، کاتالوگ به دو بخش مجزا تقسیم شده:
  📦 بسته‌های اینترنتی (catalog_type='package')
  🔋 شارژ             (catalog_type='charge')
هر دو دقیقاً از همون ساختار پوشه‌ای دو سطحی استفاده می‌کنن (جدول‌های
categories/packages مشترک هستن، فقط با ستون catalog_type از هم جدا می‌شن):
  اپراتور (پوشه اصلی، parent_category_id = NULL)
    -> زیرپوشه (مثلاً «ماهانه» یا «هفتگی» برای بسته / یا «۲۰ هزار تومانی» برای شارژ)
        -> بسته‌ها یا محصولات شارژ (packages.category_id = آیدی زیرپوشه)

نوع کاتالوگ (catalog_type) همیشه به‌صورت پارامتر آخر callback_data پاس داده
می‌شه (مثلاً catalog:view:package یا catalog:view:charge) و در FSM هم ذخیره
می‌شه تا در مراحل بعدی (قیمت/قیمت تمام‌شده) گم نشه.
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
    catalog_type_menu,
    catalog_submenu,
    category_pick_buttons,
    operator_pick_buttons,
    back_to_reseller_menu_button,
)

router = Router(name="reseller_catalog")

_pending_price_confirmations: dict[str, dict] = {}

_TYPE_LABELS = {"package": "📦 بسته‌های اینترنتی", "charge": "🔋 شارژ"}


def _label(catalog_type: str) -> str:
    return _TYPE_LABELS.get(catalog_type, catalog_type)


@router.callback_query(F.data == "rmenu:catalog")
async def catalog_type_menu_cb(callback: CallbackQuery):
    await callback.message.edit_text("📦 کاتالوگ را انتخاب کنید:", reply_markup=catalog_type_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:menu:"))
async def catalog_menu(callback: CallbackQuery):
    catalog_type = callback.data.split(":")[2]
    await callback.message.edit_text(f"{_label(catalog_type)}", reply_markup=catalog_submenu(catalog_type))
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:view:"))
async def view_catalog(callback: CallbackQuery, reseller_id: int):
    catalog_type = callback.data.split(":")[2]
    operators = await fetch_all(
        "SELECT id, operator_name FROM categories WHERE reseller_id = %s AND parent_category_id IS NULL "
        "AND catalog_type = %s",
        (reseller_id, catalog_type),
    )
    if not operators:
        await callback.message.answer(
            "هنوز هیچ اپراتوری اضافه نکرده‌اید. اول از «📁 افزودن اپراتور» شروع کنید.",
            reply_markup=back_to_reseller_menu_button(),
        )
        await callback.answer()
        return

    for op in operators:
        subcategories = await fetch_all(
            "SELECT id, title FROM categories WHERE parent_category_id = %s", (op["id"],)
        )
        text = f"📁 {op['operator_name']}"
        if not subcategories:
            text += "\n  (هنوز زیرپوشه‌ای نداره)"
        else:
            for sub in subcategories:
                packages = await fetch_all(
                    "SELECT name, sale_price, is_active FROM packages WHERE category_id = %s", (sub["id"],)
                )
                text += f"\n  📂 {sub['title']}"
                if not packages:
                    text += "\n     (چیزی ثبت نشده)"
                else:
                    for p in packages:
                        mark = "✅" if p["is_active"] else "⛔️"
                        text += f"\n     - {p['name']}: {p['sale_price']:,.0f} تومان {mark}"
        await callback.message.answer(text)
    await callback.answer()


# ---------- افزودن اپراتور (پوشه اصلی) ----------
@router.callback_query(F.data.startswith("catalog:add_operator:"))
async def start_add_operator(callback: CallbackQuery, state: FSMContext):
    catalog_type = callback.data.split(":")[2]
    await state.update_data(catalog_type=catalog_type)
    await state.set_state(ResellerCategoryStates.entering_operator_name)
    await callback.message.answer("نام اپراتور را وارد کنید (مثال: ایرانسل):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCategoryStates.entering_operator_name)
async def receive_operator_name_and_save(message: Message, state: FSMContext, reseller_id: int):
    data = await state.get_data()
    catalog_type = data.get("catalog_type", "package")
    operator_name = message.text.strip()
    await execute(
        "INSERT INTO categories (reseller_id, operator_name, title, parent_category_id, catalog_type) "
        "VALUES (%s, %s, %s, NULL, %s)",
        (reseller_id, operator_name, operator_name, catalog_type),
    )
    await message.answer(
        f"پوشه‌ی اپراتور «{operator_name}» ساخته شد ✅\n"
        f"حالا از «📂 افزودن زیرپوشه» برای ساختن زیرپوشه داخلش استفاده کنید.",
        reply_markup=catalog_submenu(catalog_type),
    )
    await state.clear()


# ---------- افزودن زیرپوشه ----------
@router.callback_query(F.data.startswith("catalog:add_subcategory:"))
async def start_add_subcategory(callback: CallbackQuery, reseller_id: int):
    catalog_type = callback.data.split(":")[2]
    operators = await fetch_all(
        "SELECT id, operator_name FROM categories WHERE reseller_id = %s AND parent_category_id IS NULL "
        "AND catalog_type = %s",
        (reseller_id, catalog_type),
    )
    if not operators:
        await callback.message.answer(
            "اول باید یک اپراتور (پوشه اصلی) بسازید.", reply_markup=catalog_submenu(catalog_type)
        )
        await callback.answer()
        return
    await callback.message.answer(
        "زیرپوشه را برای کدام اپراتور می‌سازید؟",
        reply_markup=operator_pick_buttons(operators, purpose="sub", catalog_type=catalog_type),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:pick_operator_for_sub:"))
async def pick_operator_for_sub(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, operator_id = parts[2], int(parts[3])
    operator = await fetch_one("SELECT operator_name FROM categories WHERE id = %s", (operator_id,))
    await state.update_data(
        parent_operator_id=operator_id, operator_name=operator["operator_name"], catalog_type=catalog_type
    )
    await state.set_state(ResellerCategoryStates.entering_subcategory_title)
    await callback.message.answer(
        f"عنوان زیرپوشه‌ی «{operator['operator_name']}» را وارد کنید:\n(برای انصراف /cancel)"
    )
    await callback.answer()


@router.message(ResellerCategoryStates.entering_subcategory_title)
async def receive_subcategory_title_and_save(message: Message, state: FSMContext, reseller_id: int):
    data = await state.get_data()
    catalog_type = data.get("catalog_type", "package")
    title = message.text.strip()
    await execute(
        "INSERT INTO categories (reseller_id, operator_name, title, parent_category_id, catalog_type) "
        "VALUES (%s, %s, %s, %s, %s)",
        (reseller_id, data["operator_name"], title, data["parent_operator_id"], catalog_type),
    )
    await message.answer(
        f"زیرپوشه‌ی «{data['operator_name']} / {title}» ساخته شد ✅",
        reply_markup=catalog_submenu(catalog_type),
    )
    await state.clear()


# ---------- افزودن بسته/محصول ----------
@router.callback_query(F.data.startswith("catalog:add_package:"))
async def start_add_package(callback: CallbackQuery, reseller_id: int):
    catalog_type = callback.data.split(":")[2]
    operators = await fetch_all(
        "SELECT id, operator_name FROM categories WHERE reseller_id = %s AND parent_category_id IS NULL "
        "AND catalog_type = %s",
        (reseller_id, catalog_type),
    )
    if not operators:
        await callback.message.answer(
            "اول باید یک اپراتور (پوشه اصلی) بسازید.", reply_markup=catalog_submenu(catalog_type)
        )
        await callback.answer()
        return
    await callback.message.answer(
        "برای کدام اپراتور اضافه می‌کنید؟",
        reply_markup=operator_pick_buttons(operators, purpose="pkg", catalog_type=catalog_type),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:pick_operator_for_pkg:"))
async def pick_operator_for_pkg(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, operator_id = parts[2], int(parts[3])
    subcategories = await fetch_all(
        "SELECT id, title FROM categories WHERE parent_category_id = %s", (operator_id,)
    )
    if not subcategories:
        operator = await fetch_one("SELECT operator_name FROM categories WHERE id = %s", (operator_id,))
        await callback.message.answer(
            f"اپراتور «{operator['operator_name']}» هنوز زیرپوشه‌ای نداره.\n"
            f"اول از «📂 افزودن زیرپوشه» یکی بساز.",
            reply_markup=catalog_submenu(catalog_type),
        )
        await callback.answer()
        return
    await callback.message.answer(
        "زیرپوشه‌ی این محصول را انتخاب کنید:", reply_markup=category_pick_buttons(subcategories, catalog_type)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:pick_category:"))
async def pick_category(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, category_id = parts[2], int(parts[3])
    category = await fetch_one("SELECT operator_name FROM categories WHERE id = %s", (category_id,))
    await state.update_data(category_id=category_id, operator_name=category["operator_name"], catalog_type=catalog_type)
    await state.set_state(ResellerPackageStates.entering_name)
    name_hint = "نام بسته را وارد کنید (مثال: 7 گیگ هفتگی):" if catalog_type == "package" \
        else "نام محصول شارژ را وارد کنید (مثال: شارژ 20 هزار تومانی):"
    await callback.message.answer(f"{name_hint}\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerPackageStates.entering_name)
async def receive_package_name(message: Message, state: FSMContext):
    await state.update_data(package_name=message.text.strip())
    await state.set_state(ResellerPackageStates.entering_price)
    await message.answer("قیمت فروش را وارد کنید (فقط عدد، مثال: 65000):")


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
    await message.answer("قیمت تمام‌شده/خرید را وارد کنید (فقط برای گزارش سود؛ به مشتری نشان داده نمی‌شود):")


@router.callback_query(F.data.startswith("price_confirm:"))
async def confirm_suspicious_price(callback: CallbackQuery, state: FSMContext):
    token = callback.data.split(":")[1]
    pending = _pending_price_confirmations.pop(token, None)
    if pending is None:
        await callback.answer("این درخواست منقضی شده، دوباره تلاش کنید.", show_alert=True)
        return

    await state.update_data(sale_price=str(pending["sale_price"]))
    await state.set_state(ResellerPackageStates.entering_cost_price)
    await callback.message.answer("قیمت تمام‌شده/خرید را وارد کنید:")
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
    catalog_type = data.get("catalog_type", "package")
    await execute(
        "INSERT INTO packages (reseller_id, category_id, name, sale_price, cost_price, is_active) "
        "VALUES (%s, %s, %s, %s, %s, TRUE)",
        (reseller_id, data["category_id"], data["package_name"], data["sale_price"], cost_price),
    )
    label = "بسته" if catalog_type == "package" else "محصول شارژ"
    await message.answer(f"{label} با موفقیت ثبت شد ✅", reply_markup=catalog_submenu(catalog_type))
    await state.clear()
