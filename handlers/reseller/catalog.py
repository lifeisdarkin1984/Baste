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

import aiomysql
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import execute, fetch_all, fetch_one, transaction
from services.sanity_check import is_price_suspicious
from utils.states import ResellerPackageStates, ResellerCategoryStates, ResellerCatalogEditStates
from utils.keyboards import (
    sanity_check_confirm_buttons,
    catalog_type_menu,
    catalog_submenu,
    category_pick_buttons,
    operator_pick_buttons,
    back_to_reseller_menu_button,
    catalog_manage_operator_pick_buttons,
    catalog_operator_manage_buttons,
    catalog_subcategory_manage_buttons,
    catalog_package_manage_buttons,
    catalog_delete_confirm_buttons,
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

    if pending.get("is_edit"):
        package_id = pending["edit_package_id"]
        sale_price = pending["sale_price"]
        await execute("UPDATE packages SET sale_price = %s WHERE id = %s", (sale_price, package_id))
        await state.clear()
        await callback.message.answer(f"قیمت فروش به {sale_price:,.0f} تومان تغییر کرد ✅")
        await _send_package_manage_message(callback.message, pending["catalog_type"], package_id)
        await callback.answer()
        return

    await state.update_data(sale_price=str(pending["sale_price"]))
    await state.set_state(ResellerPackageStates.entering_cost_price)
    await callback.message.answer("قیمت تمام‌شده/خرید را وارد کنید:")
    await callback.answer()


@router.callback_query(F.data.startswith("price_edit:"))
async def edit_suspicious_price(callback: CallbackQuery, state: FSMContext):
    token = callback.data.split(":")[1]
    pending = _pending_price_confirmations.pop(token, None)
    if pending and pending.get("is_edit"):
        await state.update_data(catalog_type=pending["catalog_type"], edit_package_id=pending["edit_package_id"])
        await state.set_state(ResellerCatalogEditStates.editing_package_price)
        await callback.message.answer("قیمت فروش صحیح را دوباره وارد کنید:")
        await callback.answer()
        return
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


# ==========================================================================
# مدیریت/ویرایش/حذف پوشه‌ها و محصولات (بخش جدید طبق درخواست).
#
# نکته‌ی مهم درباره‌ی حذف: categories.parent_category_id فقط ON DELETE SET
# NULL است (نه CASCADE)، پس هیچ‌وقت مستقیم اپراتور را DELETE نمی‌کنیم؛ اول
# دستی محصولات هر زیرپوشه، بعد خود زیرپوشه‌ها، بعد خود اپراتور حذف می‌شود.
# packages.category_id و charge_codes.package_id واقعاً CASCADE هستند (اوکیه).
# orders.package_id RESTRICT است؛ اگر محصولی سابقه‌ی فروش داشته باشد، همان
# دستور DELETE FROM packages با IntegrityError شکست می‌خورد و کل تراکنش
# rollback می‌شود (طبق درخواست: fail امن، نه پاک‌شدن جزئی).
# ==========================================================================

async def _count_available_codes(package_ids: list[int]) -> int:
    if not package_ids:
        return 0
    placeholders = ",".join(["%s"] * len(package_ids))
    row = await fetch_one(
        f"SELECT COUNT(*) AS c FROM charge_codes WHERE package_id IN ({placeholders}) AND status = 'available'",
        tuple(package_ids),
    )
    return row["c"] if row else 0


async def _operator_delete_counts(operator_id: int) -> dict:
    subs = await fetch_all("SELECT id FROM categories WHERE parent_category_id = %s", (operator_id,))
    sub_ids = [s["id"] for s in subs]
    pkg_ids: list[int] = []
    if sub_ids:
        placeholders = ",".join(["%s"] * len(sub_ids))
        pkgs = await fetch_all(f"SELECT id FROM packages WHERE category_id IN ({placeholders})", tuple(sub_ids))
        pkg_ids = [p["id"] for p in pkgs]
    return {
        "subcategories": len(sub_ids),
        "packages": len(pkg_ids),
        "codes": await _count_available_codes(pkg_ids),
    }


async def _subcategory_delete_counts(sub_id: int) -> dict:
    pkgs = await fetch_all("SELECT id FROM packages WHERE category_id = %s", (sub_id,))
    pkg_ids = [p["id"] for p in pkgs]
    return {"packages": len(pkg_ids), "codes": await _count_available_codes(pkg_ids)}


async def _package_delete_counts(package_id: int) -> dict:
    return {"codes": await _count_available_codes([package_id])}


async def _delete_operator_cascade(operator_id: int) -> None:
    async with transaction() as conn:
        cur = await conn.cursor()
        await cur.execute("SELECT id FROM categories WHERE parent_category_id = %s", (operator_id,))
        sub_ids = [row[0] for row in await cur.fetchall()]
        for sub_id in sub_ids:
            await cur.execute("DELETE FROM packages WHERE category_id = %s", (sub_id,))
        for sub_id in sub_ids:
            await cur.execute("DELETE FROM categories WHERE id = %s", (sub_id,))
        await cur.execute("DELETE FROM categories WHERE id = %s", (operator_id,))


async def _delete_subcategory_cascade(sub_id: int) -> None:
    async with transaction() as conn:
        cur = await conn.cursor()
        await cur.execute("DELETE FROM packages WHERE category_id = %s", (sub_id,))
        await cur.execute("DELETE FROM categories WHERE id = %s", (sub_id,))


async def _delete_package_cascade(package_id: int) -> None:
    async with transaction() as conn:
        cur = await conn.cursor()
        await cur.execute("DELETE FROM packages WHERE id = %s", (package_id,))


async def _show_operator_manage_screen(callback: CallbackQuery, catalog_type: str, operator_id: int):
    operator = await fetch_one("SELECT operator_name FROM categories WHERE id = %s", (operator_id,))
    if operator is None:
        await callback.message.answer("این اپراتور دیگر وجود ندارد.", reply_markup=catalog_submenu(catalog_type))
        return
    subcategories = await fetch_all(
        "SELECT id, title FROM categories WHERE parent_category_id = %s", (operator_id,)
    )
    await callback.message.answer(
        f"📁 {operator['operator_name']}\n"
        f"زیرپوشه‌ها را برای مدیریت انتخاب کنید یا خودِ اپراتور را ویرایش/حذف کنید:",
        reply_markup=catalog_operator_manage_buttons(catalog_type, operator_id, subcategories),
    )


async def _show_subcategory_manage_screen(callback: CallbackQuery, catalog_type: str, sub_id: int):
    sub = await fetch_one("SELECT title, parent_category_id FROM categories WHERE id = %s", (sub_id,))
    if sub is None:
        await callback.message.answer("این زیرپوشه دیگر وجود ندارد.", reply_markup=catalog_submenu(catalog_type))
        return
    packages = await fetch_all(
        "SELECT id, name, is_active FROM packages WHERE category_id = %s", (sub_id,)
    )
    await callback.message.answer(
        f"📂 {sub['title']}\n"
        f"محصولات را برای مدیریت انتخاب کنید یا خودِ زیرپوشه را ویرایش/حذف کنید:",
        reply_markup=catalog_subcategory_manage_buttons(catalog_type, sub_id, sub["parent_category_id"], packages),
    )


async def _send_package_manage_message(message: Message, catalog_type: str, package_id: int):
    package = await fetch_one(
        "SELECT name, sale_price, cost_price, is_active, category_id FROM packages WHERE id = %s", (package_id,)
    )
    if package is None:
        return
    status = "✅ فعال" if package["is_active"] else "⛔️ غیرفعال"
    cost = f"{package['cost_price']:,.0f} تومان" if package["cost_price"] is not None else "ثبت نشده"
    await message.answer(
        f"{package['name']}\n"
        f"قیمت فروش: {package['sale_price']:,.0f} تومان\n"
        f"قیمت خرید: {cost}\n"
        f"وضعیت: {status}",
        reply_markup=catalog_package_manage_buttons(catalog_type, package_id, package["category_id"], package["is_active"]),
    )


async def _show_package_manage_screen(callback: CallbackQuery, catalog_type: str, package_id: int):
    await _send_package_manage_message(callback.message, catalog_type, package_id)


# ---------- ورود به مدیریت: انتخاب اپراتور ----------
@router.callback_query(F.data.startswith("catalog:manage:"))
async def manage_pick_operator(callback: CallbackQuery, reseller_id: int):
    catalog_type = callback.data.split(":")[2]
    operators = await fetch_all(
        "SELECT id, operator_name FROM categories WHERE reseller_id = %s AND parent_category_id IS NULL "
        "AND catalog_type = %s",
        (reseller_id, catalog_type),
    )
    if not operators:
        await callback.message.answer(
            "هنوز هیچ اپراتوری اضافه نکرده‌اید.", reply_markup=catalog_submenu(catalog_type)
        )
        await callback.answer()
        return
    await callback.message.answer(
        "کدام اپراتور را می‌خواهید مدیریت کنید؟",
        reply_markup=catalog_manage_operator_pick_buttons(operators, catalog_type),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:manage_op:"))
async def manage_operator_screen(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, operator_id = parts[2], int(parts[3])
    await _show_operator_manage_screen(callback, catalog_type, operator_id)
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:manage_sub:"))
async def manage_subcategory_screen(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, sub_id = parts[2], int(parts[3])
    await _show_subcategory_manage_screen(callback, catalog_type, sub_id)
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:manage_pkg:"))
async def manage_package_screen(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    await _show_package_manage_screen(callback, catalog_type, package_id)
    await callback.answer()


# ---------- ویرایش اپراتور (نام) ----------
@router.callback_query(F.data.startswith("catalog:edit_op:"))
async def start_edit_operator(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, operator_id = parts[2], int(parts[3])
    await state.update_data(catalog_type=catalog_type, edit_operator_id=operator_id)
    await state.set_state(ResellerCatalogEditStates.editing_operator_name)
    await callback.message.answer("نام جدید اپراتور را وارد کنید:\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCatalogEditStates.editing_operator_name)
async def receive_edit_operator_name(message: Message, state: FSMContext):
    data = await state.get_data()
    catalog_type = data["catalog_type"]
    operator_id = data["edit_operator_id"]
    new_name = message.text.strip()
    await execute(
        "UPDATE categories SET operator_name = %s, title = %s WHERE id = %s",
        (new_name, new_name, operator_id),
    )
    await state.clear()
    await message.answer(f"نام اپراتور به «{new_name}» تغییر کرد ✅")
    subcategories = await fetch_all(
        "SELECT id, title FROM categories WHERE parent_category_id = %s", (operator_id,)
    )
    await message.answer(
        f"📁 {new_name}",
        reply_markup=catalog_operator_manage_buttons(catalog_type, operator_id, subcategories),
    )


# ---------- ویرایش زیرپوشه (عنوان) ----------
@router.callback_query(F.data.startswith("catalog:edit_sub:"))
async def start_edit_subcategory(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, sub_id = parts[2], int(parts[3])
    await state.update_data(catalog_type=catalog_type, edit_sub_id=sub_id)
    await state.set_state(ResellerCatalogEditStates.editing_subcategory_title)
    await callback.message.answer("عنوان جدید زیرپوشه را وارد کنید:\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCatalogEditStates.editing_subcategory_title)
async def receive_edit_subcategory_title(message: Message, state: FSMContext):
    data = await state.get_data()
    catalog_type = data["catalog_type"]
    sub_id = data["edit_sub_id"]
    new_title = message.text.strip()
    await execute("UPDATE categories SET title = %s WHERE id = %s", (new_title, sub_id))
    await state.clear()
    await message.answer(f"عنوان زیرپوشه به «{new_title}» تغییر کرد ✅")
    sub = await fetch_one("SELECT parent_category_id FROM categories WHERE id = %s", (sub_id,))
    packages = await fetch_all("SELECT id, name, is_active FROM packages WHERE category_id = %s", (sub_id,))
    await message.answer(
        f"📂 {new_title}",
        reply_markup=catalog_subcategory_manage_buttons(catalog_type, sub_id, sub["parent_category_id"], packages),
    )


# ---------- ویرایش محصول (نام / قیمت فروش / قیمت خرید) ----------
@router.callback_query(F.data.startswith("catalog:edit_pkg_name:"))
async def start_edit_package_name(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    await state.update_data(catalog_type=catalog_type, edit_package_id=package_id)
    await state.set_state(ResellerCatalogEditStates.editing_package_name)
    await callback.message.answer("نام جدید را وارد کنید:\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCatalogEditStates.editing_package_name)
async def receive_edit_package_name(message: Message, state: FSMContext):
    data = await state.get_data()
    package_id = data["edit_package_id"]
    new_name = message.text.strip()
    await execute("UPDATE packages SET name = %s WHERE id = %s", (new_name, package_id))
    await state.clear()
    await message.answer(f"نام به «{new_name}» تغییر کرد ✅")
    await _send_package_manage_message(message, data["catalog_type"], package_id)


@router.callback_query(F.data.startswith("catalog:edit_pkg_price:"))
async def start_edit_package_price(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    await state.update_data(catalog_type=catalog_type, edit_package_id=package_id)
    await state.set_state(ResellerCatalogEditStates.editing_package_price)
    await callback.message.answer("قیمت فروش جدید را وارد کنید (فقط عدد):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCatalogEditStates.editing_package_price)
async def receive_edit_package_price(message: Message, state: FSMContext):
    try:
        sale_price = Decimal(message.text.replace(",", "").strip())
    except InvalidOperation:
        await message.answer("لطفاً فقط عدد وارد کنید. مثال درست: 100000")
        return

    data = await state.get_data()
    package_id = data["edit_package_id"]
    package = await fetch_one(
        "SELECT c.operator_name FROM packages p JOIN categories c ON c.id = p.category_id WHERE p.id = %s",
        (package_id,),
    )
    operator_name = package["operator_name"] if package else ""

    if await is_price_suspicious(operator_name, sale_price):
        token = uuid.uuid4().hex[:8]
        _pending_price_confirmations[token] = {**data, "sale_price": sale_price, "is_edit": True}
        await state.set_state(ResellerCatalogEditStates.confirming_suspicious_edit_price)
        await message.answer(
            f"⚠️ این قیمت غیرعادی به نظر می‌رسه، مطمئنی؟\n"
            f"مبلغ واردشده: {sale_price:,.0f} تومان",
            reply_markup=sanity_check_confirm_buttons(token),
        )
        return

    await execute("UPDATE packages SET sale_price = %s WHERE id = %s", (sale_price, package_id))
    await state.clear()
    await message.answer(f"قیمت فروش به {sale_price:,.0f} تومان تغییر کرد ✅")
    await _send_package_manage_message(message, data["catalog_type"], package_id)


@router.callback_query(F.data.startswith("catalog:edit_pkg_cost:"))
async def start_edit_package_cost(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    await state.update_data(catalog_type=catalog_type, edit_package_id=package_id)
    await state.set_state(ResellerCatalogEditStates.editing_package_cost)
    await callback.message.answer("قیمت خرید/تمام‌شده جدید را وارد کنید (فقط عدد):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCatalogEditStates.editing_package_cost)
async def receive_edit_package_cost(message: Message, state: FSMContext):
    try:
        cost_price = Decimal(message.text.replace(",", "").strip())
    except InvalidOperation:
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return

    data = await state.get_data()
    package_id = data["edit_package_id"]
    await execute("UPDATE packages SET cost_price = %s WHERE id = %s", (cost_price, package_id))
    await state.clear()
    await message.answer(f"قیمت خرید به {cost_price:,.0f} تومان تغییر کرد ✅")
    await _send_package_manage_message(message, data["catalog_type"], package_id)


# ---------- فعال‌سازی/غیرفعال‌سازی محصول ----------
@router.callback_query(F.data.startswith("catalog:toggle_pkg:"))
async def toggle_package_active(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    package = await fetch_one("SELECT is_active FROM packages WHERE id = %s", (package_id,))
    if package is None:
        await callback.answer("این محصول دیگر وجود ندارد.", show_alert=True)
        return
    new_status = not package["is_active"]
    await execute("UPDATE packages SET is_active = %s WHERE id = %s", (new_status, package_id))
    await _show_package_manage_screen(callback, catalog_type, package_id)
    await callback.answer("وضعیت به‌روزرسانی شد.")


# ---------- حذف (با تأییدیه + شمارش دقیق قبلش) ----------
@router.callback_query(F.data.startswith("catalog:del_op:"))
async def ask_delete_operator(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, operator_id = parts[2], int(parts[3])
    operator = await fetch_one("SELECT operator_name FROM categories WHERE id = %s", (operator_id,))
    if operator is None:
        await callback.answer("این اپراتور دیگر وجود ندارد.", show_alert=True)
        return
    counts = await _operator_delete_counts(operator_id)
    lines = [
        f"⚠️ با حذف اپراتور «{operator['operator_name']}»:",
        f"- {counts['subcategories']} زیرپوشه",
        f"- {counts['packages']} محصول",
    ]
    if catalog_type == "charge":
        lines.append(f"- {counts['codes']} کد شارژِ موجود (فروخته‌نشده)")
    lines.append("برای همیشه پاک می‌شوند. مطمئنید؟")
    await callback.message.answer("\n".join(lines), reply_markup=catalog_delete_confirm_buttons("op", catalog_type, operator_id))
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:del_sub:"))
async def ask_delete_subcategory(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, sub_id = parts[2], int(parts[3])
    sub = await fetch_one("SELECT title FROM categories WHERE id = %s", (sub_id,))
    if sub is None:
        await callback.answer("این زیرپوشه دیگر وجود ندارد.", show_alert=True)
        return
    counts = await _subcategory_delete_counts(sub_id)
    lines = [f"⚠️ با حذف زیرپوشه‌ی «{sub['title']}»:", f"- {counts['packages']} محصول"]
    if catalog_type == "charge":
        lines.append(f"- {counts['codes']} کد شارژِ موجود (فروخته‌نشده)")
    lines.append("برای همیشه پاک می‌شوند. مطمئنید؟")
    await callback.message.answer("\n".join(lines), reply_markup=catalog_delete_confirm_buttons("sub", catalog_type, sub_id))
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:del_pkg:"))
async def ask_delete_package(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    package = await fetch_one("SELECT name FROM packages WHERE id = %s", (package_id,))
    if package is None:
        await callback.answer("این محصول دیگر وجود ندارد.", show_alert=True)
        return
    lines = [f"⚠️ با حذف «{package['name']}»:"]
    if catalog_type == "charge":
        counts = await _package_delete_counts(package_id)
        lines.append(f"- {counts['codes']} کد شارژِ موجود (فروخته‌نشده)")
    lines.append("این عملیات قابل بازگشت نیست. مطمئنید؟")
    await callback.message.answer("\n".join(lines), reply_markup=catalog_delete_confirm_buttons("pkg", catalog_type, package_id))
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:delno:"))
async def cancel_delete(callback: CallbackQuery):
    parts = callback.data.split(":")
    kind, catalog_type, item_id = parts[2], parts[3], int(parts[4])
    if kind == "op":
        await _show_operator_manage_screen(callback, catalog_type, item_id)
    elif kind == "sub":
        await _show_subcategory_manage_screen(callback, catalog_type, item_id)
    else:
        await _show_package_manage_screen(callback, catalog_type, item_id)
    await callback.answer("حذف لغو شد.")


@router.callback_query(F.data.startswith("catalog:delyes:"))
async def confirm_delete(callback: CallbackQuery):
    parts = callback.data.split(":")
    kind, catalog_type, item_id = parts[2], parts[3], int(parts[4])

    try:
        if kind == "op":
            operator = await fetch_one("SELECT operator_name FROM categories WHERE id = %s", (item_id,))
            await _delete_operator_cascade(item_id)
            await callback.message.answer(f"اپراتور «{operator['operator_name']}» و همه‌ی زیرمجموعه‌هایش حذف شد ✅")
            await callback.message.answer("📦 کاتالوگ", reply_markup=catalog_submenu(catalog_type))

        elif kind == "sub":
            sub = await fetch_one("SELECT title, parent_category_id FROM categories WHERE id = %s", (item_id,))
            parent_id = sub["parent_category_id"]
            await _delete_subcategory_cascade(item_id)
            await callback.message.answer(f"زیرپوشه‌ی «{sub['title']}» و محصولاتش حذف شد ✅")
            await _show_operator_manage_screen(callback, catalog_type, parent_id)

        else:
            package = await fetch_one("SELECT name, category_id FROM packages WHERE id = %s", (item_id,))
            sub_id = package["category_id"]
            await _delete_package_cascade(item_id)
            await callback.message.answer(f"«{package['name']}» حذف شد ✅")
            await _show_subcategory_manage_screen(callback, catalog_type, sub_id)

    except aiomysql.IntegrityError:
        await callback.message.answer(
            "این پوشه شامل محصولی هست که قبلاً فروخته شده، برای همین کامل قابل حذف نیست. "
            "می‌تونی به‌جاش غیرفعالش کنی تا از دید مشتری مخفی بشه."
        )
    await callback.answer()
