import re
import secrets


def redact(value: str) -> str:
    value = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", value)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "[REDACTED]", value)
    value = re.sub(
        r"(?i)((?:api[_ -]?key|access[_ -]?token|password|secret|mật khẩu)\s*[:=]\s*)([^\s,;]+)",
        r"\1[REDACTED]",
        value,
    )
    return value


def matches(value, expected):
    return bool(expected) and secrets.compare_digest(
        (value or "").encode("utf-8"), expected.encode("utf-8")
    )


def clean(settings, value):
    for secret in [
        settings.mock_webhook_secret,
        settings.claude_api_key.get_secret_value(),
        *settings.auth_tokens_json,
    ]:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return redact(value)


def dangerous(question):
    # Narrow security guard, not an intent/spam classifier.
    q = question.casefold()
    secret = any(x in q for x in ["api key", "api_key", "mật khẩu", "password", "access token"])
    demand = any(
        x in q
        for x in [
            "cho mình xin",
            "cho em xin",
            "tiết lộ",
            "in ra",
            "in api",
            "show me",
            "reveal",
            "cung cấp",
        ]
    )
    return secret and demand
