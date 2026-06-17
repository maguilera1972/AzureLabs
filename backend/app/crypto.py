import base64
import hashlib
import os

from cryptography.fernet import Fernet

from app.config import settings


def _derive_key() -> bytes:
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(value: str) -> str:
    f = Fernet(_derive_key())
    return f.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    f = Fernet(_derive_key())
    return f.decrypt(value.encode()).decode()


def generate_password(length: int = 16) -> str:
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%"
    return "".join(alphabet[b % len(alphabet)] for b in os.urandom(length))
