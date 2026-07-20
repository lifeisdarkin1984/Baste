"""
هندلر سراسری خطا — بدون این، وقتی داخل یه هندلر استثنا رخ بده، aiogram فقط
تو لاگ (که فقط تو Railway Deploy Logs دیده می‌شه) چاپش می‌کنه و کاربر هیچ
پاسخی نمی‌گیره (سکوت کامل، انگار دکمه اصلاً کار نکرده). این فایل اون رو
درست می‌کنه: خطا کامل با traceback لاگ می‌شه و به کاربر یه پیام قابل فهم
داده می‌شه، تا (۱) کاربر بی‌پاسخ نمونه و (۲) خط دقیق خطا تو لاگ Railway پیدا بشه.

استفاده (روی هر Dispatcher که ساخته میشه، هم بات ادمین هم هر بات نماینده):
    from core.error_handler import register_error_handler
    register_error_handler(dp)
"""
import logging

from aiogram import Dispatcher
from aiogram.types import ErrorEvent

logger = logging.getLogger("errors")

USER_ERROR_MESSAGE = "⚠️ مشکلی پیش اومد. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."


def register_error_handler(dp: Dispatcher) -> None:
    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        update = event.update
        # لاگ کامل با traceback -> این دقیقاً همون چیزیه که تو Deploy Logs
        # لازم داریم تا علت اصلی خطاهای «بی‌پاسخ» مثل دکمه‌ی خرید رو پیدا کنیم.
        logger.exception(
            "خطای پردازش‌نشده در آپدیت %s: %s", update.update_id, event.exception
        )

        target_message = None
        if update.message:
            target_message = update.message
        elif update.callback_query and update.callback_query.message:
            target_message = update.callback_query.message

        if target_message is not None:
            try:
                await target_message.answer(USER_ERROR_MESSAGE)
            except Exception:
                logger.exception("ارسال پیام خطا به کاربر هم ناموفق بود.")

        if update.callback_query:
            try:
                await update.callback_query.answer(USER_ERROR_MESSAGE, show_alert=True)
            except Exception:
                pass

        return True
