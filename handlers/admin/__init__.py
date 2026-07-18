from aiogram import Dispatcher
from handlers.admin.reseller_management import router as reseller_mgmt_router
from handlers.admin.wallet_and_disputes import router as wallet_disputes_router
from handlers.admin.features_and_settings import router as features_settings_router
from handlers.admin.backup import router as backup_router


def register_admin_handlers(dp: Dispatcher) -> None:
    dp.include_router(reseller_mgmt_router)
    dp.include_router(wallet_disputes_router)
    dp.include_router(features_settings_router)
    dp.include_router(backup_router)
