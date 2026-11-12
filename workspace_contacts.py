"""Immutable order contact choices, separate from authentication or bank identity."""
import json
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal


def email_address(value):
    if value and (value.count('@') != 1 or any(c.isspace() or c in ',;<>:"()\\' for c in value) or '.' not in value.split('@')[1]):
        raise ValueError('Enter one complete email address')
    return value


class ContactInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    customer_email: str = Field(default='', max_length=254)
    additional_emails: list[str] = Field(default_factory=list, max_length=3)
    customer_whatsapp: str = Field(default='', max_length=16, pattern=r'^(|\+[1-9][0-9]{7,14})$')
    preferred_channel: Literal['none', 'email', 'whatsapp'] = 'none'
    whatsapp_consent: bool = False

    @field_validator('customer_email')
    @classmethod
    def email(cls, value):
        return email_address(value)

    @field_validator('additional_emails')
    @classmethod
    def others(cls, values):
        for value in values:
            if not value or len(value) > 254 or value != value.strip():
                raise ValueError('Enter complete additional email addresses')
            email_address(value)
        if len({v.casefold() for v in values}) != len(values):
            raise ValueError('Use distinct email addresses')
        return values

    @model_validator(mode='after')
    def choice(self):
        if self.additional_emails and (not self.customer_email or self.customer_email.casefold() in {v.casefold() for v in self.additional_emails}):
            raise ValueError('Additional emails need a distinct primary email')
        if self.preferred_channel == 'email' and not self.customer_email:
            raise ValueError('Email preference needs a primary email')
        if self.preferred_channel == 'whatsapp' and (not self.customer_whatsapp or not self.whatsapp_consent):
            raise ValueError('WhatsApp preference needs a country-code number and recorded customer permission')
        return self


CONTACT_FIELDS = set(ContactInput.model_fields)


def install_contacts(db):
    with db() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS order_contacts (
          order_id TEXT PRIMARY KEY REFERENCES orders(id), customer_email TEXT NOT NULL,
          additional_emails TEXT NOT NULL, customer_whatsapp TEXT NOT NULL,
          preferred_channel TEXT NOT NULL CHECK(preferred_channel IN ('none','email','whatsapp')),
          whatsapp_consent INTEGER NOT NULL CHECK(whatsapp_consent IN (0,1))
        );''')


def save_contacts(conn, oid, data):
    conn.execute('INSERT INTO order_contacts VALUES (?,?,?,?,?,?)', (oid, data.customer_email, json.dumps(data.additional_emails), data.customer_whatsapp, data.preferred_channel, int(data.whatsapp_consent)))


def contacts_for(conn, oid, legacy=''):
    row = conn.execute('SELECT * FROM order_contacts WHERE order_id=?', (oid,)).fetchone()
    if row:
        return {'customer_email': row['customer_email'] or (legacy if '@' in legacy else ''), 'additional_emails': json.loads(row['additional_emails']),
                'customer_whatsapp': row['customer_whatsapp'], 'preferred_channel': row['preferred_channel'], 'whatsapp_consent': bool(row['whatsapp_consent'])}
    return {'customer_email': legacy if '@' in legacy else '', 'additional_emails': [], 'customer_whatsapp': '', 'preferred_channel': 'none', 'whatsapp_consent': False}
