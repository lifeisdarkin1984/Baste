"""
مدیریت موجودی کد شارژ (بخش جدید طبق درخواست) — چهار زیربخش:
  ➕ افزودن کد | 📋 نمایش کدهای موجود | 🗑 حذف موجودی | 🧾 کدهای فروخته‌شده

هر چهار مسیر مشترک هستند: انتخاب اپراتور -> انتخاب زیرپوشه -> انتخاب محصول
شارژ (فقط از کاتالوگ نوع 'charge' که در handlers/reseller/catalog.py ساخته
می‌شود)، و در نهایت اکشن مربوطه روی همان محصول انجام می‌شود. نوع اکشن در تمام
callback_data ها با پیشوند cstock: حفظ می‌شود.
"""
from html import escape

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import fetch_all, fetch_one
from services.charge_service import (
    add_charge_codes,
    count_available_codes,
    list_available_codes,
    list_sold_codes,
    delete_available_code,
    clear_available_codes,
)
from utils.states import ResellerChargeCodeStates
from utils.keyboards import (
    charge_stock_menu,
    charge_operator_pick_buttons,
    charge_category_pick_buttons,
    charge_product_pick_buttons,
    charge_code_remove_buttons,
    back_to_reseller_menu_button,
)

router = Router(name="reseller_charge_stock")

_ACTION_TITLES = {
    "add": "➕ افزودن کد — محصول را انتخاب کنید:",
    "list": "📋 نمایش کدهای موجود — محصول را انتخاب کنید:",
    "remove": "🗑 حذف موجودی — محصول را انتخاب کنید:",
    "sold": "🧾 کدهای فروخته‌شده — محصول را انتخاب کنید:",
}


@router.callback_query(F.data == "rmenu:charge_stock")
async def charge_stock_menu_cb(callback: CallbackQuery):
    await callback.message.edit_text("🎫 مدیریت شارژ", reply_markup=charge_stock_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("cstock:pick:"))
async def pick_operator_for_action(callback: CallbackQuery, reseller_id: int):
    action = callback.data.split(":")[2]
    operators = await fetch_all(
        "SELECT id, operator_name FROM categories WHERE reseller_id = %s AND parent_category_id IS NULL "
        "AND catalog_type = 'charge'",
        (reseller_id,),
    )
    if not operators:
        await callback.message.answer(
            "هنوز کاتالوگ شارژی ساخته نشده. اول از منوی «📦 کاتالوگ -> 🔋 شارژ» یک اپراتور/زیرپوشه/محصول بسازید.",
            reply_markup=back_to_reseller_menu_button(),
        )
        await callback.answer()
        return
    await callback.message.answer(_ACTION_TITLES[action], reply_markup=charge_operator_pick_buttons(operators, action))
    await callback.answer()


@router.callback_query(F.data.startswith("cstock:op:"))
async def pick_category_for_action(callback: CallbackQuery):
    parts = callback.data.split(":")
    action, operator_id = parts[2], int(parts[3])
    subcategories = await fetch_all(
        "SELECT id, title FROM categories WHERE parent_category_id = %s", (operator_id,)
    )
    if not subcategories:
        await callback.message.answer(
            "این اپراتور هنوز زیرپوشه‌ای نداره.", reply_markup=charge_stock_menu()
        )
        await callback.answer()
        return
    await callback.message.answer("زیرپوشه را انتخاب کنید:", reply_markup=charge_category_pick_buttons(subcategories, action))
    await callback.answer()


@router.callback_query(F.data.startswith("cstock:cat:"))
async def pick_product_for_action(callback: CallbackQuery):
    parts = callback.data.split(":")
    action, category_id = parts[2], int(parts[3])
    products = await fetch_all(
        "SELECT id, name, sale_price FROM packages WHERE category_id = %s", (category_id,)
    )
    if not products:
        await callback.message.answer(
            "این زیرپوشه هنوز محصول شارژی ندارد.", reply_markup=charge_stock_menu()
        )
        await callback.answer()
        return
    for p in products:
        p["available_count"] = await count_available_codes(p["id"])
    await callback.message.answer("محصول را انتخاب کنید:", reply_markup=charge_product_pick_buttons(products, action))
    await callback.answer()


@router.callback_query(F.data.startswith("cstock:prod:"))
async def act_on_product(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    action, package_id = parts[2], int(parts[3])
    product = await fetch_one("SELECT name FROM packages WHERE id = %s", (package_id,))
    if product is None:
        await callback.message.answer("این محصول دیگر موجود نیست.", reply_markup=charge_stock_menu())
        await callback.answer()
        return

    if action == "add":
        await state.update_data(charge_package_id=package_id)
        await state.set_state(ResellerChargeCodeStates.entering_codes)
        await callback.message.answer(
            f"کدهای «{product['name']}» را ارسال کنید؛ هر کد در یک خط جداگانه.\n(برای انصراف /cancel)"
        )
        await callback.answer()
        return

    if action == "list":
        codes = await list_available_codes(package_id)
        total = await count_available_codes(package_id)
        if not codes:
            await callback.message.answer(f"«{product['name']}» موجودی‌ای ندارد.", reply_markup=charge_stock_menu())
        else:
            lines = "\n".join(f"- {escape(c['code'])}" for c in codes)
            await callback.message.answer(
                f"📋 موجودی «{product['name']}» ({total} عدد):\n{lines}", reply_markup=charge_stock_menu()
            )
        await callback.answer()
        return

    if action == "remove":
        codes = await list_available_codes(package_id)
        if not codes:
            await callback.message.answer(f"«{product['name']}» موجودی‌ای برای حذف ندارد.", reply_markup=charge_stock_menu())
            await callback.answer()
            return
        await callback.message.answer(
            f"🗑 حذف موجودی «{product['name']}» — روی کد موردنظر بزنید یا همه را حذف کنید:",
            reply_markup=charge_code_remove_buttons(codes, package_id),
        )
        await callback.answer()
        return

    if action == "sold":
        sold = await list_sold_codes(package_id)
        if not sold:
            await callback.message.answer(f"«{product['name']}» هنوز فروشی نداشته.", reply_markup=charge_stock_menu())
        else:
            lines = []
            for s in sold:
                when = s["sold_at"].strftime("%Y-%m-%d %H:%M") if s["sold_at"] else "-"
                lines.append(
                    f"- {escape(s['code'])} | خریدار: {s['telegram_user_id']} | سفارش: {s['order_code']} | {when}"
                )
            await callback.message.answer(
                f"🧾 فروخته‌شده‌های «{product['name']}»:\n" + "\n".join(lines), reply_markup=charge_stock_menu()
            )
        await callback.answer()
        return

    await callback.answer()


@router.message(ResellerChargeCodeStates.entering_codes)
async def receive_charge_codes(message: Message, state: FSMContext, reseller_id: int):
    data = await state.get_data()
    package_id = data.get("charge_package_id")
    if package_id is None or not message.text:
        await message.answer("متن نامعتبر است، دوباره تلاش کنید یا /cancel بزنید.")
        return
    added = await add_charge_codes(reseller_id, package_id, message.text)
    if added == 0:
        await message.answer("هیچ کد معتبری پیدا نشد. هر کد را در یک خط جداگانه بفرستید.")
        return
    await message.answer(f"{added} کد با موفقیت به موجودی اضافه شد ✅", reply_markup=charge_stock_menu())
    await state.clear()


@router.callback_query(F.data.startswith("cstock:delcode:"))
async def delete_single_code(callback: CallbackQuery):
    parts = callback.data.split(":")
    code_id, package_id = int(parts[2]), int(parts[3])
    await delete_available_code(code_id)
    codes = await list_available_codes(package_id)
    if not codes:
        await callback.message.edit_text("کد حذف شد ✅ موجودی این محصول دیگر خالی است.")
    else:
        await callback.message.edit_text("کد حذف شد ✅ موجودی باقیمانده:", reply_markup=charge_code_remove_buttons(codes, package_id))
    await callback.answer()


@router.callback_query(F.data.startswith("cstock:clearall:"))
async def clear_all_codes(callback: CallbackQuery):
    package_id = int(callback.data.split(":")[2])
    count = await clear_available_codes(package_id)
    await callback.message.edit_text(f"{count} کد موجود حذف شد ✅")
    await callback.answer()
