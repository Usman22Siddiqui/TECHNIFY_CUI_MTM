"""Pick latest price, check sender authority, drop noise.

Without it: old price used; a caterer could change the headcount.

Pure functions: dicts in, dicts out. Configs are loaded via helpers or passed in.
"""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any


CONFIG_DIR = pathlib.Path(__file__).resolve().parent.parent / "config"

# Role names in Urdu for bilingual templated rejections
_ROLE_UR: dict[str, str] = {
    "authority": "انتظامیہ",
    "finance": "فنانس",
    "venue": "مقام منتظم",
    "caterer": "کیٹرر",
    "judging": "ججنگ کوآرڈینیٹر",
    "requester": "درخواست گزار",
    "participant": "شرکت کنندہ",
    "unknown": "نامعلوم",
}

# Bilingual rejection reason templates (code-generated, never model-written)
_REASON_TEMPLATES: dict[str, tuple[str, str]] = {
    "UNGROUNDED": (
        "Extracted value not found in source message",
        "نکالی گئی رقم اصل پیغام میں موجود نہیں",
    ),
    "NO_AUTHORITY": (
        "Sender role is not authorised to change '{key}'",
        "بھیجنے والے کو '{key}' تبدیل کرنے کا اختیار نہیں",
    ),
    "BREAKS_CHECK": (
        "Candidate plan failed check '{check}': {detail}",
        "مجوزہ منصوبہ '{check}' جانچ میں ناکام ہوا: {detail}",
    ),
    "OUT_OF_DATE": (
        "Superseded by newer message #{newer_id} for '{key}'",
        "'{key}' کے لیے نیا پیغام #{newer_id} پہلے سے موجود ہے",
    ),
    "CONTRADICTS_AUTHORITY": (
        "Conflicts with higher-authority fact for '{key}'",
        "'{key}' کے لیے اعلیٰ اختیار والے فیصلے سے متصادم ہے",
    ),
    "UNIT_ANOMALY": (
        "Value {value} for '{key}' is orders of magnitude off expected range (existing: {existing})",
        "'{key}' کی رقم {value} متوقع حد سے غیر معمولی طور پر مختلف ہے (موجودہ: {existing})",
    ),
    "REQUEST_ONLY": (
        "Message is a request, placed in wishlist rather than spending",
        "یہ پیغام صرف درخواست ہے، خرچ کے بجائے خواہشات میں شامل کیا گیا",
    ),
    "NOT_RELEVANT": (
        "Message does not affect any planning area",
        "یہ پیغام منصوبے کے کسی شعبے پر اثر انداز نہیں ہوتا",
    ),
}


def load_authority_config(path: pathlib.Path | None = None) -> dict[str, Any]:
    """Load role -> allowed keys mapping from config/authority.json."""
    target = path or (CONFIG_DIR / "authority.json")
    with open(target, "r", encoding="utf-8") as f:
        return json.load(f)


def format_rejection(
    message_id: int,
    role: str,
    code: str,
    **kwargs: Any,
) -> tuple[str, str]:
    """Build templated bilingual rejection reason (English, Urdu).

    Format matches UPDATE_ENGINE.md:
    REJECTED msg #<id> (<role>): <code>. <rule that failed>. Plan unchanged.
    """
    tmpl_en, tmpl_ur = _REASON_TEMPLATES.get(
        code,
        ("Rule check failed", "قاعدے کی خلاف ورزی"),
    )
    detail_en = tmpl_en.format(**kwargs) if kwargs else tmpl_en
    detail_ur = tmpl_ur.format(**kwargs) if kwargs else tmpl_ur
    role_ur = _ROLE_UR.get(role, role)

    reason_en = f"REJECTED msg #{message_id} ({role}): {code}. {detail_en}. Plan unchanged."
    reason_ur = f"مسترد پیغام #{message_id} ({role_ur}): {code}۔ {detail_ur}۔ منصوبہ برقرار ہے"
    return reason_en, reason_ur


def _split_structured_key(fact: dict[str, Any]) -> tuple[str, str | None, str]:
    """Normalise fact key into (base_key, subfield_or_None, ref).

    Handles:
      - key='venue_option.capacity' -> ('venue_option', 'capacity', ref)
      - key='venue_option' with u='count' -> ('venue_option', 'capacity', ref)
      - key='venue_option' with u='PKR' -> ('venue_option', 'price', ref)
      - key='venue_option' with u='bool' -> ('venue_option', 'generator', ref)
      - key='food_option.price_per_head' -> ('food_option', 'price_per_head', ref)
      - key='food_option' with u='PKR' -> ('food_option', 'delivery_fee' if delivery else 'price_per_head', ref)
      - key='students' -> ('students', None, '')
    """
    raw_key = str(fact.get("key", "")).strip()
    ref = str(fact.get("ref", "") or "").strip()
    unit = str(fact.get("u", "") or "").strip()
    quote = str(fact.get("q", "") or "").lower()

    # Dot or colon notation: venue_option.capacity, food_option:delivery_fee
    for sep in (".", ":"):
        if sep in raw_key:
            base, sub = raw_key.split(sep, 1)
            return base.strip(), sub.strip(), ref

    # Underscore variants for structured items
    for prefix in ("venue_option_", "food_option_"):
        if raw_key.startswith(prefix):
            return prefix[:-1], raw_key[len(prefix):], ref

    # Infer subfield for bare venue_option / food_option
    if raw_key == "venue_option":
        if unit == "count":
            return "venue_option", "capacity", ref
        if unit == "PKR":
            return "venue_option", "price", ref
        if unit == "bool":
            if "access" in quote or "wheelchair" in quote or "ramp" in quote:
                return "venue_option", "accessible", ref
            return "venue_option", "generator", ref
        return "venue_option", None, ref

    if raw_key == "food_option":
        if unit == "PKR":
            if "deliver" in quote:
                return "food_option", "delivery_fee", ref
            return "food_option", "price_per_head", ref
        if unit == "bool":
            if "veg" in quote:
                return "food_option", "vegetarian_available", ref
            return "food_option", "halal", ref
        return "food_option", None, ref

    return raw_key, None, ref


def _date_sort_key(date_str: str | None, msg_id: int) -> tuple[int, str, int]:
    """Compare recency: explicit date beats None; latest date wins; tie -> later msg_id."""
    has_date = 1 if date_str else 0
    return (has_date, date_str or "", msg_id)


def _is_newer_or_equal(
    new_date: str | None,
    new_id: int,
    old_date: str | None,
    old_id: int,
) -> bool:
    """Return True if incoming (new_date, new_id) supersedes (old_date, old_id)."""
    # If both have dates, compare dates first, then id
    if new_date and old_date:
        if new_date != old_date:
            return new_date > old_date
        return new_id >= old_id
    # If incoming has a date and existing does not, incoming wins
    if new_date and not old_date:
        return True
    # If existing has a date and incoming does not:
    # if incoming msg_id is strictly newer (e.g. undated follow-up message), treat as newer
    # unless explicitly dated earlier.
    if not new_date and old_date:
        return new_id > old_id
    # Neither dated: later message id wins
    return new_id >= old_id


def _is_unit_anomaly(
    new_val: Any,
    old_val: Any,
    unit: str,
    factor: int,
) -> bool:
    """Flag orders-of-magnitude rupee mix-ups (F14)."""
    if unit != "PKR":
        return False
    if isinstance(new_val, bool) or isinstance(old_val, bool):
        return False
    if not isinstance(new_val, (int, float)) or not isinstance(old_val, (int, float)):
        return False
    if new_val <= 0 or old_val <= 0:
        return False
    ratio = max(new_val, old_val) / min(new_val, old_val)
    return ratio >= factor


def _constraint_area_role_allowed(role: str, area: str) -> bool:
    """Check if a role may add constraints to a given area."""
    if role == "authority":
        return True
    allowed_by_area = {
        "venue": {"authority", "venue", "finance"},
        "food": {"authority", "caterer", "finance"},
        "schedule": {"authority", "judging", "venue"},
        "judging": {"authority", "judging"},
        "budget": {"authority", "finance"},
    }
    return role in allowed_by_area.get(area, {"authority"})


def resolve_facts(
    extracted_messages: list[dict[str, Any]],
    authority_config: dict[str, Any] | None = None,
    existing_state: dict[str, Any] | None = None,
    unit_anomaly_factor: int = 50,
) -> dict[str, Any]:
    """Resolve extracted messages into canonical facts, constraints, and events.

    Pure function: takes dicts, returns a new resolved dict without mutating inputs.

    Returns dict with:
        facts: canonical fact store (scalars + venue_options + food_options + committed_costs + wishlist)
        fact_meta: per-slot provenance (date, source_id, role, quote, unit, value)
        constraints: list of resolved constraint dicts
        superseded: list of {old_id, new_id, key}
        rejected: list of {message_id, role, code, reason_en, reason_ur, key}
        ignored: list of {message_id, role, code, reason_en, reason_ur}
        message_statuses: dict[msg_id -> {status, reason_code, reason_en, reason_ur}]
    """
    cfg = authority_config if authority_config is not None else load_authority_config()
    allowed_keys: dict[str, list[str]] = cfg.get("authority", {}).get("allowed_keys", {})

    # Start from copies of existing state if provided
    base = existing_state or {}
    fact_meta: dict[str, dict[str, Any]] = copy.deepcopy(base.get("fact_meta", {}))
    constraints: list[dict[str, Any]] = copy.deepcopy(base.get("constraints", []))
    wishlist: dict[str, dict[str, Any]] = copy.deepcopy(base.get("facts", {}).get("wishlist", {}))

    superseded: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    message_statuses: dict[int, dict[str, str]] = {}

    for msg in extracted_messages:
        msg_id = int(msg.get("i", 0))
        role = str(msg.get("r", "unknown") or "unknown")
        date_str = msg.get("d")
        kind = str(msg.get("k", "fact") or "fact")
        facts_in = msg.get("f", []) or []
        constraints_in = msg.get("c", []) or []

        # 1. Relevance filter: noise
        if kind == "noise":
            r_en, r_ur = format_rejection(msg_id, role, "NOT_RELEVANT")
            ignored.append({
                "message_id": msg_id,
                "role": role,
                "code": "NOT_RELEVANT",
                "reason_en": r_en,
                "reason_ur": r_ur,
            })
            message_statuses[msg_id] = {
                "status": "ignored",
                "reason_code": "NOT_RELEVANT",
                "reason_en": r_en,
                "reason_ur": r_ur,
            }
            continue

        # 2. Relevance filter: request -> wishlist only, never enters spending
        if kind == "request":
            r_en, r_ur = format_rejection(msg_id, role, "REQUEST_ONLY")
            for f_item in facts_in:
                label = str(f_item.get("ref") or f_item.get("key") or f"request_{msg_id}").strip()
                val = f_item.get("v")
                cost = int(round(val)) if isinstance(val, (int, float)) and not isinstance(val, bool) else 0
                wishlist[label] = {
                    "label": label,
                    "cost": cost,
                    "source_id": msg_id,
                    "quote": f_item.get("q", ""),
                }
            ignored.append({
                "message_id": msg_id,
                "role": role,
                "code": "REQUEST_ONLY",
                "reason_en": r_en,
                "reason_ur": r_ur,
            })
            message_statuses[msg_id] = {
                "status": "ignored",
                "reason_code": "REQUEST_ONLY",
                "reason_en": r_en,
                "reason_ur": r_ur,
            }
            continue

        msg_accepted_any = False
        msg_reject_record: dict[str, Any] | None = None

        # Expand dict-valued structured facts if a model returns nested objects
        expanded_facts: list[dict[str, Any]] = []
        for f_item in facts_in:
            if isinstance(f_item.get("v"), dict):
                base_k = f_item.get("key", "")
                for sub_k, sub_v in f_item["v"].items():
                    expanded_facts.append({
                        "key": f"{base_k}.{sub_k}",
                        "v": sub_v,
                        "u": f_item.get("u", "text"),
                        "q": f_item.get("q", ""),
                        "ref": f_item.get("ref", ""),
                    })
            else:
                expanded_facts.append(f_item)

        # 3. Process facts
        for f_item in expanded_facts:
            base_key, subfield, ref = _split_structured_key(f_item)
            val = f_item.get("v")
            unit = str(f_item.get("u", "text") or "text")
            quote = str(f_item.get("q", "") or "")

            # Wishlist item inside a fact/notice message still goes to wishlist
            if base_key == "wishlist_item":
                label = ref or f"item_{msg_id}"
                cost = int(round(val)) if isinstance(val, (int, float)) and not isinstance(val, bool) else 0
                wishlist[label] = {
                    "label": label,
                    "cost": cost,
                    "source_id": msg_id,
                    "quote": quote,
                }
                msg_accepted_any = True
                continue

            # Determine canonical slot id for supersession & provenance
            if subfield:
                slot = f"{base_key}::{ref}::{subfield}"
            elif ref:
                slot = f"{base_key}::{ref}"
            else:
                slot = base_key

            # Authority check
            allowed_roles = allowed_keys.get(base_key)
            existing = fact_meta.get(slot)

            if allowed_roles is not None and role not in allowed_roles:
                # Distinguish contradicting an existing authority fact vs general NO_AUTHORITY
                if (
                    existing is not None
                    and existing.get("role") == "authority"
                    and existing.get("value") != val
                ):
                    code = "CONTRADICTS_AUTHORITY"
                else:
                    code = "NO_AUTHORITY"
                r_en, r_ur = format_rejection(msg_id, role, code, key=base_key)
                rec = {
                    "message_id": msg_id,
                    "role": role,
                    "code": code,
                    "key": base_key,
                    "reason_en": r_en,
                    "reason_ur": r_ur,
                }
                rejected.append(rec)
                msg_reject_record = msg_reject_record or rec
                continue

            # Unit anomaly guard (F14) against existing value for the same slot
            if existing is not None and _is_unit_anomaly(
                val, existing.get("value"), unit, unit_anomaly_factor
            ):
                r_en, r_ur = format_rejection(
                    msg_id,
                    role,
                    "UNIT_ANOMALY",
                    key=slot,
                    value=val,
                    existing=existing.get("value"),
                )
                rec = {
                    "message_id": msg_id,
                    "role": role,
                    "code": "UNIT_ANOMALY",
                    "key": slot,
                    "reason_en": r_en,
                    "reason_ur": r_ur,
                }
                rejected.append(rec)
                msg_reject_record = msg_reject_record or rec
                continue

            # Supersession check
            if existing is not None:
                if _is_newer_or_equal(
                    date_str, msg_id, existing.get("date"), existing.get("source_id", 0)
                ):
                    old_id = existing.get("source_id", 0)
                    if old_id != msg_id:
                        superseded.append({
                            "old_id": old_id,
                            "new_id": msg_id,
                            "key": slot,
                        })
                    fact_meta[slot] = {
                        "base_key": base_key,
                        "subfield": subfield,
                        "ref": ref,
                        "value": val,
                        "unit": unit,
                        "date": date_str,
                        "source_id": msg_id,
                        "role": role,
                        "quote": quote,
                    }
                    msg_accepted_any = True
                else:
                    r_en, r_ur = format_rejection(
                        msg_id,
                        role,
                        "OUT_OF_DATE",
                        key=slot,
                        newer_id=existing.get("source_id", 0),
                    )
                    rec = {
                        "message_id": msg_id,
                        "role": role,
                        "code": "OUT_OF_DATE",
                        "key": slot,
                        "reason_en": r_en,
                        "reason_ur": r_ur,
                    }
                    rejected.append(rec)
                    msg_reject_record = msg_reject_record or rec
            else:
                fact_meta[slot] = {
                    "base_key": base_key,
                    "subfield": subfield,
                    "ref": ref,
                    "value": val,
                    "unit": unit,
                    "date": date_str,
                    "source_id": msg_id,
                    "role": role,
                    "quote": quote,
                }
                msg_accepted_any = True

        # 4. Process constraints
        for c_item in constraints_in:
            area = str(c_item.get("a", "") or "").strip()
            subject = str(c_item.get("s", "") or "").strip()
            op = str(c_item.get("op", "") or "").strip()
            c_val = c_item.get("v")
            hard = bool(c_item.get("hard", True))
            q = str(c_item.get("q", "") or "")

            # Normalise subject to include area prefix if omitted (e.g. "generator" -> "venue.generator")
            full_subject = subject if "." in subject else (f"{area}.{subject}" if area else subject)

            if not _constraint_area_role_allowed(role, area):
                r_en, r_ur = format_rejection(msg_id, role, "NO_AUTHORITY", key=full_subject)
                rec = {
                    "message_id": msg_id,
                    "role": role,
                    "code": "NO_AUTHORITY",
                    "key": full_subject,
                    "reason_en": r_en,
                    "reason_ur": r_ur,
                }
                rejected.append(rec)
                msg_reject_record = msg_reject_record or rec
                continue

            # Replace existing constraint with same (area, subject, op) if newer
            constraints = [
                c for c in constraints
                if not (c["area"] == area and c["subject"] == full_subject and c["op"] == op)
            ]
            constraints.append({
                "area": area,
                "subject": full_subject,
                "op": op,
                "value": c_val,
                "hard": hard,
                "source_id": msg_id,
                "quote": q,
            })
            msg_accepted_any = True

        # Record overall message status
        if msg_accepted_any and msg_reject_record is None:
            message_statuses[msg_id] = {
                "status": "accepted",
                "reason_code": "",
                "reason_en": "",
                "reason_ur": "",
            }
        elif msg_reject_record is not None and not msg_accepted_any:
            message_statuses[msg_id] = {
                "status": "rejected",
                "reason_code": msg_reject_record["code"],
                "reason_en": msg_reject_record["reason_en"],
                "reason_ur": msg_reject_record["reason_ur"],
            }
        elif msg_accepted_any and msg_reject_record is not None:
            message_statuses[msg_id] = {
                "status": "accepted",
                "reason_code": msg_reject_record["code"],
                "reason_en": msg_reject_record["reason_en"],
                "reason_ur": msg_reject_record["reason_ur"],
            }
        else:
            message_statuses[msg_id] = {
                "status": "accepted",
                "reason_code": "",
                "reason_en": "",
                "reason_ur": "",
            }

    # Build canonical structured facts dict from fact_meta
    facts = _compile_facts(fact_meta, wishlist)

    return {
        "facts": facts,
        "fact_meta": fact_meta,
        "constraints": constraints,
        "superseded": superseded,
        "rejected": rejected,
        "ignored": ignored,
        "message_statuses": message_statuses,
    }


def _compile_facts(
    fact_meta: dict[str, dict[str, Any]],
    wishlist: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Assemble structured canonical facts dict from flat fact_meta slots."""
    facts: dict[str, Any] = {
        "venue_options": {},
        "food_options": {},
        "committed_costs": {},
        "wishlist": wishlist,
    }

    for slot, meta in fact_meta.items():
        base_key = meta["base_key"]
        subfield = meta.get("subfield")
        ref = meta.get("ref", "")
        val = meta["value"]

        if base_key == "venue_option":
            name = ref or "default"
            entry = facts["venue_options"].setdefault(name, {"name": name})
            if subfield:
                entry[subfield] = val
            else:
                entry["value"] = val
        elif base_key == "food_option":
            tier = ref or "standard"
            entry = facts["food_options"].setdefault(tier, {"tier": tier, "delivery_fee": 0})
            if subfield:
                entry[subfield] = val
            else:
                entry["price_per_head"] = val
        elif base_key == "committed_cost":
            label = ref or slot
            facts["committed_costs"][label] = int(round(val)) if isinstance(val, (int, float)) else 0
        else:
            facts[base_key] = val

    return facts
