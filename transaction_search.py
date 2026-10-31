"""
transaction_search.py
The chat's `find_transactions` lookup tool.

The chat prompt only carries the most recent ledger lines. This module lets the
model search the user's FULL history (ledger rows and bank alerts) by amount,
date, text, category or channel, and get back complete records, including the
original currency, the channel and what the user said about each one.

Every read is scoped by user_id. Matching is deterministic code, so the model
never has to guess which transaction "it" refers to.
"""

import database

MAX_RESULTS = 10
DEFAULT_TOLERANCE_PCT = 5.0

FIND_TRANSACTIONS_TOOL = {
    "function_declarations": [{
        "name": "find_transactions",
        "description": (
            "Search the user's full transaction history (cash logs, receipts and bank alerts) and "
            "return complete records: amount in naira, original amount and currency, date, category, "
            "the channel it was logged through (WhatsApp, web chat, bank email) and what the user said "
            "about it. Use this whenever the user refers to a specific payment, an amount, a date, a "
            "vendor or 'that one', or when the recent transactions already in your context do not "
            "contain it. All arguments are optional filters that are combined."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Approximate amount. Matches either the naira amount or the original "
                                   "currency amount (e.g. 200 matches '200 MUR' as well as N200).",
                },
                "amount_tolerance_pct": {
                    "type": "number",
                    "description": "How far an amount may differ, in percent. Default 5. Use 0 for exact.",
                },
                "min_amount": {"type": "number", "description": "Smallest naira amount."},
                "max_amount": {"type": "number", "description": "Largest naira amount."},
                "date_from": {"type": "string", "description": "Earliest date, YYYY-MM-DD."},
                "date_to": {"type": "string", "description": "Latest date, YYYY-MM-DD."},
                "text": {
                    "type": "string",
                    "description": "Words to look for in the vendor, category, narration or the user's own words.",
                },
                "category": {"type": "string", "description": "Category name, partial match allowed."},
                "transaction_type": {"type": "string", "enum": ["expense", "income"]},
                "channel": {
                    "type": "string",
                    "enum": ["whatsapp", "web_chat", "receipt_upload", "bank_email"],
                    "description": "Where the transaction was logged from.",
                },
                "limit": {"type": "integer", "description": "Maximum results, up to 10."},
            },
        },
    }]
}


def _num(value):
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _record(t: dict) -> dict:
    """The fields the model needs, with empty ones dropped to save tokens."""
    original = t.get("original_amount")
    currency = t.get("original_currency") or "NGN"
    record = {
        "id": t.get("id"),
        "date": str(t.get("date") or "")[:10],
        "vendor": t.get("vendor"),
        "amount_naira": t.get("amount"),
        "type": t.get("type"),
        "category": t.get("category"),
        "channel": t.get("channel_label") or database.LEGACY_CHANNEL_LABEL,
        "logged_at": str(t.get("logged_at") or "")[:16].replace("T", " ") or None,
        "user_words": t.get("user_words"),
    }
    if currency != "NGN" and original:
        record["original_amount"] = original
        record["original_currency"] = currency
        record["fx_rate"] = t.get("fx_rate")
    return {k: v for k, v in record.items() if v not in (None, "")}


def _amount_matches(t: dict, target: float, tolerance_pct: float) -> bool:
    slack = abs(target) * tolerance_pct / 100.0
    candidates = [_num(t.get("amount")), _num(t.get("original_amount"))]
    return any(c is not None and abs(c - target) <= max(slack, 0.005) for c in candidates)


def _in_range(t: dict, start, end) -> bool:
    if not start and not end:
        return True
    day = database._to_date_obj(t.get("date"))
    if not day:
        return False
    return (not start or day >= start) and (not end or day <= end)


def _text_matches(t: dict, words: list) -> bool:
    haystack = " ".join(str(t.get(k) or "") for k in ("vendor", "category", "user_words", "description")).lower()
    return all(w in haystack for w in words)


def _load_all(user_id: str) -> list:
    """Ledger rows plus bank alerts, newest first, in the chat's record shape."""
    ledger = []
    res = database.get_transactions(user_id, limit=1000)
    if res["status"] == "success":
        for r in res["data"]:
            income = (r.get("transaction_type") or "").lower() in ("in", "income", "credit", "deposit")
            ledger.append({
                "date": r.get("date") or r.get("occurred_on"),
                "vendor": r.get("vendor") or r.get("description") or "Unknown",
                "description": r.get("description"),
                "amount": database._to_money(r.get("amount")),
                "category": r.get("category") or "other",
                "type": "income" if income else "expense",
                **database.transaction_details(r),
            })
    alerts = []
    g = database.get_gmail_financial_context(user_id, limit=1000)
    if g["status"] == "success" and g["data"]:
        alerts = g["data"].get("recent_transactions") or []
    merged = ledger + alerts
    merged.sort(key=lambda t: str(t.get("date") or ""), reverse=True)
    return merged


def find_transactions(user_id: str, amount=None, amount_tolerance_pct=None, min_amount=None,
                      max_amount=None, date_from=None, date_to=None, text=None, category=None,
                      transaction_type=None, channel=None, limit=None) -> dict:
    """Search one user's history. Returns {"total_matches", "returned", "transactions"}."""
    if not user_id or user_id == "default_user":
        return {"total_matches": 0, "returned": 0, "transactions": [], "error": "unknown user"}

    target = _num(amount)
    tolerance = _num(amount_tolerance_pct)
    tolerance = DEFAULT_TOLERANCE_PCT if tolerance is None else max(0.0, tolerance)
    low, high = _num(min_amount), _num(max_amount)
    start, end = database._to_date_obj(date_from), database._to_date_obj(date_to)
    words = [w for w in str(text or "").lower().split() if w]
    wanted_category = str(category or "").strip().lower()
    wanted_type = str(transaction_type or "").strip().lower()
    wanted_channel = str(channel or "").strip().lower()
    cap = max(1, min(int(_num(limit) or MAX_RESULTS), MAX_RESULTS))

    matches = []
    for t in _load_all(user_id):
        if target is not None and not _amount_matches(t, target, tolerance):
            continue
        naira = _num(t.get("amount")) or 0.0
        if (low is not None and naira < low) or (high is not None and naira > high):
            continue
        if not _in_range(t, start, end):
            continue
        if words and not _text_matches(t, words):
            continue
        if wanted_category and wanted_category not in str(t.get("category") or "").lower():
            continue
        if wanted_type and t.get("type") != wanted_type:
            continue
        if wanted_channel and t.get("channel") != wanted_channel:
            continue
        matches.append(t)

    return {
        "total_matches": len(matches),
        "returned": min(len(matches), cap),
        "transactions": [_record(t) for t in matches[:cap]],
    }
