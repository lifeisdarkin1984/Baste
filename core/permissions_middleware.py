"""
میان‌افزار مجوز — مطمئن می‌شود فقط خود نماینده (صاحب ربات) یا اپراتور فعال او
می‌تواند رسید را تأیید/رد کند، سفارش را فعال کند یا درخواست استرداد ثبت کند.
اپراتور طبق بخش ۷ اسپک هرگز نباید به کیف‌پول/تنظیمات/گزارش سود دسترسی داشته
باشد؛ این میان‌افزار فقط روی اکشن‌های سفارش اعمال می‌شود (نه روی هندلرهای
کیف‌پول/کاتالوگ که در روتر جدا هستند).
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from database.db import fetch_one


class OrderActionPermissionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        reseller_id = data.get("reseller_id")
        user_id = event.from_user.id

        reseller = await fetch_one(
            "SELECT telegram_numeric_id FROM resellers WHERE id = %s", (reseller_id,)
        )
        if reseller and reseller["telegram_numeric_id"] == user_id:
            return await handler(event, data)

        operator = await fetch_one(
            "SELECT id FROM reseller_operators WHERE reseller_id = %s "
            "AND telegram_user_id = %s AND status = 'active'",
            (reseller_id, user_id),
        )
        if operator:
            return await handler(event, data)

        await event.answer("⛔️ شما مجاز به انجام این عملیات نیستید.", show_alert=True)
        return None
