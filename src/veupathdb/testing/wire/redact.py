from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable
from urllib.parse import quote, quote_plus, unquote, unquote_plus

from pydantic import BaseModel, ConfigDict

from veupathdb.testing.wire.key import FAKE_USER_ID

ACCOUNT_EMAIL = "e2e-account@strategist.test"
ACCOUNT_FIRST_NAME = "E2E"
ACCOUNT_LAST_NAME = "Account"
ACCOUNT_ORGANIZATION = "Strategist e2e"
REDACTED = "wire-redacted"

_JWT = re.compile(rb"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
_AUTHORIZATION = re.compile(
    rb"(?i)(authorization[\"']?\s*:\s*)(?:\"[^\"]*\"|'[^']*'|[^\r\n]*)"
)
_COOKIE_HEADER = re.compile(
    rb"(?i)((?:set-)?cookie[\"']?\s*[:=]\s*[\"']?)([^\"'\r\n]*)"
)
_AUTH_KEY = re.compile(
    rb"(?i)(auth[_-]?key[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s;,&\"'\r\n]+)"
)
_PAIR = re.compile(rb"([^=;,\s]+)=([^;,\"'\r\n]*)")
_NAMED_COOKIE = re.compile(rb"(?i)\b(jsessionid|authorization|auth_tkt)=([^;\s\"',&]+)")
_BEARER = re.compile(rb"(?i)\b(bearer\s+)([A-Za-z0-9._~+/=-]+)")
_JSON_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})|\\(.)")
_AT = rb"(?:@|%40|\\u0040|&#64;|&#x40;)"
_SPACE = rb"(?:\s+|\+|%20)"
_DECODINGS = 2


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
    return re.escape(text).encode().replace(rb"\+", rb"(?:\+|%2B)")


def _email(email: str) -> re.Pattern[bytes]:
    local, _, domain = email.partition("@")
    return re.compile(_escaped(local) + _AT + _escaped(domain), re.IGNORECASE)


def _phrase(text: str) -> re.Pattern[bytes]:
    words = [_escaped(word) for word in text.split()]
    return re.compile(_word(_SPACE.join(words)), re.IGNORECASE)


def _encodings(secret: str) -> set[str]:
    json_form = json.dumps(secret)[1:-1]
    return {
        secret,
        quote(secret, safe=""),
        quote_plus(secret, safe=""),
        json_form,
        json_form.replace("/", "\\/"),
        html.escape(secret),
        "".join(f"&#{ord(c)};" for c in secret),
        "".join(f"&#x{ord(c):x};" for c in secret),
    }


def _secret(secret: str) -> re.Pattern[bytes]:
    forms = sorted(_encodings(secret), key=len, reverse=True)
    return re.compile(b"|".join(re.escape(f).encode() for f in forms), re.IGNORECASE)


def _json_unescape(text: str) -> str:
    def one(match: re.Match[str]) -> str:
        code, char = match.groups()
        return chr(int(code, 16)) if code else char

    return _JSON_ESCAPE.sub(one, text)


def normalized_forms(data: bytes) -> set[str]:
    forms = {data.decode("utf-8", errors="replace")}
    for _ in range(_DECODINGS):
        forms |= {
            decode(form)
            for form in forms
            for decode in (unquote, unquote_plus, _json_unescape, html.unescape)
        }
    return {form.lower() for form in forms}


def _redact_pairs(match: re.Match[bytes]) -> bytes:
    pairs = _PAIR.sub(rb"\1=" + REDACTED.encode(), match.group(2))
    return match.group(1) + pairs


class Redactor:
    def __init__(self, identity: Identity, secrets: Iterable[str] = ()) -> None:
        self._identity = identity
        self._user_id = re.compile(_word(str(identity.user_id).encode()))
        named = (
            (identity.email, _email, ACCOUNT_EMAIL),
            (identity.first_name, _phrase, ACCOUNT_FIRST_NAME),
            (identity.last_name, _phrase, ACCOUNT_LAST_NAME),
            (identity.organization, _phrase, ACCOUNT_ORGANIZATION),
        )
        self._values = [
            (pattern(value), placeholder.encode())
            for value, pattern, placeholder in named
            if value.strip()
        ]
        self._secrets: dict[str, re.Pattern[bytes]] = {}
        for secret in secrets:
            self.add_secret(secret)

    def add_secret(self, secret: str) -> None:
        if secret and secret not in self._secrets:
            self._secrets[secret] = _secret(secret)

    def body(self, body: bytes) -> bytes:
        for secret in self._secrets.values():
            body = secret.sub(REDACTED.encode(), body)
        body = _JWT.sub(REDACTED.encode(), body)
        body = _AUTHORIZATION.sub(rb'\1"' + REDACTED.encode() + b'"', body)
        body = _AUTH_KEY.sub(rb'\1"' + REDACTED.encode() + b'"', body)
        body = _COOKIE_HEADER.sub(_redact_pairs, body)
        body = _NAMED_COOKIE.sub(rb"\1=" + REDACTED.encode(), body)
        body = _BEARER.sub(rb"\1" + REDACTED.encode(), body)
        for pattern, placeholder in self._values:
            body = pattern.sub(placeholder, body)
        return self._user_id.sub(str(FAKE_USER_ID).encode(), body)

    def path(self, path: str) -> str:
        return self.body(path.encode()).decode()

    def leaks(self, data: bytes) -> list[str]:
        forms = normalized_forms(data)
        identity = self._identity
        watched = (
            ("email", identity.email),
            ("first name", identity.first_name),
            ("last name", identity.last_name),
            ("organization", identity.organization),
            ("user id", str(identity.user_id)),
            *(("secret", secret) for secret in self._secrets),
        )
        found = [
            label
            for label, value in watched
            if value.strip() and any(value.lower() in form for form in forms)
        ]
        if _JWT.search(data):
            found.append("token")
        return list(dict.fromkeys(found))

    def refuse_leaks(self, data: bytes, what: str) -> None:
        found = self.leaks(data)
        if found:
            msg = f"{what} still holds the account's {', '.join(found)}; it is not written"
            raise LeakError(msg)
