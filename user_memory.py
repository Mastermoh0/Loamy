"""
user_memory.py
Durable facts Loamy learns about a user from their own words.

A fact is one short sentence ("plays soccer", "runs a shop selling sugar") taken
from a note the user wrote about a transaction. It is stored in the existing
`vector_embeddings` table under the `user_facts` collection, linked to the
transaction it came from, so no new table is needed.

Cost model:
- Writing a fact costs one embedding call, and only when the fact is new
  (the id is a hash of the normalised text, so repeats just overwrite).
- Reading costs NO Gemini call while the user has a small set of facts: they
  are all loaded and sent. Only past PROMPT_FACT_LIMIT does recall switch to a
  semantic search (one embedding call per chat turn).

Every read and write is scoped by user_id.
"""

import hashlib
import re
from datetime import datetime

import vector_store
from database import supabase

COLLECTION = "user_facts"
MAX_FACT_CHARS = 200
MAX_FACTS_PER_USER = 200
PROMPT_FACT_LIMIT = 25
SEMANTIC_RECALL_LIMIT = 8


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", str(text or "").lower()).strip()


def _fact_id(user_id: str, fact: str) -> str:
    digest = hashlib.sha1(f"{user_id}|{_normalize(fact)}".encode()).hexdigest()[:16]
    return f"fact_{digest}"


def _count(user_id: str) -> int:
    res = (supabase.table(vector_store.TABLE).select("doc_id", count="exact")
           .eq("user_id", user_id).eq("collection", COLLECTION).limit(1).execute())
    return int(res.count or 0)


def remember_fact(user_id: str, fact: str, source_tx_id: str = "", vendor: str = "",
                  note: str = "") -> bool:
    """Save one durable fact. Returns True when stored. Never raises."""
    fact = " ".join(str(fact or "").split())[:MAX_FACT_CHARS]
    if not user_id or len(_normalize(fact)) < 6:
        return False
    try:
        if _count(user_id) >= MAX_FACTS_PER_USER:
            print(f"[user_memory] fact cap reached for {user_id}")
            return False
        res = vector_store.add_vector(
            user_id,
            fact,
            metadata={
                "kind": "fact",
                "source_tx_id": source_tx_id or "",
                "vendor": vendor or "",
                "note": str(note or "")[:300],
                "created_at": datetime.now().isoformat(),
            },
            collection=COLLECTION,
            doc_id=_fact_id(user_id, fact),
        )
        return res["status"] == "success"
    except Exception as e:
        print(f"[user_memory] remember_fact failed: {e}")
        return False


def list_facts(user_id: str, limit: int = MAX_FACTS_PER_USER) -> list:
    """All of one user's facts, newest first: [{"id", "fact", "vendor", "source_tx_id", "created_at"}]."""
    if not user_id:
        return []
    try:
        res = (supabase.table(vector_store.TABLE).select("doc_id,content,metadata")
               .eq("user_id", user_id).eq("collection", COLLECTION).limit(limit).execute())
    except Exception as e:
        print(f"[user_memory] list_facts failed: {e}")
        return []
    facts = []
    for row in res.data or []:
        meta = row.get("metadata") or {}
        facts.append({
            "id": row["doc_id"],
            "fact": row.get("content") or "",
            "vendor": meta.get("vendor") or "",
            "source_tx_id": meta.get("source_tx_id") or "",
            "created_at": meta.get("created_at") or "",
        })
    facts.sort(key=lambda f: f["created_at"], reverse=True)
    return facts


def delete_fact(user_id: str, fact_id: str) -> bool:
    """Delete one fact. The user_id filter means nobody can delete another user's memory."""
    if not user_id or not fact_id:
        return False
    try:
        (supabase.table(vector_store.TABLE).delete()
         .eq("user_id", user_id).eq("collection", COLLECTION).eq("doc_id", fact_id).execute())
        return True
    except Exception as e:
        print(f"[user_memory] delete_fact failed: {e}")
        return False


def facts_for_prompt(user_id: str, query: str = "") -> str:
    """A prompt-ready block of what Loamy knows about this user, or "" when nothing."""
    if not user_id or user_id == "default_user":
        return ""
    facts = list_facts(user_id)
    if not facts:
        return ""
    if len(facts) > PROMPT_FACT_LIMIT and query.strip():
        hits = vector_store.search_vectors(
            user_id, query, limit=SEMANTIC_RECALL_LIMIT, collection=COLLECTION)
        chosen = [h["content"] for h in hits if h.get("content")]
        if not chosen:
            chosen = [f["fact"] for f in facts[:PROMPT_FACT_LIMIT]]
    else:
        chosen = [f["fact"] for f in facts[:PROMPT_FACT_LIMIT]]
    lines = "\n".join(f"  - {c}" for c in chosen)
    return (
        "WHAT YOU KNOW ABOUT THIS USER (learned from their own notes; use it to personalise "
        "answers and suggestions, treat it as likely but not certain, and never recite it unprompted):\n"
        f"{lines}"
    )
