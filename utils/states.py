from aiogram.fsm.state import State, StatesGroup


class CustomerOrderStates(StatesGroup):
    choosing_package = State()
    waiting_receipt = State()


class ResellerPackageStates(StatesGroup):
    entering_name = State()
    entering_price = State()
    confirming_suspicious_price = State()   # هشدار Sanity Check
    entering_cost_price = State()


class ResellerDisputeStates(StatesGroup):
    entering_reason = State()


class ResellerTopupStates(StatesGroup):
    choosing_method = State()
    entering_amount = State()
    uploading_receipt = State()


class SuperAdminResellerStates(StatesGroup):
    entering_bot_token = State()
    entering_telegram_id = State()
    entering_commission_percent = State()
    entering_credit_limit = State()
    entering_order_prefix = State()
