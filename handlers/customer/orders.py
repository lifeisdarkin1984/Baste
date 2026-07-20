"""
هندلرهای پنل مشتری نهایی (بخش ۴ و ۷ اسپک) + ناوبری پوشه‌ای کاتالوگ و خرید
خودکار از کیف‌پول (فیچر جدید طبق درخواست).

ساختار ناوبری (همه با کیبورد پایین صفحه، نه inline):
  🛍 مشاهده کاتالوگ
    -> لیست اپراتورها (پوشه اصلی)
       -> لیست زیرپوشه‌ها (روزانه/هفتگی/ماهانه/...)
          -> لیست بسته‌ها
             -> جزئیات بسته + دکمه‌ی متنی «🛒 خرید این بسته»

موقع زدن «خرید»:
  ۱. اگر موجودی کیف‌پول مشتری کافی باشد -> کسر خودکار، سفارش مستقیم confirmed،
     نیازی به رسید/تأیید نماینده نیست (فقط فعال‌سازی نهایی).
  ۲. در غیر این صورت -> فلوی قبلی: نمایش کارت‌ها/زرین‌پال نماینده + آپلود رسید.
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import fetch_all, fetch_one, execute
from services.order_service import (
    get_or_create_customer,
    create_order,
    create_order_paid_by_wallet,
    submit_receipt,
    PendingOrderLimitExceeded,
    CustomerBlacklistedError,
    OrderInsufficientCreditError,
    WalletInsufficientBalanceError,
)
from services.notifications import (
    notify_reseller_insufficient_credit,
    notify_super_admin_insufficient_credit,
)
from services.forced_join_service import user_has_joined_all
from services.referral_service import register_referral
from services.discount_service import validate_discount_code, apply_discount, increment_usage, InvalidDiscountCode
from services.payment_methods_service import list_cards, get_zarinpal_merchant, format_card_number
from services.customer_wallet_service import get_wallet_balance
from utils.states import CustomerOrderStates, CustomerCatalogStates
from utils.keyboards import (
    customer_main_reply_keyboard,
    customer_folder_reply_keyboard,
    customer_package_detail_keyboard,
    activate_order_button,
    CUSTOMER_CATALOG_BUTTON_TEXT,
    CUSTOMER_SUPPORT_BUTTON_TEXT,
    CUSTOMER_WALLET_BUTTON_TEXT,
    CUSTOMER_BACK_BUTTON_TEXT,
    CUSTOMER_BACK_TO_MENU_BUTTON_TEXT,
    CUSTOMER_BUY_BUTTON_TEXT,
)

router = Router(name="customer_orders")


@router.message(F.text.startswith("/start"))
async def customer_start(message: Message, reseller_id: int, state: FSMContext):
    await state.clear()
    # لینک رفرال: https://t.me/<bot>?start=ref_<customer_id>
    parts = message.text.split(maxsplit=1)
    customer = await get_or_create_customer(reseller_id, message.from_user.id)

    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            referrer_customer_id = int(parts[1].removeprefix("ref_"))
            await register_referral(reseller_id, referrer_customer_id, customer["id"])
        except ValueError:
            pass

    reseller = await fetch_one("SELECT support_contact FROM resellers WHERE id = %s", (reseller_id,))
    has_support = bool(reseller and reseller["support_contact"])

    await message.answer(
        "به ربات فروش خوش آمدید! 👋\nبرای مشاهده‌ی بسته‌ها از دکمه‌ی زیر (پایین صفحه) استفاده کنید.",
        reply_markup=customer_main_reply_keyboard(has_support_contact=has_support),
    )


async def _back_to_main_menu(message: Message, reseller_id: int, state: FSMContext):
    await state.clear()
    reseller = await fetch_one("SELECT support_contact FROM resellers WHERE id = %s", (reseller_id,))
    has_support = bool(reseller and reseller["support_contact"])
    await message.answer("منوی اصلی:", reply_markup=customer_main_reply_keyboard(has_support_contact=has_support))


@router.message(F.text == CUSTOMER_SUPPORT_BUTTON_TEXT)
async def show_support_from_keyboard(message: Message, reseller_id: int):
    reseller = await fetch_one("SELECT support_contact FROM resellers WHERE id = %s", (reseller_id,))
    contact = reseller["support_contact"] if reseller else None
    await message.answer(f"📞 پشتیبانی: {contact or 'در دسترس نیست'}")


# ==========================================================================
# سطح ۱: لیست اپراتورها (پوشه اصلی)
# ==========================================================================
async def _show_operators(message: Message, reseller_id: int, user_id: int, state: FSMContext):
    joined, missing_channels = await user_has_joined_all(message.bot, reseller_id, user_id)
    if not joined:
        channels_text = "\n".join(f"- {c}" for c in missing_channels)
        await message.answer(
            f"⛔️ برای مشاهده‌ی کاتالوگ ابتدا باید عضو کانال(های) زیر شوید:\n{channels_text}\n\n"
            f"بعد از عضویت، دوباره روی «{CUSTOMER_CATALOG_BUTTON_TEXT}» بزنید."
        )
        return

    operators = await fetch_all(
        "SELECT id, operator_name FROM categories WHERE reseller_id = %s AND parent_category_id IS NULL",
        (reseller_id,),
    )
    if not operators:
        await message.answer("در حال حاضر بسته‌ای ثبت نشده است.")
        return

    operator_map = {f"📁 {op['operator_name']}": op["id"] for op in operators}
    await state.set_state(CustomerCatalogStates.browsing_operators)
    await state.update_data(operator_map=operator_map)
    await message.answer(
        "یک اپراتور را انتخاب کنید:",
        reply_markup=customer_folder_reply_keyboard(list(operator_map.keys()), back_text=CUSTOMER_BACK_TO_MENU_BUTTON_TEXT),
    )


@router.message(F.text == CUSTOMER_CATALOG_BUTTON_TEXT)
async def show_catalog_from_keyboard(message: Message, reseller_id: int, state: FSMContext):
    await _show_operators(message, reseller_id, message.from_user.id, state)


@router.message(CustomerCatalogStates.browsing_operators)
async def handle_operator_pick(message: Message, reseller_id: int, state: FSMContext):
    if message.text == CUSTOMER_BACK_TO_MENU_BUTTON_TEXT:
        await _back_to_main_menu(message, reseller_id, state)
        return

    data = await state.get_data()
    operator_id = data.get("operator_map", {}).get(message.text)
    if operator_id is None:
        await message.answer("لطفاً یکی از گزینه‌های روی کیبورد را انتخاب کنید.")
        return

    subcategories = await fetch_all(
        "SELECT id, title FROM categories WHERE parent_category_id = %s", (operator_id,)
    )
    if not subcategories:
        await message.answer("این اپراتور هنوز زیرپوشه‌ای (مثل ماهانه/هفتگی) ندارد.")
        return

    subcategory_map = {f"📂 {c['title']}": c["id"] for c in subcategories}
    await state.set_state(CustomerCatalogStates.browsing_subcategories)
    await state.update_data(subcategory_map=subcategory_map)
    await message.answer(
        "یک زیرپوشه را انتخاب کنید:",
        reply_markup=customer_folder_reply_keyboard(list(subcategory_map.keys()), back_text=CUSTOMER_BACK_BUTTON_TEXT),
    )


@router.message(CustomerCatalogStates.browsing_subcategories)
async def handle_subcategory_pick(message: Message, reseller_id: int, state: FSMContext):
    if message.text == CUSTOMER_BACK_BUTTON_TEXT:
        await _show_operators(message, reseller_id, message.from_user.id, state)
        return

    data = await state.get_data()
    category_id = data.get("subcategory_map", {}).get(message.text)
    if category_id is None:
        await message.answer("لطفاً یکی از گزینه‌های روی کیبورد را انتخاب کنید.")
        return

    packages = await fetch_all(
        "SELECT id, name, sale_price FROM packages WHERE category_id = %s AND is_active = TRUE",
        (category_id,),
    )
    if not packages:
        await message.answer("در این زیرپوشه هنوز بسته‌ای ثبت نشده است.")
        return

    package_map = {f"📦 {p['name']} — {p['sale_price']:,.0f} تومان": p["id"] for p in packages}
    await state.update_data(package_map=package_map)
    await state.set_state(CustomerCatalogStates.browsing_packages)
    await message.answer(
        "یک بسته را انتخاب کنید:",
        reply_markup=customer_folder_reply_keyboard(list(package_map.keys()), back_text=CUSTOMER_BACK_BUTTON_TEXT),
    )


@router.message(CustomerCatalogStates.browsing_packages)
async def handle_package_pick(message: Message, reseller_id: int, state: FSMContext):
    data = await state.get_data()
    if message.text == CUSTOMER_BACK_BUTTON_TEXT:
        operator_map = data.get("operator_map", {})
        await state.set_state(CustomerCatalogStates.browsing_operators)
        await message.answer(
            "یک اپراتور را انتخاب کنید:",
            reply_markup=customer_folder_reply_keyboard(list(operator_map.keys()), back_text=CUSTOMER_BACK_TO_MENU_BUTTON_TEXT),
        )
        return

    package_id = data.get("package_map", {}).get(message.text)
    if package_id is None:
        await message.answer("لطفاً یکی از گزینه‌های روی کیبورد را انتخاب کنید.")
        return

    package = await fetch_one(
        "SELECT p.id, p.name, p.sale_price, c.operator_name, c.title "
        "FROM packages p JOIN categories c ON p.category_id = c.id WHERE p.id = %s",
        (package_id,),
    )
    if package is None:
        await message.answer("این بسته دیگر موجود نیست.")
        return

    await state.set_state(CustomerCatalogStates.package_selected)
    await state.update_data(selected_package_id=package_id)
    await message.answer(
        f"📦 {package['operator_name']} - {package['title']}\n{package['name']}\n"
        f"💰 {package['sale_price']:,.0f} تومان\n\n"
        f"برای خرید، دکمه‌ی «{CUSTOMER_BUY_BUTTON_TEXT}» را بزنید.",
        reply_markup=customer_package_detail_keyboard(),
    )


@router.message(CustomerCatalogStates.package_selected, F.text == CUSTOMER_BACK_BUTTON_TEXT)
async def handle_package_detail_back(message: Message, reseller_id: int, state: FSMContext):
    data = await state.get_data()
    package_map = data.get("package_map", {})
    await state.set_state(CustomerCatalogStates.browsing_packages)
    await message.answer(
        "یک بسته را انتخاب کنید:",
        reply_markup=customer_folder_reply_keyboard(list(package_map.keys()), back_text=CUSTOMER_BACK_BUTTON_TEXT),
    )


@router.message(CustomerCatalogStates.package_selected, F.text == CUSTOMER_BUY_BUTTON_TEXT)
async def handle_buy_button(message: Message, reseller_id: int, state: FSMContext):
    data = await state.get_data()
    package_id = data.get("selected_package_id")
    if package_id is None:
        await _back_to_main_menu(message, reseller_id, state)
        return

    customer = await get_or_create_customer(reseller_id, message.from_user.id)

    # مرحله ۱: تلاش برای پرداخت خودکار از کیف‌پول مشتری
    try:
        order = await create_order_paid_by_wallet(reseller_id, package_id, customer["id"])
    except CustomerBlacklistedError:
        await message.answer("⛔️ امکان ثبت سفارش برای شما وجود ندارد.")
        await state.clear()
        return
    except WalletInsufficientBalanceError:
        order = None
    else:
        await state.clear()
        reseller = await fetch_one(
            "SELECT telegram_numeric_id, support_contact FROM resellers WHERE id = %s", (reseller_id,)
        )
        await message.answer(
            f"✅ پرداخت از کیف‌پول شما با موفقیت انجام شد.\nشناسه سفارش: {order['order_code']}\n"
            f"سفارش شما تأیید شد و به‌زودی توسط نماینده فعال می‌شود.\n"
            f"پشتیبانی: {reseller['support_contact'] or 'در دسترس نیست'}"
        )
        if reseller and reseller["telegram_numeric_id"]:
            try:
                await message.bot.send_message(
                    reseller["telegram_numeric_id"],
                    f"🛒 سفارش جدید {order['order_code']} با پرداخت خودکار از کیف‌پول مشتری ثبت شد "
                    f"(مبلغ: {order['package_price']:,.0f} تومان).\nبعد از فعال‌سازی دستی بسته، دکمه‌ی زیر را بزنید.",
                    reply_markup=activate_order_button(order["id"]),
                )
            except Exception:
                pass
        return

    # مرحله ۲: موجودی کافی نبود -> فلوی عادی رسید
    try:
        order = await create_order(reseller_id, package_id, customer["id"])
    except CustomerBlacklistedError:
        await message.answer("⛔️ امکان ثبت سفارش برای شما وجود ندارد.")
        await state.clear()
        return

    reseller = await fetch_one(
        "SELECT support_contact FROM resellers WHERE id = %s", (reseller_id,)
    )

    await state.update_data(order_id=order["id"])
    await state.set_state(CustomerOrderStates.waiting_receipt)

    active_cards = await list_cards(reseller_id, only_active=True)
    zarinpal_merchant = await get_zarinpal_merchant(reseller_id)

    payment_lines = []
    for c in active_cards:
        line = f"💳 {format_card_number(c['card_number'])} | به‌نام: {c['card_holder_name']}"
        if c["bank_name"]:
            line += f" | {c['bank_name']}"
        payment_lines.append(line)

    if zarinpal_merchant:
        payment_lines.append("🔗 پرداخت آنلاین از طریق زرین‌پال هم برای این نماینده فعال است.")

    if not payment_lines:
        payment_info = "⚠️ نماینده هنوز روش دریافت وجهی ثبت نکرده؛ برای روش پرداخت با پشتیبانی هماهنگ کنید."
    else:
        payment_info = "\n".join(payment_lines)

    await message.answer(
        f"موجودی کیف‌پول شما کافی نیست، پس سفارش با روش رسیدی ثبت شد ✅\n"
        f"شناسه سفارش: {order['order_code']}\n"
        f"مبلغ قابل پرداخت: {order['package_price']:,.0f} تومان\n\n"
        f"{payment_info}\n\n"
        f"اگر کد تخفیف دارید، با فرمت زیر ارسال کنید:\n/discount CODE\n\n"
        f"بعد از پرداخت، تصویر رسید را همینجا ارسال کنید.\n"
        f"پشتیبانی: {reseller['support_contact'] or 'در دسترس نیست'}"
    )


@router.message(CustomerOrderStates.waiting_receipt, F.text.startswith("/discount "))
async def apply_discount_code(message: Message, state: FSMContext, reseller_id: int):
    code = message.text.split(maxsplit=1)[1].strip()
    data = await state.get_data()
    order_id = data.get("order_id")
    order = await fetch_one("SELECT * FROM orders WHERE id = %s", (order_id,))

    try:
        discount_row = await validate_discount_code(reseller_id, code)
    except InvalidDiscountCode as e:
        await message.answer(f"⛔️ {e}")
        return

    new_price = apply_discount(Decimal(order["package_price"]), discount_row)
    await execute("UPDATE orders SET package_price = %s WHERE id = %s", (new_price, order_id))
    await increment_usage(discount_row["id"])

    await message.answer(
        f"کد تخفیف اعمال شد ✅\nمبلغ جدید قابل پرداخت: {new_price:,.0f} تومان\n"
        f"حالا تصویر رسید پرداخت را ارسال کنید."
    )


@router.message(CustomerOrderStates.waiting_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext, reseller_id: int):
    data = await state.get_data()
    order_id = data.get("order_id")
    receipt_file_id = message.photo[-1].file_id

    try:
        order = await submit_receipt(order_id, receipt_file_id)
    except PendingOrderLimitExceeded as e:
        await message.answer(
            f"⛔️ {e}\nلطفاً منتظر بررسی سفارش‌های در انتظار قبلی خود بمانید."
        )
        return
    except OrderInsufficientCreditError as e:
        await notify_reseller_insufficient_credit(message.bot, e.reseller_id, e.order_code)
        await notify_super_admin_insufficient_credit(e.reseller_id, e.order_code)
        await state.clear()
        reseller = await fetch_one("SELECT support_contact FROM resellers WHERE id = %s", (reseller_id,))
        has_support = bool(reseller and reseller["support_contact"])
        await message.answer(
            "رسید شما دریافت شد، ولی پردازش سفارش به‌طور موقت با تأخیر مواجه شده. "
            "به‌زودی توسط نماینده پیگیری می‌شود.",
            reply_markup=customer_main_reply_keyboard(has_support_contact=has_support),
        )
        return

    await state.clear()
    reseller = await fetch_one("SELECT support_contact FROM resellers WHERE id = %s", (reseller_id,))
    has_support = bool(reseller and reseller["support_contact"])
    await message.answer(
        f"رسید دریافت شد ✅\nسفارش {order['order_code']} در انتظار بررسی نماینده است.",
        reply_markup=customer_main_reply_keyboard(has_support_contact=has_support),
    )
