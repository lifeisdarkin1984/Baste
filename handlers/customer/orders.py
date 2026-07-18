"""
هندلرهای پنل مشتری نهایی (بخش ۴ و ۷ اسپک).
"""
from decimal import Decimal, InvalidOperation

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import fetch_all, fetch_one, execute
from services.order_service import (
    get_or_create_customer,
    create_order,
    submit_receipt,
    PendingOrderLimitExceeded,
    CustomerBlacklistedError,
    OrderInsufficientCreditError,
)
from services.notifications import (
    notify_reseller_insufficient_credit,
    notify_super_admin_insufficient_credit,
)
from services.forced_join_service import user_has_joined_all
from services.referral_service import register_referral
from services.discount_service import validate_discount_code, apply_discount, increment_usage, InvalidDiscountCode
from services.payment_methods_service import list_cards, get_zarinpal_merchant, format_card_number
from utils.states import CustomerOrderStates
from utils.keyboards import catalog_button, package_purchase_button

router = Router(name="customer_orders")


@router.message(F.text.startswith("/start"))
async def customer_start(message: Message, reseller_id: int):
    # لینک رفرال: https://t.me/<bot>?start=ref_<customer_id>
    parts = message.text.split(maxsplit=1)
    customer = await get_or_create_customer(reseller_id, message.from_user.id)

    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            referrer_customer_id = int(parts[1].removeprefix("ref_"))
            await register_referral(reseller_id, referrer_customer_id, customer["id"])
        except ValueError:
            pass

    await message.answer(
        "به ربات فروش خوش آمدید! 👋\nبرای مشاهده‌ی بسته‌ها روی دکمه زیر بزنید.",
        reply_markup=catalog_button(),
    )


@router.callback_query(F.data == "show_catalog")
async def show_catalog(callback: CallbackQuery, reseller_id: int):
    # جوین اجباری: بخش ۷ اسپک، فاز ۲
    joined, missing_channels = await user_has_joined_all(callback.bot, reseller_id, callback.from_user.id)
    if not joined:
        channels_text = "\n".join(f"- {c}" for c in missing_channels)
        await callback.message.answer(
            f"⛔️ برای مشاهده‌ی کاتالوگ ابتدا باید عضو کانال(های) زیر شوید:\n{channels_text}\n\n"
            f"بعد از عضویت، دوباره روی «مشاهده کاتالوگ» بزنید.",
            reply_markup=catalog_button(),
        )
        await callback.answer()
        return

    packages = await fetch_all(
        "SELECT p.id, p.name, p.sale_price, c.operator_name, c.title "
        "FROM packages p JOIN categories c ON p.category_id = c.id "
        "WHERE p.reseller_id = %s AND p.is_active = TRUE",
        (reseller_id,),
    )
    if not packages:
        await callback.message.answer("در حال حاضر بسته‌ای ثبت نشده است.")
        return

    for pkg in packages:
        text = f"📦 {pkg['operator_name']} - {pkg['title']}\n{pkg['name']}\n💰 {pkg['sale_price']:,.0f} تومان"
        await callback.message.answer(text, reply_markup=package_purchase_button(pkg["id"]))
    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_package(callback: CallbackQuery, reseller_id: int, state: FSMContext):
    package_id = int(callback.data.split(":")[1])
    customer = await get_or_create_customer(reseller_id, callback.from_user.id)
    try:
        order = await create_order(reseller_id, package_id, customer["id"])
    except CustomerBlacklistedError:
        await callback.message.answer("⛔️ امکان ثبت سفارش برای شما وجود ندارد.")
        await callback.answer()
        return

    reseller = await fetch_one(
        "SELECT support_contact FROM resellers WHERE id = %s", (reseller_id,)
    )

    await state.update_data(order_id=order["id"])
    await state.set_state(CustomerOrderStates.waiting_receipt)

    # «روش دریافت وجه از مشتری» — کارت‌های فعال نماینده + زرین‌پال شخصی او (اگر تنظیم شده)
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

    await callback.message.answer(
        f"سفارش شما ثبت شد ✅\nشناسه سفارش: {order['order_code']}\n"
        f"مبلغ قابل پرداخت: {order['package_price']:,.0f} تومان\n\n"
        f"{payment_info}\n\n"
        f"اگر کد تخفیف دارید، با فرمت زیر ارسال کنید:\n/discount CODE\n\n"
        f"بعد از پرداخت، تصویر رسید را همینجا ارسال کنید.\n"
        f"پشتیبانی: {reseller['support_contact'] or 'در دسترس نیست'}"
    )
    await callback.answer()


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
async def receive_receipt(message: Message, state: FSMContext):
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
        # رفع باگ: قبلاً اینجا فقط یک کامنت ادعا می‌کرد به نماینده/مدیر کل اطلاع
        # داده می‌شود ولی هیچ پیامی واقعاً ارسال نمی‌شد و وضعیت سفارش هم به‌اشتباه
        # به‌صورت عادی (awaiting_receipt_review) commit شده بود. حالا order_service
        # وضعیت را روی failed_insufficient_credit ثبت می‌کند (اتمیک) و اینجا واقعاً
        # به هر دو طرف پیام می‌فرستیم.
        await notify_reseller_insufficient_credit(message.bot, e.reseller_id, e.order_code)
        await notify_super_admin_insufficient_credit(e.reseller_id, e.order_code)
        await message.answer(
            "رسید شما دریافت شد، ولی پردازش سفارش به‌طور موقت با تأخیر مواجه شده. "
            "به‌زودی توسط نماینده پیگیری می‌شود."
        )
        await state.clear()
        return

    await message.answer(
        f"رسید دریافت شد ✅\nسفارش {order['order_code']} در انتظار بررسی نماینده است."
    )
    await state.clear()
