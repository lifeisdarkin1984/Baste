"""
نقطه‌ی ورود پروژه.
دو چیز به‌صورت هم‌زمان (Async) اجرا می‌شود:
  ۱. بات مدیر کل (توکن ثابت از env)
  ۲. DynamicBotManager که بات تمام نماینده‌های فعال را از دیتابیس می‌خواند و
     با polling اجرا می‌کند (بدون نیاز به ری‌استارت کل سرویس هنگام افزودن/حذف نماینده)

همچنین یک تسک پس‌زمینه برای «لایه‌ی دوم اطمینان» (بخش ۳): اگر بعد از X ساعت از
تأیید رسید، دکمه‌ی «فعال شد» زده نشود، به مدیر کل هشدار خودکار ارسال می‌شود.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import Config
from database.db import init_pool, close_pool
from database.migrator import run_migrations
from core.bot_manager import DynamicBotManager
from core.error_handler import register_error_handler
from handlers.admin import register_admin_handlers
from services.order_service import find_orders_pending_activation_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("main")


async def activation_alert_loop(admin_bot: Bot):
    """لایه‌ی دوم اطمینان — بخش ۳ اسپک."""
    while True:
        try:
            stale_orders = await find_orders_pending_activation_alert(
                Config.PENDING_ACTIVATION_ALERT_HOURS
            )
            for order in stale_orders:
                await admin_bot.send_message(
                    Config.SUPER_ADMIN_TELEGRAM_ID,
                    f"⚠️ سفارش {order['order_code']} (نماینده {order['reseller_id']}) "
                    f"بیش از {Config.PENDING_ACTIVATION_ALERT_HOURS} ساعت است تأیید شده "
                    f"ولی هنوز فعال نشده است.",
                )
        except Exception:
            logger.exception("خطا در activation_alert_loop")
        await asyncio.sleep(1800)  # هر ۳۰ دقیقه چک شود


async def run_admin_bot():
    admin_bot = Bot(
        token=Config.SUPER_ADMIN_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    register_error_handler(dp)
    register_admin_handlers(dp)

    asyncio.create_task(activation_alert_loop(admin_bot))
    await dp.start_polling(admin_bot, handle_signals=False)


async def main():
    await init_pool()
    await run_migrations()
    bot_manager = DynamicBotManager()
    try:
        await asyncio.gather(
            run_admin_bot(),
            bot_manager.run_forever(),
        )
    finally:
        await bot_manager.shutdown()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
