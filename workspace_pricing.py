"""Exact order-level discounts followed by exclusive tax; immutable saved breakdowns."""
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from workspace_finances import money


class PricingInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    tax_label: str = Field(default='Tax', min_length=2, max_length=60)
    tax_rate: Decimal = Field(default=Decimal('0'), ge=0, le=100, max_digits=5, decimal_places=2)


def location_pricing(conn, lid):
    row = conn.execute('SELECT tax_label,tax_rate_bps FROM location_pricing WHERE location_id=?', (lid,)).fetchone()
    return {'tax_label': row['tax_label'], 'tax_rate': money(row['tax_rate_bps'])} if row else {'tax_label': 'Tax', 'tax_rate': '0.00'}


def calculate(subtotal, kind, value, rate_bps):
    if kind == 'none' and value != 0:
        raise HTTPException(422, 'Choose a discount type for this value')
    if kind == 'percent' and value > 100:
        raise HTTPException(422, 'Percentage discounts cannot exceed 100')
    discount = int((Decimal(subtotal) * value / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if kind == 'percent' else int(value * 100) if kind == 'fixed' else 0
    if discount >= subtotal:
        raise HTTPException(422, 'The discount must leave a positive order amount')
    taxable = subtotal - discount
    tax = int((Decimal(taxable) * rate_bps / 10000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return discount, tax, taxable + tax


def order_pricing(conn, oid, total):
    row = conn.execute('SELECT * FROM order_pricing WHERE order_id=?', (oid,)).fetchone()
    if not row:
        return {'subtotal': money(total), 'discount': '0.00', 'discount_type': 'none', 'discount_value': '0.00', 'discount_reason': '', 'tax_label': 'Tax', 'tax_rate': '0.00', 'tax': '0.00'}
    return {'subtotal': money(row['subtotal_minor']), 'discount': money(row['discount_minor']), 'discount_type': row['discount_type'],
            'discount_value': money(row['discount_value_hundredths']), 'discount_reason': row['discount_reason'],
            'tax_label': row['tax_label'], 'tax_rate': money(row['tax_rate_bps']), 'tax': money(row['tax_minor'])}


def install_pricing(db):
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS location_pricing (
            location_id TEXT PRIMARY KEY REFERENCES locations(id), tax_label TEXT NOT NULL,
            tax_rate_bps INTEGER NOT NULL CHECK(tax_rate_bps BETWEEN 0 AND 10000)
          );
          CREATE TABLE IF NOT EXISTS order_pricing (
            order_id TEXT PRIMARY KEY REFERENCES orders(id), subtotal_minor INTEGER NOT NULL CHECK(subtotal_minor>0),
            discount_type TEXT NOT NULL CHECK(discount_type IN ('none','fixed','percent')),
            discount_value_hundredths INTEGER NOT NULL CHECK(discount_value_hundredths>=0),
            discount_minor INTEGER NOT NULL CHECK(discount_minor>=0 AND discount_minor<subtotal_minor),
            discount_reason TEXT NOT NULL, tax_label TEXT NOT NULL,
            tax_rate_bps INTEGER NOT NULL CHECK(tax_rate_bps BETWEEN 0 AND 10000),
            tax_minor INTEGER NOT NULL CHECK(tax_minor>=0)
          );
        ''')
