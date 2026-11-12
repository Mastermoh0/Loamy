"""Bounded .eml attachment review; headers are unverified, never instructions."""
import base64
import binascii
import hashlib
from email import policy
from email.parser import BytesParser
from fastapi import HTTPException
from workspace_expenses import receipt_bytes


def email_attachments(encoded):
    try:
        raw=base64.b64decode(encoded,validate=True)
        if not raw or len(raw)>2*1024*1024: raise ValueError()
        message=BytesParser(policy=policy.default).parsebytes(raw)
        parts=list(message.walk())
        if len(parts)>40: raise ValueError()
        attachments=[]
        for index,part in enumerate(parts):
            if part.get_content_type() not in {'application/pdf','image/jpeg','image/png'}: continue
            content=part.get_payload(decode=True)
            if not content: continue
            b64=base64.b64encode(content).decode()
            validated,mime,extension=receipt_bytes(b64)
            attachments.append({'index':index,'filename':str(part.get_filename() or f'attachment.{extension}')[:160],
                                'receipt_base64':base64.b64encode(validated).decode(),'mime':mime,'sha256':hashlib.sha256(validated).hexdigest()})
        if not 1<=len(attachments)<=5: raise ValueError()
        return {'email_sha256':hashlib.sha256(raw).hexdigest(),'sender':str(message.get('From',''))[:254],
                'subject':str(message.get('Subject',''))[:240],'attachments':attachments,'warning':'Email headers are unverified. Review the supplier, attachment and amount before importing. No mailbox was connected.'}
    except (ValueError,TypeError,binascii.Error,RecursionError,HTTPException):
        raise HTTPException(422,'Use a valid .eml email up to 2 MB with 1–5 supported PDF/JPEG/PNG attachments')


def install_supplier_email(db):
    with db() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS supplier_email_evidence (
          bill_id TEXT PRIMARY KEY REFERENCES supplier_bills(id), email_sha256 TEXT NOT NULL,
          sender TEXT NOT NULL, subject TEXT NOT NULL, attachment_sha256 TEXT NOT NULL
        );''')
