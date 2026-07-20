"""
فیچر جدید «خرید شارژ سطح» برای مشتری.

برخلاف خرید بسته‌ی اینترنتی (که نیاز به شماره‌خط و فعال‌سازی دستی نماینده
دارد)، شارژ یک کد از پیش تولیدشده است: به محض خرید (فقط با کسر از کیف‌پول،
چون تحویل باید آنی باشد) بلافاصله کد به مشتری تحویل داده می‌شود. اگر موجودی
کیف‌پول کافی نباشد، از مشتری خواسته می‌شود اول کیف‌پولش را شارژ کند (فلوی
رسیدی این‌جا معنا ندارد چون کد باید فوری تحویل داده شود).

ناوبری (کیبورد پایین صفحه، مثل بخش بسته‌ها):
  🔋 خرید شارژ سطح
    -> لیست اپراتورها (پوشه اصلی، فقط کاتالوگ نوع 'charge')
       -> لیست زیرپوشه‌ها
          -> لیست محصولات شارژ
             -> جزئیات + دکمه‌ی «🔋 خرید این شارژ»
"""
from decimal import Decimal

from aiogram import Router, F
from aiogram.types import Message

from database.db import fetch_all, fetch_one
from aiogram.fsm.context import FSMContext

from services.order_service import get_or_create_customer
from services.charge_service import (
    purchase_charge_bulk,
    ChargeCustomerBlacklistedError,
    ChargeInsufficientBalanceError,
    ChargeOutOfStockError,
)
from services.forced_join_service import user_has_joined_all
from utils.states import CustomerChargeStates
from utils.keyboards import (
    customer_main_reply_keyboard,
    customer_folder_reply_keyboard,
    customer_charge_detail_keyboard,
    customer_charge_quantity_keyboard,
    CUSTOMER_CHARGE_BUTTON_TEXT,
    CUSTOMER_BACK_BUTTON_TEXT,
    CUSTOMER_BACK_TO_MENU_BUTTON_TEXT,
    CUSTOMER_BUY_CHARGE_BUTTON_TEXT,
    CUSTOMER_WALLET_BUTTON_TEXT,
)

router = Router(name="customer_charge")


async def _back_to_main_menu(message: Message, reseller_id: int, state: FSMContext):
    await state.clear()
    reseller = await fetch_one("SELECT support_contact FROM resellers WHERE id = %s", (reseller_id,))
    has_support = bool(reseller and reseller["support_contact"])
    await message.answer("منوی اصلی:", reply_markup=customer_main_reply_keyboard(has_support_contact=has_support))


async def _show_operators(message: Message, reseller_id: int, user_id: int, state: FSMContext):
    joined, missing_channels = await user_has_joined_all(message.bot, reseller_id, user_id)
    if not joined:
        channels_text = "\n".join(f"- {c}" for c in missing_channels)
        await message.answer(
            f"⛔️ برای مشاهده‌ی این بخش ابتدا باید عضو کانال(های) زیر شوید:\n{channels_text}\n\n"
            f"بعد از عضویت، دوباره روی «{CUSTOMER_CHARGE_BUTTON_TEXT}» بزنید."
        )
        return

    operators = await fetch_all(
        "SELECT id, operator_name FROM categories WHERE reseller_id = %s AND parent_category_id IS NULL "
        "AND catalog_type = 'charge'",
        (reseller_id,),
    )
    if not operators:
        await message.answer("در حال حاضر شارژی ثبت نشده است.")
        return

    operator_map = {f"📁 {op['operator_name']}": op["id"] for op in operators}
    await state.set_state(CustomerChargeStates.browsing_operators)
    await state.update_data(charge_operator_map=operator_map)
    await message.answer(
        "یک اپراتور را انتخاب کنید:",
        reply_markup=customer_folder_reply_keyboard(list(operator_map.keys()), back_text=CUSTOMER_BACK_TO_MENU_BUTTON_TEXT),
    )


@router.message(F.text == CUSTOMER_CHARGE_BUTTON_TEXT)
async def show_charge_catalog_from_keyboard(message: Message, reseller_id: int, state: FSMContext):
    await _show_operators(message, reseller_id, message.from_user.id, state)


@router.message(CustomerChargeStates.browsing_operators)
async def handle_charge_operator_pick(message: Message, reseller_id: int, state: FSMContext):
    if message.text == CUSTOMER_BACK_TO_MENU_BUTTON_TEXT:
        await _back_to_main_menu(message, reseller_id, state)
        return

    data = await state.get_data()
    operator_id = data.get("charge_operator_map", {}).get(message.text)
    if operator_id is None:
        await message.answer("لطفاً یکی از گزینه‌های روی کیبورد را انتخاب کنید.")
        return

    subcategories = await fetch_all(
        "SELECT id, title FROM categories WHERE parent_category_id = %s", (operator_id,)
    )
    if not subcategories:
        await message.answer("این اپراتور هنوز زیرپوشه‌ای ندارد.")
        return

    subcategory_map = {f"📂 {c['title']}": c["id"] for c in subcategories}
    await state.set_state(CustomerChargeStates.browsing_subcategories)
    await state.update_data(charge_subcategory_map=subcategory_map)
    await message.answer(
        "یک زیرپوشه را انتخاب کنید:",
        reply_markup=customer_folder_reply_keyboard(list(subcategory_map.keys()), back_text=CUSTOMER_BACK_BUTTON_TEXT),
    )


@router.message(CustomerChargeStates.browsing_subcategories)
async def handle_charge_subcategory_pick(message: Message, reseller_id: int, state: FSMContext):
    data = await state.get_data()
    if message.text == CUSTOMER_BACK_BUTTON_TEXT:
        operator_map = data.get("charge_operator_map", {})
        await state.set_state(CustomerChargeStates.browsing_operators)
        await message.answer(
            "یک اپراتور را انتخاب کنید:",
            reply_markup=customer_folder_reply_keyboard(list(operator_map.keys()), back_text=CUSTOMER_BACK_TO_MENU_BUTTON_TEXT),
        )
        return

    category_id = data.get("charge_subcategory_map", {}).get(message.text)
    if category_id is None:
        await message.answer("لطفاً یکی از گزینه‌های روی کیبورد را انتخاب کنید.")
        return

    products = await fetch_all(
        "SELECT id, name, sale_price FROM packages WHERE category_id = %s AND is_active = TRUE",
        (category_id,),
    )
    if not products:
        await message.answer("در این زیرپوشه هنوز شارژی ثبت نشده است.")
        return

    product_map = {f"🔋 {p['name']} — {p['sale_price']:,.0f} تومان": p["id"] for p in products}
    await state.update_data(charge_product_map=product_map)
    await state.set_state(CustomerChargeStates.browsing_products)
    await message.answer(
        "یک شارژ را انتخاب کنید:",
        reply_markup=customer_folder_reply_keyboard(list(product_map.keys()), back_text=CUSTOMER_BACK_BUTTON_TEXT),
    )


@router.message(CustomerChargeStates.browsing_products)
async def handle_charge_product_pick(message: Message, reseller_id: int, state: FSMContext):
    data = await state.get_data()
    if message.text == CUSTOMER_BACK_BUTTON_TEXT:
        subcategory_map = data.get("charge_subcategory_map", {})
        await state.set_state(CustomerChargeStates.browsing_subcategories)
        await message.answer(
            "یک زیرپوشه را انتخاب کنید:",
            reply_markup=customer_folder_reply_keyboard(list(subcategory_map.keys()), back_text=CUSTOMER_BACK_BUTTON_TEXT),
        )
        return

    package_id = data.get("charge_product_map", {}).get(message.text)
    if package_id is None:
        await message.answer("لطفاً یکی از گزینه‌های روی کیبورد را انتخاب کنید.")
        return

    product = await fetch_one(
        "SELECT p.id, p.name, p.sale_price, c.operator_name, c.title "
        "FROM packages p JOIN categories c ON p.category_id = c.id WHERE p.id = %s",
        (package_id,),
    )
    if product is None:
        await message.answer("این شارژ دیگر موجود نیست.")
        return

    await state.set_state(CustomerChargeStates.product_selected)
    await state.update_data(selected_charge_package_id=package_id)
    await message.answer(
        f"🔋 {product['operator_name']} - {product['title']}\n{product['name']}\n"
        f"💰 {product['sale_price']:,.0f} تومان\n\n"
        f"مبلغ از کیف‌پول شما کسر می‌شود و کد بلافاصله همین‌جا تحویل داده می‌شود.\n"
        f"برای خرید، دکمه‌ی «{CUSTOMER_BUY_CHARGE_BUTTON_TEXT}» را بزنید.",
        reply_markup=customer_charge_detail_keyboard(),
    )


@router.message(CustomerChargeStates.product_selected, F.text == CUSTOMER_BACK_BUTTON_TEXT)
async def handle_charge_detail_back(message: Message, reseller_id: int, state: FSMContext):
    data = await state.get_data()
    product_map = data.get("charge_product_map", {})
    await state.set_state(CustomerChargeStates.browsing_products)
    await message.answer(
        "یک شارژ را انتخاب کنید:",
        reply_markup=customer_folder_reply_keyboard(list(product_map.keys()), back_text=CUSTOMER_BACK_BUTTON_TEXT),
    )


@router.message(CustomerChargeStates.product_selected, F.text == CUSTOMER_BUY_CHARGE_BUTTON_TEXT)
async def handle_buy_charge_button(message: Message, reseller_id: int, state: FSMContext):
    data = await state.get_data()
    package_id = data.get("selected_charge_package_id")
    if package_id is None:
        await _back_to_main_menu(message, reseller_id, state)
        return

    await state.set_state(CustomerChargeStates.entering_quantity)
    await message.answer(
        "چند عدد از این شارژ می‌خواهید بخرید؟ عدد را تایپ کنید (حداقل ۱):",
        reply_markup=customer_charge_quantity_keyboard(),
    )


async def _show_product_detail(message: Message, state: FSMContext, package_id: int) -> bool:
    """جزئیات محصول را دوباره نمایش می‌دهد (برای بازگشت از مرحله‌ی تعداد). موفقیت را برمی‌گرداند."""
    product = await fetch_one(
        "SELECT p.id, p.name, p.sale_price, c.operator_name, c.title "
        "FROM packages p JOIN categories c ON p.category_id = c.id WHERE p.id = %s",
        (package_id,),
    )
    if product is None:
        return False
    await state.set_state(CustomerChargeStates.product_selected)
    await message.answer(
        f"🔋 {product['operator_name']} - {product['title']}\n{product['name']}\n"
        f"💰 {product['sale_price']:,.0f} تومان\n\n"
        f"مبلغ از کیف‌پول شما کسر می‌شود و کد بلافاصله همین‌جا تحویل داده می‌شود.\n"
        f"برای خرید، دکمه‌ی «{CUSTOMER_BUY_CHARGE_BUTTON_TEXT}» را بزنید.",
        reply_markup=customer_charge_detail_keyboard(),
    )
    return True


@router.message(CustomerChargeStates.entering_quantity, F.text == CUSTOMER_BACK_BUTTON_TEXT)
async def handle_charge_quantity_back(message: Message, reseller_id: int, state: FSMContext):
    data = await state.get_data()
    package_id = data.get("selected_charge_package_id")
    if package_id is None or not await _show_product_detail(message, state, package_id):
        await _back_to_main_menu(message, reseller_id, state)


@router.message(CustomerChargeStates.entering_quantity)
async def handle_charge_quantity_input(message: Message, reseller_id: int, state: FSMContext):
    data = await state.get_data()
    package_id = data.get("selected_charge_package_id")
    if package_id is None:
        await _back_to_main_menu(message, reseller_id, state)
        return

    raw_text = (message.text or "").strip()
    if not raw_text.isdigit() or int(raw_text) < 1:
        await message.answer(
            "لطفاً یک عدد صحیح مثبت (حداقل ۱) وارد کنید:",
            reply_markup=customer_charge_quantity_keyboard(),
        )
        return
    quantity = int(raw_text)

    package = await fetch_one("SELECT sale_price FROM packages WHERE id = %s", (package_id,))
    if package is None:
        await message.answer("این شارژ دیگر موجود نیست.")
        await _back_to_main_menu(message, reseller_id, state)
        return

    unit_price = Decimal(package["sale_price"])
    total_price = unit_price * quantity
    await message.answer(f"مبلغ کل برای {quantity} عدد: {total_price:,.0f} تومان\nدر حال پردازش خرید...")

    customer = await get_or_create_customer(reseller_id, message.from_user.id)

    try:
        result = await purchase_charge_bulk(reseller_id, package_id, customer["id"], quantity)
    except ChargeCustomerBlacklistedError:
        await message.answer("⛔️ امکان خرید برای شما وجود ندارد.")
        await state.clear()
        return
    except ChargeInsufficientBalanceError:
        await message.answer(
            f"موجودی کیف‌پول شما برای این خرید کافی نیست.\n"
            f"لطفاً ابتدا از «{CUSTOMER_WALLET_BUTTON_TEXT}» کیف‌پولتان را شارژ کنید و دوباره تلاش کنید."
        )
        return
    except ChargeOutOfStockError as e:
        available = getattr(e, "available", None)
        if not available:
            await message.answer(
                "متأسفانه موجودی این شارژ در حال حاضر تمام شده است. لطفاً بعداً امتحان کنید.",
                reply_markup=customer_charge_quantity_keyboard(),
            )
        else:
            await message.answer(
                f"در حال حاضر فقط {available} عدد از این شارژ موجود است.\n"
                f"لطفاً عددی کمتر یا مساوی {available} وارد کنید:",
                reply_markup=customer_charge_quantity_keyboard(),
            )
        return

    orders = result["orders"]
    total = result["total_price"]
    await state.clear()
    reseller = await fetch_one(
        "SELECT telegram_numeric_id, support_contact FROM resellers WHERE id = %s", (reseller_id,)
    )
    has_support = bool(reseller and reseller["support_contact"])

    lines = [f"✅ خرید {quantity} عدد شارژ با موفقیت انجام شد.\nمبلغ کل: {total:,.0f} تومان"]
    for i, order in enumerate(orders, start=1):
        lines.append(f"{i}) شناسه سفارش: {order['order_code']}\n🎫 کد: {order['code']}")
    lines.append(f"پشتیبانی: {reseller['support_contact'] or 'در دسترس نیست'}")
    await message.answer(
        "\n\n".join(lines),
        reply_markup=customer_main_reply_keyboard(has_support_contact=has_support),
    )

    if reseller and reseller["telegram_numeric_id"]:
        try:
            await message.bot.send_message(
                reseller["telegram_numeric_id"],
                f"🔋 فروش شارژ جدید ثبت شد.\nتعداد: {quantity}\n"
                f"مبلغ کل: {total:,.0f} تومان (از کیف‌پول مشتری کسر و کدها به‌صورت خودکار تحویل داده شدند).",
            )
        except Exception:
            pass
