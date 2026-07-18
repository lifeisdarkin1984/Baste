"""
رمزنگاری/رمزگشایی توکن ربات نماینده‌ها قبل از ذخیره در دیتابیس (بخش ۱۱).
کلید از TOKEN_ENCRYPTION_KEY در Environment Variables خوانده می‌شود.
تولید کلید جدید: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from cryptography.fernet import Fernet
from config import Config

_fernet = Fernet(Config.TOKEN_ENCRYPTION_KEY.encode())


def encrypt_token(raw_token: str) -> str:
    return _fernet.encrypt(raw_token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    return _fernet.decrypt(encrypted_token.encode()).decode()
