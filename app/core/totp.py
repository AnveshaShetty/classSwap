import hashlib

import pyotp
from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    if not settings.totp_encryption_key:
        raise RuntimeError("TOTP_ENCRYPTION_KEY must be configured before enrolling an admin.")
    return Fernet(settings.totp_encryption_key.encode("ascii"))


def encrypt_totp_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(encrypted_secret: str) -> str:
    return _fernet().decrypt(encrypted_secret.encode("ascii")).decode("ascii")


def new_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="ClassSwap")


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()
