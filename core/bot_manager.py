"""
Dynamic Bot Manager (بخش ۱ و ۱۰ اسپک)

هر نماینده یک ربات تلگرامی مستقل با توکن خودش دارد. این کلاس لیست نماینده‌های
فعال را از دیتابیس می‌خواند و برای هرکدام یک Bot/Dispatcher جدا با aiogram
polling در قالب یک Async Task اجرا می‌کند. افزودن/حذف نماینده بدون ری‌استارت
کل سرویس ممکن است: فقط یک Task جدید به Event Loop اضافه یا از آن حذف می‌شود.

فاز ۱: Polling (چون تعداد بات‌ها کم است و روی Railway بدون دامنه ساده‌تر است).
اگر تعداد نماینده‌ها بیش از ۱۰-۱۵ شد، مهاجرت به Webhook مشترک توصیه می‌شود
(هر بات روی مسیر /webhook/<bot_id>) — این تغییر در لایه‌ی این کلاس ایزوله است
و بقیه‌ی کد (handlers/services) دست‌نخورده می‌ماند.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from core.encryption import decrypt_token
from core.error_handler import register_error_handler
from database.db import fetch_all
from handlers.reseller import register_reseller_handlers
from handlers.operator import register_operator_handlers
from handlers.customer import register_customer_handlers

logger = logging.getLogger("bot_manager")


class RunningBot:
    def __init__(self, reseller_id: int, bot: Bot, dispatcher: Dispatcher, task: asyncio.Task):
        self.reseller_id = reseller_id
        self.bot = bot
        self.dispatcher = dispatcher
        self.task = task


class DynamicBotManager:
    """مدیریت‌کننده‌ی مرکزی همه‌ی بات‌های نماینده‌ها."""

    def __init__(self):
        self._running: dict[int, RunningBot] = {}   # reseller_id -> RunningBot
        self._poll_interval_seconds = 30             # هر چند وقت لیست نماینده‌های فعال را چک کند

    async def _build_dispatcher_for_reseller(self, reseller_id: int) -> Dispatcher:
        """یک Dispatcher تازه با تمام هندلرهای نماینده/اپراتور/مشتری برای یک ربات خاص می‌سازد."""
        dp = Dispatcher()
        # reseller_id را در workflow_data تزریق می‌کنیم تا هندلرها بدانند این
        # پیام مربوط به کدام نماینده است (چون هر بات فقط برای یک نماینده است).
        dp.workflow_data["reseller_id"] = reseller_id

        register_error_handler(dp)
        register_reseller_handlers(dp)
        register_operator_handlers(dp)
        register_customer_handlers(dp)
        return dp

    async def start_bot(self, reseller_row: dict) -> None:
        """یک بات جدید را (اگر از قبل در حال اجرا نیست) استارت می‌کند."""
        reseller_id = reseller_row["id"]
        if reseller_id in self._running:
            return

        raw_token = decrypt_token(reseller_row["bot_token_encrypted"])
        bot = Bot(token=raw_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = await self._build_dispatcher_for_reseller(reseller_id)

        async def _run():
            try:
                logger.info(f"[reseller {reseller_id}] شروع polling")
                await dp.start_polling(bot, handle_signals=False)
            except asyncio.CancelledError:
                logger.info(f"[reseller {reseller_id}] polling متوقف شد")
            except Exception as e:
                logger.exception(f"[reseller {reseller_id}] خطا در polling: {e}")

        task = asyncio.create_task(_run(), name=f"reseller-bot-{reseller_id}")
        self._running[reseller_id] = RunningBot(reseller_id, bot, dp, task)
        logger.info(f"بات نماینده {reseller_id} ({reseller_row['bot_username']}) اضافه شد.")

    async def stop_bot(self, reseller_id: int) -> None:
        """یک بات در حال اجرا را متوقف می‌کند (مثلاً وقتی نماینده suspend می‌شود)."""
        running = self._running.pop(reseller_id, None)
        if running is None:
            return
        running.task.cancel()
        await running.bot.session.close()
        logger.info(f"بات نماینده {reseller_id} متوقف و حذف شد.")

    async def sync_once(self) -> None:
        """
        لیست نماینده‌های فعال را از دیتابیس می‌خواند:
          - نماینده‌ی فعال جدید که در حال اجرا نیست -> استارت می‌شود
          - نماینده‌ای که suspend/حذف شده ولی هنوز در حال اجراست -> متوقف می‌شود
        این متد اجازه می‌دهد افزودن/تعلیق نماینده بدون ری‌استارت کل سرویس اعمال شود.
        """
        active_resellers = await fetch_all(
            "SELECT * FROM resellers WHERE status = 'active'"
        )
        active_ids = {r["id"] for r in active_resellers}

        # استارت نماینده‌های جدید
        for row in active_resellers:
            if row["id"] not in self._running:
                await self.start_bot(row)

        # توقف نماینده‌هایی که دیگر فعال نیستند
        for reseller_id in list(self._running.keys()):
            if reseller_id not in active_ids:
                await self.stop_bot(reseller_id)

    async def run_forever(self) -> None:
        """حلقه‌ی اصلی: هر ۳۰ ثانیه (قابل تنظیم) تغییرات نماینده‌ها را sync می‌کند."""
        while True:
            try:
                await self.sync_once()
            except Exception:
                logger.exception("خطا در sync_once")
            await asyncio.sleep(self._poll_interval_seconds)

    async def shutdown(self) -> None:
        for reseller_id in list(self._running.keys()):
            await self.stop_bot(reseller_id)
