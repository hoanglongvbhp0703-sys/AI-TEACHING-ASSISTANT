"""Argon2id password hashing. Cleartext passwords are never persisted."""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def hash_password(password):
    return HASHER.hash(password)


def verify_password(encoded, password):
    try:
        return HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False
