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
from utils.states import ResellerPackageStates, ResellerCategoryStates, ResellerCatalogManageStates
from utils.keyboards import (
    sanity_check_confirm_buttons,
    catalog_type_menu,
    catalog_submenu,
    category_pick_buttons,
    operator_pick_buttons,
    back_to_reseller_menu_button,
    catalog_manage_operator_list_buttons,
    catalog_manage_operator_detail_buttons,
    catalog_manage_subcategory_detail_buttons,
    catalog_manage_package_detail_buttons,
    catalog_delete_confirm_buttons,
    package_edit_price_confirm_buttons,
)

router = Router(name="reseller_catalog")

_pending_price_confirmations: dict[str, dict] = {}
_pending_edit_price_confirmations: dict[str, dict] = {}

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


# ==========================================================================
# مدیریت/ویرایش/حذف اپراتور، زیرپوشه، محصول (بخش ۴ درخواست جدید).
# نکته‌ی مهم: categories.parent_category_id روی ON DELETE SET NULL است (نه
# CASCADE)، پس هیچ‌وقت مستقیم اپراتور را از دیتابیس حذف نمی‌کنیم بدون اینکه
# قبلش زیرپوشه‌ها و محصولات داخلشون رو دستی حذف کرده باشیم؛ وگرنه زیرپوشه‌های
# یتیم (parent_category_id = NULL) به‌اشتباه به‌عنوان اپراتور جدید نشون داده
# می‌شن. orders.package_id هم RESTRICT است (نه CASCADE)، پس اگه محصولی قبلاً
# فروش داشته باشه، حذفش (یا زیرپوشه/اپراتوری که شاملشه) با Foreign Key Error
# رد می‌شه که اینجا می‌گیریمش و به‌جای partial-delete، کامل rollback می‌کنیم.
# ==========================================================================

async def _render_manage_operators(callback: CallbackQuery, catalog_type: str, reseller_id: int):
    operators = await fetch_all(
        "SELECT id, operator_name FROM categories WHERE reseller_id = %s AND parent_category_id IS NULL "
        "AND catalog_type = %s",
        (reseller_id, catalog_type),
    )
    if not operators:
        await callback.message.edit_text(
            "هنوز هیچ اپراتوری اضافه نکرده‌اید.", reply_markup=catalog_submenu(catalog_type)
        )
        return
    await callback.message.edit_text(
        f"{_label(catalog_type)} — یک اپراتور را برای مدیریت انتخاب کنید:",
        reply_markup=catalog_manage_operator_list_buttons(operators, catalog_type),
    )


async def _render_operator_detail(callback: CallbackQuery, catalog_type: str, operator_id: int):
    operator = await fetch_one("SELECT id, operator_name FROM categories WHERE id = %s", (operator_id,))
    if operator is None:
        await callback.message.edit_text("این اپراتور دیگر وجود ندارد.", reply_markup=catalog_submenu(catalog_type))
        return
    subcategories = await fetch_all(
        "SELECT id, title FROM categories WHERE parent_category_id = %s", (operator_id,)
    )
    text = f"📁 {operator['operator_name']}"
    if not subcategories:
        text += "\n(هنوز زیرپوشه‌ای نداره)"
    await callback.message.edit_text(
        text, reply_markup=catalog_manage_operator_detail_buttons(catalog_type, operator_id, subcategories)
    )


async def _render_subcategory_detail(callback: CallbackQuery, catalog_type: str, subcategory_id: int):
    sub = await fetch_one(
        "SELECT id, title, parent_category_id FROM categories WHERE id = %s", (subcategory_id,)
    )
    if sub is None:
        await callback.message.edit_text("این زیرپوشه دیگر وجود ندارد.", reply_markup=catalog_submenu(catalog_type))
        return
    products = await fetch_all(
        "SELECT id, name, is_active FROM packages WHERE category_id = %s", (subcategory_id,)
    )
    text = f"📂 {sub['title']}"
    if not products:
        text += "\n(چیزی ثبت نشده)"
    await callback.message.edit_text(
        text,
        reply_markup=catalog_manage_subcategory_detail_buttons(
            catalog_type, sub["parent_category_id"], subcategory_id, products
        ),
    )


async def _render_package_detail(callback: CallbackQuery, catalog_type: str, package_id: int):
    pkg = await fetch_one(
        "SELECT id, category_id, name, sale_price, cost_price, is_active FROM packages WHERE id = %s",
        (package_id,),
    )
    if pkg is None:
        await callback.message.edit_text("این محصول دیگر وجود ندارد.", reply_markup=catalog_submenu(catalog_type))
        return
    mark = "✅ فعال" if pkg["is_active"] else "⛔️ غیرفعال"
    cost_text = f"{pkg['cost_price']:,.0f} تومان" if pkg["cost_price"] is not None else "ثبت نشده"
    icon = "🔋" if catalog_type == "charge" else "📦"
    text = (
        f"{icon} {pkg['name']}\n"
        f"قیمت فروش: {pkg['sale_price']:,.0f} تومان\n"
        f"قیمت خرید: {cost_text}\n"
        f"وضعیت: {mark}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=catalog_manage_package_detail_buttons(
            catalog_type, pkg["category_id"], package_id, pkg["is_active"]
        ),
    )


# ---------- شمارش تعداد موارد وابسته قبل از حذف (برای پیام تأییدیه) ----------
async def _count_operator_deletion_impact(operator_id: int) -> tuple[int, int, int]:
    subs = await fetch_all("SELECT id FROM categories WHERE parent_category_id = %s", (operator_id,))
    sub_ids = [s["id"] for s in subs]
    products_count = 0
    codes_count = 0
    if sub_ids:
        fmt = ",".join(["%s"] * len(sub_ids))
        products = await fetch_all(f"SELECT id FROM packages WHERE category_id IN ({fmt})", tuple(sub_ids))
        products_count = len(products)
        product_ids = [p["id"] for p in products]
        if product_ids:
            fmt2 = ",".join(["%s"] * len(product_ids))
            row = await fetch_one(
                f"SELECT COUNT(*) AS cnt FROM charge_codes WHERE status = 'available' AND package_id IN ({fmt2})",
                tuple(product_ids),
            )
            codes_count = row["cnt"]
    return len(sub_ids), products_count, codes_count


async def _count_subcategory_deletion_impact(subcategory_id: int) -> tuple[int, int]:
    products = await fetch_all("SELECT id FROM packages WHERE category_id = %s", (subcategory_id,))
    product_ids = [p["id"] for p in products]
    codes_count = 0
    if product_ids:
        fmt = ",".join(["%s"] * len(product_ids))
        row = await fetch_one(
            f"SELECT COUNT(*) AS cnt FROM charge_codes WHERE status = 'available' AND package_id IN ({fmt})",
            tuple(product_ids),
        )
        codes_count = row["cnt"]
    return len(product_ids), codes_count


async def _count_package_deletion_impact(package_id: int) -> int:
    row = await fetch_one(
        "SELECT COUNT(*) AS cnt FROM charge_codes WHERE status = 'available' AND package_id = %s", (package_id,)
    )
    return row["cnt"]


# ---------- حذف اتمیک (تراکنشی) ----------
async def _delete_operator_tree(operator_id: int) -> None:
    """اول محصولات هر زیرپوشه، بعد خود زیرپوشه‌ها، بعد خود اپراتور — دستی و به ترتیب،
    چون categories.parent_category_id فاقد CASCADE است."""
    async with transaction() as conn:
        cur = await conn.cursor()
        await cur.execute("SELECT id FROM categories WHERE parent_category_id = %s", (operator_id,))
        sub_ids = [row[0] for row in await cur.fetchall()]
        if sub_ids:
            fmt = ",".join(["%s"] * len(sub_ids))
            await cur.execute(f"DELETE FROM packages WHERE category_id IN ({fmt})", tuple(sub_ids))
            await cur.execute(f"DELETE FROM categories WHERE id IN ({fmt})", tuple(sub_ids))
        await cur.execute("DELETE FROM categories WHERE id = %s", (operator_id,))


async def _delete_subcategory_tree(subcategory_id: int) -> None:
    async with transaction() as conn:
        cur = await conn.cursor()
        await cur.execute("DELETE FROM packages WHERE category_id = %s", (subcategory_id,))
        await cur.execute("DELETE FROM categories WHERE id = %s", (subcategory_id,))


async def _delete_package(package_id: int) -> None:
    async with transaction() as conn:
        cur = await conn.cursor()
        # charge_codes.package_id روی ON DELETE CASCADE است، پس کدهای موجودِ
        # فروخته‌نشده‌ی همین محصول خودکار پاک می‌شوند.
        await cur.execute("DELETE FROM packages WHERE id = %s", (package_id,))


_FK_ERROR_TEXT = (
    "این پوشه شامل محصولی هست که قبلاً فروخته شده، برای همین کامل قابل حذف نیست. "
    "می‌تونی به‌جاش غیرفعالش کنی تا از دید مشتری مخفی بشه."
)
_FK_ERROR_TEXT_PKG = (
    "این محصول قبلاً فروخته شده، برای همین قابل حذف نیست. "
    "می‌تونی به‌جاش غیرفعالش کنی تا از دید مشتری مخفی بشه."
)


# ---------- ناوبری منوی مدیریت ----------
@router.callback_query(F.data.startswith("catalog:manage:"))
async def manage_operators_cb(callback: CallbackQuery, reseller_id: int):
    catalog_type = callback.data.split(":")[2]
    await _render_manage_operators(callback, catalog_type, reseller_id)
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:manage_op:"))
async def manage_operator_detail_cb(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, operator_id = parts[2], int(parts[3])
    await _render_operator_detail(callback, catalog_type, operator_id)
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:manage_sub:"))
async def manage_subcategory_detail_cb(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, subcategory_id = parts[2], int(parts[3])
    await _render_subcategory_detail(callback, catalog_type, subcategory_id)
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:manage_pkg:"))
async def manage_package_detail_cb(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    await _render_package_detail(callback, catalog_type, package_id)
    await callback.answer()


# ---------- ویرایش نام اپراتور ----------
@router.callback_query(F.data.startswith("catalog:edit_op_name:"))
async def start_edit_operator_name(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, operator_id = parts[2], int(parts[3])
    await state.update_data(catalog_type=catalog_type, operator_id=operator_id)
    await state.set_state(ResellerCatalogManageStates.editing_operator_name)
    await callback.message.answer("نام جدید اپراتور را وارد کنید:\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCatalogManageStates.editing_operator_name)
async def save_operator_name_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    new_name = message.text.strip()
    await execute(
        "UPDATE categories SET operator_name = %s, title = %s WHERE id = %s",
        (new_name, new_name, data["operator_id"]),
    )
    await message.answer(
        f"نام اپراتور به «{new_name}» تغییر کرد ✅", reply_markup=catalog_submenu(data["catalog_type"])
    )
    await state.clear()


# ---------- ویرایش عنوان زیرپوشه ----------
@router.callback_query(F.data.startswith("catalog:edit_sub_title:"))
async def start_edit_subcategory_title(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, subcategory_id = parts[2], int(parts[3])
    await state.update_data(catalog_type=catalog_type, subcategory_id=subcategory_id)
    await state.set_state(ResellerCatalogManageStates.editing_subcategory_title)
    await callback.message.answer("عنوان جدید زیرپوشه را وارد کنید:\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCatalogManageStates.editing_subcategory_title)
async def save_subcategory_title_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    new_title = message.text.strip()
    await execute("UPDATE categories SET title = %s WHERE id = %s", (new_title, data["subcategory_id"]))
    await message.answer(
        f"عنوان زیرپوشه به «{new_title}» تغییر کرد ✅", reply_markup=catalog_submenu(data["catalog_type"])
    )
    await state.clear()


# ---------- ویرایش اسم محصول ----------
@router.callback_query(F.data.startswith("catalog:edit_pkg_name:"))
async def start_edit_package_name(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    await state.update_data(catalog_type=catalog_type, package_id=package_id)
    await state.set_state(ResellerCatalogManageStates.editing_package_name)
    label = "بسته" if catalog_type == "package" else "محصول شارژ"
    await callback.message.answer(f"نام جدید {label} را وارد کنید:\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCatalogManageStates.editing_package_name)
async def save_package_name_edit(message: Message, state: FSMContext):
    data = await state.get_data()
    new_name = message.text.strip()
    await execute("UPDATE packages SET name = %s WHERE id = %s", (new_name, data["package_id"]))
    await message.answer(f"نام به «{new_name}» تغییر کرد ✅", reply_markup=catalog_submenu(data["catalog_type"]))
    await state.clear()


# ---------- ویرایش قیمت فروش (با همون منطق هشدار قیمت غیرعادی) ----------
@router.callback_query(F.data.startswith("catalog:edit_pkg_price:"))
async def start_edit_package_price(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    await state.update_data(catalog_type=catalog_type, package_id=package_id)
    await state.set_state(ResellerCatalogManageStates.editing_package_price)
    await callback.message.answer("قیمت فروش جدید را وارد کنید (فقط عدد، مثال: 65000):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCatalogManageStates.editing_package_price)
async def receive_package_price_edit(message: Message, state: FSMContext):
    try:
        sale_price = Decimal(message.text.replace(",", "").strip())
    except InvalidOperation:
        await message.answer("لطفاً فقط عدد وارد کنید. مثال درست: 100000")
        return

    data = await state.get_data()
    package_id = data["package_id"]
    row = await fetch_one(
        "SELECT c.operator_name FROM packages p JOIN categories c ON c.id = p.category_id WHERE p.id = %s",
        (package_id,),
    )
    operator_name = row["operator_name"] if row else ""

    if await is_price_suspicious(operator_name, sale_price):
        token = uuid.uuid4().hex[:8]
        _pending_edit_price_confirmations[token] = {
            "package_id": package_id,
            "catalog_type": data["catalog_type"],
            "sale_price": sale_price,
        }
        await state.set_state(ResellerCatalogManageStates.confirming_suspicious_edit_price)
        await message.answer(
            f"⚠️ این قیمت غیرعادی به نظر می‌رسه، مطمئنی؟\n"
            f"مبلغ واردشده: {sale_price:,.0f} تومان",
            reply_markup=package_edit_price_confirm_buttons(token),
        )
        return

    await execute("UPDATE packages SET sale_price = %s WHERE id = %s", (sale_price, package_id))
    await message.answer(
        f"قیمت فروش به {sale_price:,.0f} تومان تغییر کرد ✅", reply_markup=catalog_submenu(data["catalog_type"])
    )
    await state.clear()


@router.callback_query(F.data.startswith("pkgedit_price_confirm:"))
async def confirm_edit_suspicious_price(callback: CallbackQuery, state: FSMContext):
    token = callback.data.split(":")[1]
    pending = _pending_edit_price_confirmations.pop(token, None)
    if pending is None:
        await callback.answer("این درخواست منقضی شده، دوباره تلاش کنید.", show_alert=True)
        return
    await execute("UPDATE packages SET sale_price = %s WHERE id = %s", (pending["sale_price"], pending["package_id"]))
    await callback.message.answer(
        f"قیمت فروش به {pending['sale_price']:,.0f} تومان تغییر کرد ✅",
        reply_markup=catalog_submenu(pending["catalog_type"]),
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("pkgedit_price_edit:"))
async def edit_again_suspicious_price(callback: CallbackQuery, state: FSMContext):
    token = callback.data.split(":")[1]
    _pending_edit_price_confirmations.pop(token, None)
    await state.set_state(ResellerCatalogManageStates.editing_package_price)
    await callback.message.answer("قیمت صحیح را دوباره وارد کنید:")
    await callback.answer()


# ---------- ویرایش قیمت خرید/تمام‌شده ----------
@router.callback_query(F.data.startswith("catalog:edit_pkg_cost:"))
async def start_edit_package_cost(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    await state.update_data(catalog_type=catalog_type, package_id=package_id)
    await state.set_state(ResellerCatalogManageStates.editing_package_cost_price)
    await callback.message.answer("قیمت خرید/تمام‌شده‌ی جدید را وارد کنید (فقط عدد):\n(برای انصراف /cancel)")
    await callback.answer()


@router.message(ResellerCatalogManageStates.editing_package_cost_price)
async def save_package_cost_edit(message: Message, state: FSMContext):
    try:
        cost_price = Decimal(message.text.replace(",", "").strip())
    except InvalidOperation:
        await message.answer("لطفاً فقط عدد وارد کنید.")
        return
    data = await state.get_data()
    await execute("UPDATE packages SET cost_price = %s WHERE id = %s", (cost_price, data["package_id"]))
    await message.answer(
        f"قیمت خرید به {cost_price:,.0f} تومان تغییر کرد ✅", reply_markup=catalog_submenu(data["catalog_type"])
    )
    await state.clear()


# ---------- فعال/غیرفعال کردن محصول (مستقل از حذف) ----------
@router.callback_query(F.data.startswith("catalog:toggle_pkg:"))
async def toggle_package_active(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    await execute("UPDATE packages SET is_active = NOT is_active WHERE id = %s", (package_id,))
    await callback.answer("وضعیت محصول تغییر کرد ✅")
    await _render_package_detail(callback, catalog_type, package_id)


# ---------- حذف اپراتور ----------
@router.callback_query(F.data.startswith("catalog:del_op:"))
async def confirm_delete_operator(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, operator_id = parts[2], int(parts[3])
    subs_count, products_count, codes_count = await _count_operator_deletion_impact(operator_id)
    await callback.message.edit_text(
        f"با حذف این اپراتور، {subs_count} زیرپوشه، {products_count} محصول و "
        f"{codes_count} کد شارژ موجود (فروخته‌نشده) هم حذف می‌شوند.\nمطمئنی؟",
        reply_markup=catalog_delete_confirm_buttons(catalog_type, "op", operator_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:del_op_yes:"))
async def delete_operator_confirmed(callback: CallbackQuery, reseller_id: int):
    parts = callback.data.split(":")
    catalog_type, operator_id = parts[2], int(parts[3])
    try:
        await _delete_operator_tree(operator_id)
    except aiomysql.IntegrityError:
        await callback.answer(_FK_ERROR_TEXT, show_alert=True)
        await _render_operator_detail(callback, catalog_type, operator_id)
        return
    await callback.answer("اپراتور حذف شد ✅", show_alert=True)
    await _render_manage_operators(callback, catalog_type, reseller_id)


@router.callback_query(F.data.startswith("catalog:del_op_no:"))
async def delete_operator_cancelled(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, operator_id = parts[2], int(parts[3])
    await callback.answer("انصراف داده شد.")
    await _render_operator_detail(callback, catalog_type, operator_id)


# ---------- حذف زیرپوشه ----------
@router.callback_query(F.data.startswith("catalog:del_sub:"))
async def confirm_delete_subcategory(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, subcategory_id = parts[2], int(parts[3])
    products_count, codes_count = await _count_subcategory_deletion_impact(subcategory_id)
    await callback.message.edit_text(
        f"با حذف این زیرپوشه، {products_count} محصول و {codes_count} کد شارژ موجود "
        f"(فروخته‌نشده) هم حذف می‌شوند.\nمطمئنی؟",
        reply_markup=catalog_delete_confirm_buttons(catalog_type, "sub", subcategory_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:del_sub_yes:"))
async def delete_subcategory_confirmed(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, subcategory_id = parts[2], int(parts[3])
    sub = await fetch_one("SELECT parent_category_id FROM categories WHERE id = %s", (subcategory_id,))
    try:
        await _delete_subcategory_tree(subcategory_id)
    except aiomysql.IntegrityError:
        await callback.answer(_FK_ERROR_TEXT, show_alert=True)
        await _render_subcategory_detail(callback, catalog_type, subcategory_id)
        return
    await callback.answer("زیرپوشه حذف شد ✅", show_alert=True)
    if sub and sub["parent_category_id"]:
        await _render_operator_detail(callback, catalog_type, sub["parent_category_id"])
    else:
        await callback.message.edit_text("زیرپوشه حذف شد.", reply_markup=catalog_submenu(catalog_type))


@router.callback_query(F.data.startswith("catalog:del_sub_no:"))
async def delete_subcategory_cancelled(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, subcategory_id = parts[2], int(parts[3])
    await callback.answer("انصراف داده شد.")
    await _render_subcategory_detail(callback, catalog_type, subcategory_id)


# ---------- حذف محصول ----------
@router.callback_query(F.data.startswith("catalog:del_pkg:"))
async def confirm_delete_package(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    codes_count = await _count_package_deletion_impact(package_id)
    extra = f"\n({codes_count} کد شارژ موجود هم همراهش حذف می‌شود.)" if catalog_type == "charge" else ""
    await callback.message.edit_text(
        f"این محصول حذف می‌شود.{extra}\nمطمئنی؟",
        reply_markup=catalog_delete_confirm_buttons(catalog_type, "pkg", package_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("catalog:del_pkg_yes:"))
async def delete_package_confirmed(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    pkg = await fetch_one("SELECT category_id FROM packages WHERE id = %s", (package_id,))
    try:
        await _delete_package(package_id)
    except aiomysql.IntegrityError:
        await callback.answer(_FK_ERROR_TEXT_PKG, show_alert=True)
        await _render_package_detail(callback, catalog_type, package_id)
        return
    await callback.answer("محصول حذف شد ✅", show_alert=True)
    if pkg:
        await _render_subcategory_detail(callback, catalog_type, pkg["category_id"])
    else:
        await callback.message.edit_text("محصول حذف شد.", reply_markup=catalog_submenu(catalog_type))


@router.callback_query(F.data.startswith("catalog:del_pkg_no:"))
async def delete_package_cancelled(callback: CallbackQuery):
    parts = callback.data.split(":")
    catalog_type, package_id = parts[2], int(parts[3])
    await callback.answer("انصراف داده شد.")
    await _render_package_detail(callback, catalog_type, package_id)
