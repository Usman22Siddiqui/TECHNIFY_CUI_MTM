"""Apply new messages to a copy of state, recompute only affected areas.

Without it: full re-run on every change — slower, more tokens.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import pathlib
import time
from typing import Any

from core.extract import extract
from core.ground import ground_facts
from core.llm import LLMClient
from core.planner import (
    AREA_INPUTS,
    AREA_ORDER,
    build_plan,
    find_unhandled_constraints,
    load_defaults,
    load_known_subjects,
    load_prayer_defaults,
    plan_budget,
    plan_food,
    plan_headcount,
    plan_judging,
    plan_schedule,
    plan_venue,
)
from core.resolve import format_rejection, load_authority_config, resolve_facts
from core.trace import TraceCollector
from core.validate import all_checks_pass, first_failure, validate


# ---------------------------------------------------------------------------
# Mode detection (no flags allowed)
# ---------------------------------------------------------------------------

def detect_mode(
    incoming_messages: list[dict[str, Any]],
    existing_state: dict[str, Any] | None,
    fresh_threshold: int = 4,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Decide fresh vs update from incoming messages and existing state.

    Rules (UPDATE_ENGINE.md):
    1. No state -> fresh
    2. Some incoming hashes already in state -> update (unseen hashes only)
    3. No overlap and len(incoming) >= fresh_threshold -> fresh (archive old state)
    4. No overlap and len(incoming) < fresh_threshold -> update (all incoming)

    Returns:
        (mode, reason, messages_to_process)
    """
    if existing_state is None:
        return "fresh", "no existing state", list(incoming_messages)

    seen_hashes = {m.get("hash") for m in existing_state.get("messages", []) if m.get("hash")}
    overlap = [m for m in incoming_messages if m.get("hash") in seen_hashes]

    if overlap:
        unseen = [m for m in incoming_messages if m.get("hash") not in seen_hashes]
        return "update", f"overlap with existing state ({len(overlap)} seen, {len(unseen)} new)", unseen

    if len(incoming_messages) >= fresh_threshold:
        return (
            "fresh",
            f"no overlap and {len(incoming_messages)} >= {fresh_threshold} messages (new pack)",
            list(incoming_messages),
        )

    return (
        "update",
        f"no overlap and {len(incoming_messages)} < {fresh_threshold} messages (follow-up)",
        list(incoming_messages),
    )


# ---------------------------------------------------------------------------
# Dependency graph hashing (derived from planner.AREA_INPUTS)
# ---------------------------------------------------------------------------

def _read_dotted(obj: dict[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _area_input_hash(
    area: str,
    facts: dict[str, Any],
    plan: dict[str, Any],
    constraints: list[dict[str, Any]],
) -> str:
    """Hash the declared inputs for a single planning area."""
    spec = AREA_INPUTS[area]
    fact_slice = {k: facts.get(k) for k in spec["facts"]}
    upstream_slice = {p: _read_dotted(plan, p) for p in spec["upstream"]}
    c_areas = set(spec["constraints"])
    constraint_slice = [
        {
            "area": c.get("area"),
            "subject": c.get("subject"),
            "op": c.get("op"),
            "value": c.get("value"),
            "hard": c.get("hard", True),
        }
        for c in (constraints or [])
        if c.get("area") in c_areas or str(c.get("subject", "")).split(".")[0] in c_areas
    ]
    payload = json.dumps(
        {"facts": fact_slice, "upstream": upstream_slice, "constraints": constraint_slice},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def recompute_affected_areas(
    old_plan: dict[str, Any],
    old_facts: dict[str, Any],
    old_constraints: list[dict[str, Any]],
    new_facts: dict[str, Any],
    new_constraints: list[dict[str, Any]],
    defaults: dict[str, Any] | None = None,
    known_subjects: set[str] | None = None,
    prayer_defaults: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Recompute only areas whose input hash changed, in topological order.

    Returns:
        (candidate_plan, recomputed_areas, unchanged_areas)
    """
    cfg = defaults if defaults is not None else load_defaults()
    p_cfg = prayer_defaults if prayer_defaults is not None else load_prayer_defaults()

    before_hashes = {
        area: _area_input_hash(area, old_facts, old_plan, old_constraints)
        for area in AREA_ORDER
    }

    cand = copy.deepcopy(old_plan)
    recomputed: list[str] = []
    unchanged: list[str] = []

    for area in AREA_ORDER:
        after_hash = _area_input_hash(area, new_facts, cand, new_constraints)
        if after_hash == before_hashes[area]:
            unchanged.append(area)
            continue

        recomputed.append(area)
        if area == "judging":
            cand["judging"] = plan_judging(new_facts, new_constraints, cfg)
        elif area == "headcount":
            cand["headcount"] = plan_headcount(new_facts, cand["judging"], new_constraints)
        elif area == "venue":
            cand["venue"] = plan_venue(new_facts, cand["headcount"], new_constraints)
        elif area == "food":
            cand["food"] = plan_food(new_facts, cand["headcount"], new_constraints)
        elif area == "schedule":
            cand["schedule"] = plan_schedule(new_facts, cand["judging"], new_constraints, cfg, prayer_defaults=p_cfg)
        elif area == "budget":
            cand["budget"] = plan_budget(new_facts, cand["venue"], cand["food"], cand["judging"], new_constraints)

    # Degradation ladder if budget went over
    degradation_steps: list[str] = []
    if cand.get("budget", {}).get("status") == "over_budget":
        food = cand["food"]
        venue = cand["venue"]
        headcount = cand["headcount"]
        judging = cand["judging"]
        budget = cand["budget"]

        if food.get("status") == "ok" and food.get("alternatives"):
            tried_food = {food["tier"]}
            while budget.get("status") == "over_budget":
                alt_food = plan_food(new_facts, headcount, new_constraints, exclude_tiers=tried_food)
                if alt_food.get("status") != "ok":
                    break
                tried_food.add(alt_food["tier"])
                if alt_food["cost"] < food["cost"]:
                    degradation_steps.append(
                        f"food tier switched from '{food['tier']}' to cheaper '{alt_food['tier']}'"
                    )
                    food = alt_food
                    cand["food"] = food
                    if "food" not in recomputed:
                        recomputed.append("food")
                        if "food" in unchanged:
                            unchanged.remove("food")
                    budget = plan_budget(new_facts, venue, food, judging, new_constraints)
                    cand["budget"] = budget
                else:
                    break

        if budget.get("status") == "over_budget" and venue.get("status") == "ok" and venue.get("alternatives"):
            tried_venues = {venue["selected"]}
            while budget.get("status") == "over_budget":
                alt_venue = plan_venue(new_facts, headcount, new_constraints, exclude_names=tried_venues)
                if alt_venue.get("status") != "ok":
                    break
                tried_venues.add(alt_venue["selected"])
                if alt_venue["cost"] < venue["cost"]:
                    degradation_steps.append(
                        f"venue switched from '{venue['selected']}' to cheaper '{alt_venue['selected']}'"
                    )
                    venue = alt_venue
                    cand["venue"] = venue
                    if "venue" not in recomputed:
                        recomputed.append("venue")
                        if "venue" in unchanged:
                            unchanged.remove("venue")
                    budget = plan_budget(new_facts, venue, food, judging, new_constraints)
                    cand["budget"] = budget
                else:
                    break

    cand["degradation_steps"] = degradation_steps
    cand["unhandled_constraints"] = find_unhandled_constraints(new_constraints, known_subjects=known_subjects)
    cand["feasible"] = (
        cand.get("judging", {}).get("status") == "ok"
        and cand.get("headcount", {}).get("status") == "ok"
        and cand.get("venue", {}).get("status") == "ok"
        and cand.get("food", {}).get("status") == "ok"
        and cand.get("schedule", {}).get("feasible", False)
        and cand.get("budget", {}).get("status") == "ok"
    )
    return cand, recomputed, unchanged


# ---------------------------------------------------------------------------
# Compact key index for update extraction prompt
# ---------------------------------------------------------------------------

def build_existing_key_index(facts: dict[str, Any]) -> dict[str, Any]:
    """Return a compact summary of existing keys and refs (saves tokens)."""
    index: dict[str, Any] = {}
    for k, v in (facts or {}).items():
        if k in ("venue_options", "food_options", "committed_costs", "wishlist"):
            if isinstance(v, dict) and v:
                index[k] = sorted(v.keys())
        else:
            index[k] = v
    return index


# ---------------------------------------------------------------------------
# State persistence & archiving
# ---------------------------------------------------------------------------

def load_state(state_path: pathlib.Path) -> dict[str, Any] | None:
    if not state_path.exists():
        return None
    with open(state_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict[str, Any], state_path: pathlib.Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def archive_state(state_path: pathlib.Path) -> pathlib.Path | None:
    if not state_path.exists():
        return None
    archive_dir = state_path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = archive_dir / f"state_{ts}.json"
    dest.write_text(state_path.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# Main pipeline execution (fresh or update)
# ---------------------------------------------------------------------------

def run_pipeline(
    incoming_messages: list[dict[str, Any]],
    state_path: pathlib.Path,
    client: LLMClient | None = None,
    defaults: dict[str, Any] | None = None,
    authority_config: dict[str, Any] | None = None,
    known_subjects: set[str] | None = None,
    prayer_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the full fresh or update pipeline and return (state, trace, summary).

    Validator-gated commit: on update, candidate commits ONLY if all 6 checks pass.
    """
    t0 = time.perf_counter()
    cfg = defaults if defaults is not None else load_defaults()
    auth_cfg = authority_config if authority_config is not None else load_authority_config()
    known = known_subjects if known_subjects is not None else load_known_subjects()
    p_cfg = prayer_defaults if prayer_defaults is not None else load_prayer_defaults()
    fresh_threshold = int(cfg.get("update", {}).get("fresh_threshold", 4))
    anomaly_factor = int(cfg.get("update", {}).get("unit_anomaly_factor", 50))

    existing_state = load_state(state_path)
    mode, mode_reason, to_process = detect_mode(incoming_messages, existing_state, fresh_threshold)

    # Archive old state if starting fresh over an existing state
    if mode == "fresh" and existing_state is not None:
        archive_state(state_path)
        existing_state = None

    # Prepare trace collector (continuing session trace on update)
    trace = TraceCollector()
    start_counter = 0
    if mode == "update" and existing_state is not None:
        trace.add_calls(existing_state.get("trace_calls", []))
        for ev in existing_state.get("trace_events", []):
            trace.add_event(
                ev["type"],
                ev["text_en"],
                text_ur=ev.get("text_ur", ""),
                message_id=ev.get("message_id"),
                code=ev.get("code", ""),
            )
        start_counter = int(existing_state.get("call_counter", len(existing_state.get("trace_calls", []))))

    trace.add_event("mode", f"{mode} ({mode_reason})")

    # If update with zero unseen messages -> no model call, return existing state
    if mode == "update" and existing_state is not None and not to_process:
        elapsed = time.perf_counter() - t0
        trace.add_event("recompute", "areas: none (no new messages, 0 tokens)")
        trace.add_event("timing", f"run {elapsed:.1f} s")
        state = copy.deepcopy(existing_state)
        state["trace_events"] = trace._events
        save_state(state, state_path)
        return {
            "mode": mode,
            "committed": True,
            "recomputed": [],
            "unchanged": list(AREA_ORDER),
            "state": state,
            "trace": trace,
            "elapsed": elapsed,
        }

    # Re-assign sequential message IDs on update so they don't collide with existing messages
    if mode == "update" and existing_state is not None:
        max_id = max((int(m.get("id", 0)) for m in existing_state.get("messages", [])), default=0)
        remapped = []
        for idx, m in enumerate(to_process, start=max_id + 1):
            nm = dict(m)
            nm["id"] = idx
            remapped.append(nm)
        to_process = remapped

    # Create or reuse LLMClient
    llm = client if client is not None else LLMClient(initial_call_counter=start_counter)
    if client is not None and start_counter > llm.call_counter:
        llm._call_counter = start_counter

    # Step 1: Extraction (exactly 1 reading call; +1 repair retry only if invalid JSON)
    existing_index = (
        build_existing_key_index(existing_state.get("facts", {}))
        if mode == "update" and existing_state is not None
        else None
    )

    prev_call_len = len(llm.calls)
    try:
        ext_result = extract(llm, to_process, existing_keys=existing_index)
    except Exception as exc:
        # Record any calls made before failure
        new_calls = llm.calls[prev_call_len:]
        trace.add_calls(new_calls)
        elapsed = time.perf_counter() - t0
        trace.add_event("reject", f"extraction failed: {exc}")
        trace.add_event("timing", f"run {elapsed:.1f} s")
        if existing_state is not None:
            state = copy.deepcopy(existing_state)
            state["call_counter"] = llm.call_counter
            state["trace_calls"] = trace._calls
            state["trace_events"] = trace._events
            save_state(state, state_path)
            return {
                "mode": mode,
                "committed": False,
                "recomputed": [],
                "unchanged": list(AREA_ORDER),
                "state": state,
                "trace": trace,
                "elapsed": elapsed,
            }
        raise

    new_calls = llm.calls[prev_call_len:]
    trace.add_calls(new_calls)

    # Convert pydantic result to plain dicts
    extracted_dicts = [m.model_dump() for m in ext_result.m]

    # If model returned original local id (e.g. 1) on a 1-message update when we remapped id, align it
    if len(to_process) == 1 and len(extracted_dicts) == 1:
        extracted_dicts[0]["i"] = to_process[0]["id"]

    # Step 2: Grounding
    grounded_msgs, dropped_facts = ground_facts(extracted_dicts, to_process)
    for d in dropped_facts:
        trace.add_event(
            "ungrounded",
            f"msg #{d['message_id']} {d['key']} {d['value']} dropped",
            message_id=d["message_id"],
            code="UNGROUNDED",
        )

    # Step 3: Resolve (on a candidate copy of existing state if update)
    resolved = resolve_facts(
        grounded_msgs,
        authority_config=auth_cfg,
        existing_state=existing_state if mode == "update" else None,
        unit_anomaly_factor=anomaly_factor,
    )

    for sup in resolved["superseded"]:
        trace.add_event(
            "superseded",
            f"msg #{sup['old_id']} replaced by msg #{sup['new_id']} ({sup['key']})",
        )

    for rej in resolved["rejected"]:
        trace.add_event(
            "reject",
            rej["reason_en"],
            text_ur=rej["reason_ur"],
            message_id=rej["message_id"],
            code=rej["code"],
        )

    # Build message records for newly processed messages
    ext_role_by_id = {int(m.get("i", 0)): str(m.get("r", "unknown")) for m in grounded_msgs}
    ext_date_by_id = {int(m.get("i", 0)): m.get("d") for m in grounded_msgs}
    new_msg_records: list[dict[str, Any]] = []
    for m in to_process:
        mid = m["id"]
        st = resolved["message_statuses"].get(mid, {"status": "accepted", "reason_code": "", "reason_en": "", "reason_ur": ""})
        new_msg_records.append({
            "id": mid,
            "hash": m["hash"],
            "sender": m.get("sender", ""),
            "role": ext_role_by_id.get(mid, "unknown"),
            "date": m.get("date") or ext_date_by_id.get(mid),
            "text": m.get("text", ""),
            "status": st["status"],
            "reason_code": st["reason_code"],
            "reason_en": st["reason_en"],
            "reason_ur": st["reason_ur"],
        })

    # Step 4: Plan (full on fresh; dependency recompute on update)
    if mode == "fresh" or existing_state is None:
        candidate_plan = build_plan(
            resolved["facts"],
            resolved["constraints"],
            defaults=cfg,
            known_subjects=known,
            prayer_defaults=p_cfg,
        )
        recomputed = list(AREA_ORDER)
        unchanged: list[str] = []
    else:
        candidate_plan, recomputed, unchanged = recompute_affected_areas(
            old_plan=existing_state["plan"],
            old_facts=existing_state["facts"],
            old_constraints=existing_state.get("constraints", []),
            new_facts=resolved["facts"],
            new_constraints=resolved["constraints"],
            defaults=cfg,
            known_subjects=known,
            prayer_defaults=p_cfg,
        )

    rec_str = ", ".join(recomputed) if recomputed else "none"
    unc_str = ", ".join(unchanged) if unchanged else "none"
    trace.add_event("recompute", f"areas: {rec_str} (code, 0 tokens); unchanged: {unc_str}")

    for u in candidate_plan.get("unhandled_constraints", []):
        trace.add_event("unhandled", f"constraint subject not enforced: {u.get('subject')}")

    # Step 5: Validate six checks
    checks = validate(candidate_plan, resolved["facts"], resolved["constraints"], defaults=cfg)
    check_line = " | ".join(
        f"{name} {'ok' if checks[name]['ok'] else 'FAIL'}"
        for name in ("figures", "budget", "venue", "schedule", "judges", "coverage")
    )
    trace.add_event("check", check_line)

    # Step 6: Validator-gated commit
    committed = True
    if mode == "update" and existing_state is not None and not all_checks_pass(checks):
        # REJECT candidate, keep old plan!
        committed = False
        fail_info = first_failure(checks)
        fail_check = fail_info[0] if fail_info else "unknown"
        fail_detail = fail_info[1].get("detail", "validation failed") if fail_info else "validation failed"

        state = copy.deepcopy(existing_state)
        for rec in new_msg_records:
            r_en, r_ur = format_rejection(
                rec["id"],
                rec["role"],
                "BREAKS_CHECK",
                check=fail_check,
                detail=fail_detail,
            )
            rec["status"] = "rejected"
            rec["reason_code"] = "BREAKS_CHECK"
            rec["reason_en"] = r_en
            rec["reason_ur"] = r_ur
            state["messages"].append(rec)
            trace.add_event(
                "reject",
                r_en,
                text_ur=r_ur,
                message_id=rec["id"],
                code="BREAKS_CHECK",
            )

        state["call_counter"] = llm.call_counter
        state["trace_calls"] = trace._calls
        state["trace_events"] = trace._events
    else:
        # Commit fresh state or passing update candidate
        pack_id = (
            existing_state["pack_id"]
            if mode == "update" and existing_state is not None
            else hashlib.sha256(
                "".join(m["hash"] for m in incoming_messages).encode("utf-8")
            ).hexdigest()[:16]
        )
        all_messages = (
            list(existing_state.get("messages", [])) + new_msg_records
            if mode == "update" and existing_state is not None
            else new_msg_records
        )

        # Mark superseded messages in message history
        sup_old_ids = {s["old_id"] for s in resolved["superseded"]}
        for m in all_messages:
            if m["id"] in sup_old_ids and m["status"] == "accepted":
                newer = next((s["new_id"] for s in resolved["superseded"] if s["old_id"] == m["id"]), 0)
                m["status"] = "superseded"
                m["reason_code"] = "SUPERSEDED"
                m["reason_en"] = f"Superseded by msg #{newer}"
                m["reason_ur"] = f"پیغام #{newer} سے تبدیل ہو گیا"

        state = {
            "pack_id": pack_id,
            "messages": all_messages,
            "facts": resolved["facts"],
            "fact_meta": resolved["fact_meta"],
            "constraints": resolved["constraints"],
            "plan": candidate_plan,
            "checks": checks,
            "call_counter": llm.call_counter,
            "trace_calls": trace._calls,
            "trace_events": trace._events,
        }

    elapsed = time.perf_counter() - t0
    trace.add_event("timing", f"run {elapsed:.1f} s")
    state["trace_events"] = trace._events
    save_state(state, state_path)

    return {
        "mode": mode,
        "committed": committed,
        "recomputed": recomputed,
        "unchanged": unchanged,
        "state": state,
        "trace": trace,
        "elapsed": elapsed,
    }
