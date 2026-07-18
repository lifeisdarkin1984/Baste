"""
جوین اجباری کانال/گروه (بخش ۷ اسپک، فاز ۲) — نماینده کانال اختصاصی خودش را
تعیین می‌کند و مشتری قبل از خرید باید عضو باشد.
"""
from aiogram import Bot
from database.db import fetch_all, execute


async def get_forced_channels(reseller_id: int) -> list[dict]:
    return await fetch_all(
        "SELECT * FROM forced_join_channels WHERE reseller_id = %s", (reseller_id,)
    )


async def add_forced_channel(reseller_id: int, channel_id: str, set_by: str) -> None:
    await execute(
        "INSERT INTO forced_join_channels (reseller_id, channel_id, set_by) VALUES (%s, %s, %s)",
        (reseller_id, channel_id, set_by),
    )


async def remove_forced_channel(channel_row_id: int) -> None:
    await execute("DELETE FROM forced_join_channels WHERE id = %s", (channel_row_id,))


async def user_has_joined_all(bot: Bot, reseller_id: int, telegram_user_id: int) -> tuple[bool, list[str]]:
    """
    عضویت مشتری را در تمام کانال‌های اجباری این نماینده چک می‌کند.
    خروجی: (همه‌جا عضو است؟, لیست کانال‌هایی که عضو نیست)
    """
    channels = await get_forced_channels(reseller_id)
    missing = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["channel_id"], telegram_user_id)
            if member.status in ("left", "kicked"):
                missing.append(ch["channel_id"])
        except Exception:
            # اگر ربات ادمین کانال نباشد یا کانال در دسترس نباشد، به‌صورت محافظه‌کارانه
            # عضویت را نامعتبر در نظر می‌گیریم تا خطای فنی باعث دور زدن این قابلیت نشود.
            missing.append(ch["channel_id"])
    return (len(missing) == 0, missing)
