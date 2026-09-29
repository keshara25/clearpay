"""Pure decision rules. No network, database or UI dependencies."""
from datetime import datetime, timezone, timedelta

VERSION = "1.0.0"
REQUIRED = ("amount_minor", "account", "reference", "paid_at", "currency")

def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone is required")
    return result.astimezone(timezone.utc)

def decide(order, slip, messages, claims=(), image_used=False, now=None):
    now = now or datetime.now(timezone.utc)
    checks = []
    def outcome(status, code, reason, next_action, customer, sms_id=None):
        return dict(status=status, code=code, reason=reason, next_action=next_action,
                    customer_message=customer, checks=checks, sms_id=sms_id,
                    policy_version=VERSION, certainty="Corroborated" if status == "APPROVED" else
                    "Evidence conflict" if status == "REJECTED" else "Uncertain")
    def review(code, reason):
        return outcome("NEEDS VERIFICATION", code, reason,
                       "Review the evidence or wait for an authenticated bank notification, then recheck.",
                       "We are checking your payment. Please wait or contact the business.")
    def reject(code, reason):
        return outcome("REJECTED", code, reason, "Ask for the correct payment evidence; do not fulfil this order.",
                       "This payment could not be accepted for your order. Please check the details or contact the business.")
    if image_used:
        return reject("DUPLICATE_IMAGE", "This exact image already supports an accepted payment.")
    # OCR certainty is an extraction gate, never a probability that money was received.
    if slip.get("source") != "ocr" or slip.get("confidence", 0) < .90 or slip.get("issues"):
        result = review("UNRELIABLE_EXTRACTION", "The image could not be read reliably, or only manual transcription is available.")
        result["customer_message"] = "Please send a clearer image of the complete payment slip."
        return result
    if any(slip.get(key) in (None, "") for key in REQUIRED):
        # Some otherwise legible bank layouts use labels/date formats outside
        # the deliberately narrow parser. A clearer copy will not fix that.
        compact_text = "".join(c for c in slip.get("text", "").lower() if c.isalpha())
        if all(label in compact_text for label in ("transactionamount", "transactionid", "toaccountnumber")):
            result = review("UNSUPPORTED_RECEIPT_FORMAT", "This readable receipt layout is not supported by the automatic field parser; required transaction fields cannot be verified safely.")
            result["next_action"] = "Keep fulfilment on hold. Reconcile the transfer with the merchant bank record and order before deciding."
            result["customer_message"] = "We received your payment slip, but cannot verify this format automatically. Please wait while the business checks its bank records."
            return result
        return review("MISSING_FIELDS", "Required transaction fields are missing or ambiguous.")
    checks.append({"label": "Image extraction", "result": "Required fields read"})
    if slip["currency"] != order["currency"]:
        return reject("WRONG_CURRENCY", "The payment currency differs from the order currency.")
    if slip["account"] != order["account"]:
        return reject("WRONG_ACCOUNT", "The receiving account differs from the business account. Masked slips require review.")
    if slip["amount_minor"] != order["amount_minor"]:
        return reject("WRONG_AMOUNT", "The submitted amount does not equal the amount due, including cents.")
    checks.append({"label": "Order details", "result": "Amount, currency and receiving account match"})
    try:
        paid = instant(slip["paid_at"])
        created = instant(order["created_at"])
    except (ValueError, TypeError):
        return review("INVALID_DATE", "The payment date or its timezone is not reliable.")
    if paid < created - timedelta(minutes=5):
        return reject("OLD_PAYMENT", "This transaction predates the order beyond the clock-skew allowance.")
    if paid > now + timedelta(minutes=5):
        return review("FUTURE_DATE", "The payment timestamp is unexpectedly in the future.")
    if paid > instant(order["expires_at"]):
        return review("EXPIRED_ORDER", "The payment was made after the order payment window closed.")
    key = f"{order['account']}:{slip['reference']}"
    if key in claims:
        return reject("REUSED_TRANSACTION", "This bank transaction was already allocated to an order, possibly using a different image.")
    if order.get("paid"):
        return reject("ORDER_ALREADY_PAID", "This order already has an accepted payment.")
    # Matching amount is deliberately insufficient. Match a bank reference first.
    matching = [m for m in messages if m.get("reference") == slip["reference"]]
    if not matching:
        return review("NO_BANK_EVIDENCE", "No authenticated bank notification matches this transaction reference.")
    if any(m.get("conflict") for m in matching):
        return review("BANK_CONFLICT", "The same bank reference arrived with conflicting notification details.")
    if len(matching) != 1:
        return review("AMBIGUOUS_BANK_MATCH", "More than one bank record matches this reference.")
    sms = matching[0]
    if not sms.get("trusted"):
        return review("UNTRUSTED_BANK_EVIDENCE", "The notification was not received from an authenticated merchant device.")
    if any(sms.get(k) != slip[k] for k in ("amount_minor", "currency", "account")):
        return review("CONFLICTING_EVIDENCE", "Bank notification and slip disagree. A human must resolve the conflict.")
    try:
        if abs((instant(sms["paid_at"]) - paid).total_seconds()) > 300:
            return review("CONFLICTING_TIME", "The bank transaction time and slip time differ by more than five minutes.")
    except (ValueError, TypeError, KeyError):
        return review("MISSING_BANK_TIME", "The notification does not establish the transaction time.")
    if sms.get("order_code") != order["payment_code"]:
        return review("UNPROVEN_OWNERSHIP", "The bank evidence does not contain this order's unique payment code; amount and time alone do not establish ownership.")
    if slip.get("order_code") and slip["order_code"] != order["payment_code"]:
        return review("ORDER_CODE_CONFLICT", "The slip's payment code belongs to a different order.")
    checks.extend([{"label": "Bank evidence", "result": "Authenticated credit notification matches transaction"},
                   {"label": "Order attribution", "result": "Bank memo matches the server-issued order code"},
                   {"label": "Reuse protection", "result": "Transaction and order are unclaimed"}])
    return outcome("APPROVED", "CORROBORATED", "Slip, authenticated bank credit and unique order code agree; the transaction is unused.",
                   "Payment accepted. The order can proceed to fulfilment.",
                   "Thank you! Your payment has been verified and your order is confirmed.", sms["id"])
