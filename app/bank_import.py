"""Strict merchant-imported credit records. Import provenance is not bank authentication."""
import csv
import io
import re
from datetime import datetime, timezone
from .extraction import money

COLUMNS = ('account', 'reference', 'amount', 'currency', 'paid_at', 'direction', 'status', 'order_code')


def parse_statement(raw, account):
    if len(raw) > 1024 * 1024:
        raise ValueError('Bank CSV must be smaller than 1 MB')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('Save the bank records as UTF-8 CSV')
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != list(COLUMNS):
        raise ValueError('Use the CSV template columns in the supplied order')
    records, skipped = [], 0
    for number, row in enumerate(reader, 2):
        if number > 5001:
            raise ValueError('Import at most 5,000 rows at a time')
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f'Row {number}: missing or extra columns')
        row = {key: value.strip() for key, value in row.items()}
        if row['direction'].upper() == 'DEBIT' or row['status'].upper() in ('PENDING', 'FAILED', 'REVERSED'):
            skipped += 1
            continue
        try:
            if row['direction'].upper() != 'CREDIT' or row['status'].upper() != 'COMPLETED':
                raise ValueError('direction must be CREDIT and status COMPLETED')
            if row['account'] != account or not row['account'].isascii() or not row['account'].isdigit():
                raise ValueError('receiving account must match the configured merchant account')
            if row['currency'].upper() != 'LKR':
                raise ValueError('only LKR credits are supported')
            if not re.fullmatch(r'[A-Za-z0-9-]{4,40}', row['reference']):
                raise ValueError('invalid transaction reference')
            paid = datetime.fromisoformat(row['paid_at'].replace('Z', '+00:00'))
            if paid.tzinfo is None:
                raise ValueError('paid_at requires a timezone, e.g. +05:30')
            code = row['order_code'].upper()
            if code and not re.fullmatch(r'PAY-[A-Z0-9]{6,20}', code):
                raise ValueError('invalid order code; leave empty if absent from bank memo')
            records.append(dict(account=account, reference=row['reference'].upper(),
                                amount_minor=money(row['amount']), currency='LKR',
                                paid_at=paid.astimezone(timezone.utc).isoformat(timespec='seconds'),
                                order_code=code or None, trusted=True, issues=[], evidence_source='merchant_statement'))
        except ValueError as exc:
            raise ValueError(f'Row {number}: {exc}') from exc
    if not records:
        raise ValueError('No completed credits to import')
    return records, skipped
