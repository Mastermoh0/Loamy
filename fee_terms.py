"""Single definition of "this narration is a bank fee/charge".

The Review Queue scan, the dashboard and Bank Accounts all skip pure bank fees.
They used to do that with plain substring checks, so short keywords matched
inside unrelated words ("SALVATION" contains "vat", "COFFEE" contains "fee",
"COTTON" contains "cot") and real transfers silently never reached the queue.
Short keywords now have to be whole words; long, unambiguous ones can match
as substrings (so "CHARGES" and "SMSCHARGE" still count).
"""
import re

_FEE_PATTERN = re.compile(
    r"charge|chrg|stamp duty|commission|maintenance"
    r"|\b(?:fees?|vat|levy|levies|cot)\b"
)


def is_bank_fee(narration) -> bool:
    return bool(_FEE_PATTERN.search((narration or "").lower()))
