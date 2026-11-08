"""PayPal Reporting Transactions API response validation and normalization."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.integrations.paypal.exceptions import PayPalInvalidResponseError
from app.integrations.paypal.schemas import PayPalTransaction

_CURRENCY = re.compile(r"^[A-Z]{3}$")
_AMOUNT = re.compile(r"^-?\d{1,12}(?:\.\d{1,2})?$")


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise PayPalInvalidResponseError("PayPal transaction is missing its date.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PayPalInvalidResponseError("PayPal returned an invalid transaction date.") from None
    if parsed.tzinfo is None:
        raise PayPalInvalidResponseError("PayPal returned a transaction date without a timezone.")
    return parsed


def normalize_transaction(row: dict[str, Any]) -> PayPalTransaction:
    """Normalize only the reporting fields needed by the ledger."""

    info = row.get("transaction_info")
    payer = row.get("payer_info") or {}
    if not isinstance(info, dict) or not isinstance(payer, dict):
        raise PayPalInvalidResponseError("PayPal returned an invalid transaction record.")
    raw_id = info.get("transaction_id")
    code = info.get("transaction_event_code")
    amount_info = info.get("transaction_amount")
    if not isinstance(raw_id, str) or not raw_id or not isinstance(code, str) or not code:
        raise PayPalInvalidResponseError("PayPal transaction is missing required identifiers.")
    if not isinstance(amount_info, dict):
        raise PayPalInvalidResponseError("PayPal transaction is missing its amount.")
    raw_amount = amount_info.get("value")
    currency = amount_info.get("currency_code")
    if not isinstance(raw_amount, str) or not _AMOUNT.fullmatch(raw_amount):
        raise PayPalInvalidResponseError("PayPal returned an invalid transaction amount.")
    if not isinstance(currency, str) or not _CURRENCY.fullmatch(currency):
        raise PayPalInvalidResponseError("PayPal returned an invalid transaction currency.")
    try:
        signed_amount = Decimal(raw_amount)
    except InvalidOperation:
        raise PayPalInvalidResponseError("PayPal returned an invalid transaction amount.") from None
    if not signed_amount.is_finite():
        raise PayPalInvalidResponseError("PayPal returned an invalid transaction amount.")

    occurred_at = _parse_time(info.get("transaction_initiation_date"))
    # Transaction Search can include multiple report rows for a transaction ID.
    # This stable compound key preserves those separate events under the ledger's unique constraint.
    external_id = f"{raw_id}:{code}:{occurred_at.isoformat()}"
    status_codes = {"S": "completed", "P": "pending", "D": "denied", "V": "reversed"}
    name_parts = []
    payer_name = payer.get("payer_name") if isinstance(payer.get("payer_name"), dict) else {}
    if payer_name.get("given_name"):
        name_parts.append(payer_name["given_name"])
    if payer_name.get("surname"):
        name_parts.append(payer_name["surname"])
    name = payer_name.get("alternate_full_name") or " ".join(name_parts) or None
    email = payer.get("email_address")
    if not isinstance(email, str):
        email = None
    description = info.get("transaction_subject")
    if not isinstance(description, str):
        description = info.get("transaction_event_description")
    if not isinstance(description, str):
        description = None

    return PayPalTransaction(
        external_transaction_id=external_id[:255],
        transaction_type=code[:64],
        status=status_codes.get(str(info.get("transaction_status", "")).upper(), "unknown"),
        direction="expense" if signed_amount < 0 else "income",
        amount=abs(signed_amount),
        currency=currency,
        occurred_at=occurred_at,
        description=description[:500] if description else None,
        counterparty_name=name[:200] if name else None,
        counterparty_email=email[:254] if email else None,
        # Keep only non-PII reporting identifiers; never persist the full PayPal payload.
        raw_metadata={
            "paypal_transaction_id": raw_id,
            "transaction_event_code": code,
            "paypal_reference_id": info.get("paypal_reference_id"),
        },
    )
