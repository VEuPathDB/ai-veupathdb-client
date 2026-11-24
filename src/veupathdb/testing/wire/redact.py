from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from veupathdb.testing.wire.key import FAKE_USER_ID

ACCOUNT_EMAIL = "e2e-account@strategist.test"
ACCOUNT_FIRST_NAME = "E2E"
ACCOUNT_LAST_NAME = "Account"
ACCOUNT_ORGANIZATION = "Strategist e2e"
REDACTED = "wire-redacted"

_JWT = re.compile(rb"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
_CREDENTIAL = re.compile(
    rb"(?i)\b((?:set-)?cookie|authorization|jsessionid|auth[_-]?key|auth_tkt)"
    rb"([\"']?\s*[:=]\s*[\"']?)(bearer\s+)?([^;\s\"',&]+)"
)
_BEARER = re.compile(rb"(?i)\b(bearer\s+)([A-Za-z0-9._~+/=-]+)")
_AT = rb"(?:@|%40|\\u0040|&#64;)"
_SPACE = rb"(?:\s+|\+|%20)"


class LeakError(ValueError):
    pass


class Identity(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: int
    email: str
    first_name: str = ""
    last_name: str = ""
    organization: str = ""


def _word(pattern: bytes) -> bytes:
    return rb"(?<![A-Za-z0-9])" + pattern + rb"(?![A-Za-z0-9])"


def _escaped(text: str) -> bytes:
    escaped = re.escape(text).encode()
    return escaped.replace(rb"\+", rb"(?:\+|%2B)")


def _email(email: str) -> re.Pattern[bytes]:
    local, _, domain = email.partition("@")
    return re.compile(_escaped(local) + _AT + _escaped(domain), re.IGNORECASE)


def _phrase(text: str) -> re.Pattern[bytes]:
    words = [_escaped(word) for word in text.split()]
    return re.compile(_word(_SPACE.join(words)), re.IGNORECASE)


class Redactor:
    def __init__(self, identity: Identity, secrets: Iterable[str] = ()) -> None:
        self._user_id = re.compile(_word(str(identity.user_id).encode()))
        named = (
            ("email", identity.email, _email, ACCOUNT_EMAIL),
            ("first name", identity.first_name, _phrase, ACCOUNT_FIRST_NAME),
            ("last name", identity.last_name, _phrase, ACCOUNT_LAST_NAME),
            ("organization", identity.organization, _phrase, ACCOUNT_ORGANIZATION),
        )
        self._values = [
            (label, pattern(value), placeholder.encode())
            for label, value, pattern, placeholder in named
            if value.strip()
        ]
        self._secrets = [
            re.compile(re.escape(secret).encode(), re.IGNORECASE)
            for secret in secrets
            if secret
        ]

    def add_secret(self, secret: str) -> None:
        if secret:
            self._secrets.append(re.compile(re.escape(secret).encode(), re.IGNORECASE))

    def body(self, body: bytes) -> bytes:
        for secret in self._secrets:
            body = secret.sub(REDACTED.encode(), body)
        body = _JWT.sub(REDACTED.encode(), body)
        body = _CREDENTIAL.sub(rb"\1\2\3" + REDACTED.encode(), body)
        body = _BEARER.sub(rb"\1" + REDACTED.encode(), body)
        for _, pattern, placeholder in self._values:
            body = pattern.sub(placeholder, body)
        return self._user_id.sub(str(FAKE_USER_ID).encode(), body)

    def path(self, path: str) -> str:
        return self.body(path.encode()).decode()

    def leaks(self, data: bytes) -> list[str]:
        found = [label for label, pattern, _ in self._values if pattern.search(data)]
        if self._user_id.search(data):
            found.append("user id")
        if any(secret.search(data) for secret in self._secrets):
            found.append("secret")
        if _JWT.search(data):
            found.append("token")
        credentials = [*_CREDENTIAL.finditer(data), *_BEARER.finditer(data)]
        if any(
            match.group(match.lastindex or 0) != REDACTED.encode()
            for match in credentials
        ):
            found.append("credential")
        return found

    def refuse_leaks(self, data: bytes, what: str) -> None:
        found = self.leaks(data)
        if found:
            msg = f"{what} still holds the account's {', '.join(found)}; it is not written"
            raise LeakError(msg)
