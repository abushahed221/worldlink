from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _cipher():
    return Fernet(settings.CHAT_ENCRYPTION_KEY.encode())


def encrypt_text(text):
    if not text:
        return text
    return _cipher().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(text):
    if not text:
        return text
    try:
        return _cipher().decrypt(text.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        # نص غير مشفر (محادثة عادية)
        return text