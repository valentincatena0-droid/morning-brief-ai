"""Hard guard for the money rule. This project has NO broker, bank, exchange or payment integration.
Any code path that would spend, buy, sell, transfer, invest or commit money must call `require_confirmation`,
which always raises unless a human explicitly supplied a confirmation token out-of-band (not implemented on purpose)."""
from __future__ import annotations


class ConfirmationRequired(Exception):
    """Raised for any action with monetary consequences. Nothing in this repo catches it and proceeds."""


def require_confirmation(action: str, amount: str | None = None) -> None:
    raise ConfirmationRequired(
        f"Refusing to perform monetary action '{action}'{' (' + amount + ')' if amount else ''}: "
        "explicit human confirmation is required and automated execution is disabled.")


def assert_read_only(settings: dict) -> None:
    fin = settings.get("finance", {})
    if fin.get("trading_enabled"):
        require_confirmation("enable trading", "settings.finance.trading_enabled=true")
