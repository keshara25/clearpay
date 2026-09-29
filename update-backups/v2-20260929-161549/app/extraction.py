"""Conservative labelled-field parser plus local CPU OCR. Unknown formats fail closed."""
import io
import re
import threading
from decimal import Decimal, InvalidOperation
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 6 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 16_000_000
_engine = None
_lock = threading.Lock()

def money(value):
    if not re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?", value.strip()):
        raise ValueError("Invalid amount")
    amount = Decimal(value.replace(",", "")) * 100
    if amount <= 0 or amount > 100_000_000_00:
        raise ValueError("Amount out of range")
    return int(amount)

def parse_text(text):
    fields, issues = {}, []
    rules = {
        "amount_minor": r"(?:Amount|Credited)\s*[:=]?\s*(?:LKR|Rs\.?)\s*([\d,.]+)",
        "account": r"(?:Acc[o0]unt|A/C)\s*[:=]?\s*([0-9Xx*]{4,20})",
        "reference": r"(?:Reference|Ref)\s*[:=]?\s*([A-Za-z0-9-]{4,40})",
        "paid_at": r"(?:Date|Time)\s*[:=]?\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2}))",
        "order_code": r"(?:Memo|Payment code)\s*[:=]?\s*(PAY-[A-Z0-9]{6,20})",
    }
    for field, pattern in rules.items():
        matches = set(re.findall(pattern, text, re.I))
        if len(matches) > 1:
            issues.append(f"Conflicting values for {field}")
        elif matches:
            value = matches.pop()
            try:
                fields[field] = money(value) if field == "amount_minor" else value.upper() if field in ("reference", "order_code") else value
            except (ValueError, InvalidOperation):
                issues.append("Invalid money format")
    # OCR often removes the space in LKR25,000. The amount parser already
    # requires an explicit LKR/Rs prefix; do not demand a word boundary before digits.
    if fields.get("amount_minor") is not None:
        fields["currency"] = "LKR"
    if re.search(r"(?<![A-Z])(?:USD|EUR|GBP)(?![A-Z])", text, re.I):
        issues.append("Unsupported or conflicting currency")
    if fields.get("account") and not fields["account"].isdigit():
        issues.append("Masked account is not a full account match")
    fields["issues"] = issues
    return fields

def parse_sms(text):
    # Two explicitly supported adapters; we do not guess arbitrary bank formats.
    normalized = re.sub(r"Rs\.\s*([\d,.]+)\s+credited\s+to", r"Credited LKR \1 to", text, flags=re.I)
    fields = parse_text(normalized)
    if not re.search(r"\bcredited\b", text, re.I) or re.search(r"\b(debited|reversed|failed|pending)\b", text, re.I):
        fields["issues"].append("Not an unambiguous credit notification")
    return fields

def normalize_image(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("Image exceeds 6 MB")
    try:
        with Image.open(io.BytesIO(raw)) as src:
            if src.format not in ("PNG", "JPEG", "WEBP"):
                raise ValueError("Use PNG, JPEG or WebP")
            if src.width * src.height > 16_000_000:
                raise ValueError("Image exceeds 16 megapixels")
            src.load()
            image = ImageOps.exif_transpose(src).convert("RGB")
            if min(image.size) < 100:
                raise ValueError("Image is too small to read")
            image.thumbnail((2400, 2400))
            out = io.BytesIO()
            image.save(out, format="PNG")
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Invalid or oversized image") from exc

def extract(image_bytes):
    global _engine
    try:
        with _lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR
                _engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
            results, _ = _engine(image_bytes)
        if not results:
            return {"source": "ocr", "confidence": 0, "issues": ["No text detected"], "text": ""}
        text = "\n".join(line[1] for line in results)
        fields = parse_text(text)
        # Minimum over recognised lines is intentionally conservative.
        fields.update(source="ocr", confidence=round(min(float(line[2]) for line in results), 4), text=text)
        return fields
    except Exception as exc:
        # Engine failure must never turn into an approval. Avoid leaking server paths.
        return {"source": "unavailable", "confidence": 0, "issues": [f"OCR unavailable ({type(exc).__name__})"], "text": ""}
