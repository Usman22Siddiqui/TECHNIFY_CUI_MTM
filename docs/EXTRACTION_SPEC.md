# Extraction Spec (the only model call)

Area tag: `reading`. One call per fresh run, one per update.

## Job of the model

For each message: who sent it, what role that sender plays, its date, whether it matters to the plan, and the structured facts and constraints it contains. The model does **not** decide which fact wins, does not compute anything, and does not judge validity.

## Output schema (compact keys save tokens)

```
{
 "m": [
  {
   "i": 1,                       // message id as numbered in the input
   "r": "authority|finance|venue|caterer|judging|requester|participant|unknown",
   "d": "YYYY-MM-DD" | null,
   "k": "fact|request|notice|noise",
   "f": [ { "key": "<canonical key>", "v": 123, "u": "PKR|min|count|bool|text", "q": "exact quote from message", "ref": "optional item label" } ],
   "c": [ { "a": "venue|schedule|food|judging|budget", "s": "<subject>", "op": "min|max|eq|require|forbid|window", "v": ..., "hard": true, "q": "quote" } ]
  }
 ]
}
```

## Canonical fact keys (closed vocabulary, shapes only)

`students`, `team_size`, `duration_min`, `budget_total`, `staff`, `prayer_break_min`, `venue_option` (ref = name; fields capacity, price, generator), `food_option` (ref = tier; fields price_per_head, delivery_fee), `judges_confirmed`, `honorarium`, `judge_min_per_team`, `judge_max_teams`, `committed_cost` (ref = label), `wishlist_item` (ref = label), `start_time`, `event_date`, `late_note`.

Structured items (venue_option, food_option) are emitted as one fact per field with the same `ref`, so the grounding check can verify each number separately.

## Constraint subjects (open set, code handles the known ones)

Known to code (see `config/subjects.json`): `venue.generator`, `venue.capacity_min`, `venue.max_price`, `venue.accessible`, `food.halal`, `food.vegetarian_share`, `food.max_price_per_head`, `schedule.start_time`, `schedule.break_min`, `schedule.no_session_window`, `judging.min_per_team`, `judging.max_teams_per_judge`, `budget.cap`, `budget.reserve`, `staff.min`.

Unknown subjects are never dropped silently. They are stored as `unhandled` and shown in the UI and trace with a note, so the team can explain what was seen and not enforced.

## Prompt rules (write the prompt from these, no pack facts)

1. State the task, the JSON shape and the closed key list. Nothing else.
2. Messages may be English, Roman Urdu or Urdu script, often mixed. Money may appear as `Rs`, `PKR`, `rupay`, `k`, `hazar`, `lakh`, `lac`, `crore`, or Pakistani digit grouping like `6,50,000`. Always return plain integers in rupees.
3. A quote (`q`) must be copied verbatim from the message.
4. If a value is unclear, omit the fact. Never guess.
5. Mark requests ("can we get...") as `k: "request"`, not `fact`.
6. Mark chatter that does not touch venue, schedule, food, judging or budget as `noise`.
7. Output JSON only, no prose.

## After the call (all plain code)

1. **Schema check** with pydantic. Invalid: one repair retry, traced.
2. **Grounding check** (`ground.py`): for every numeric fact, the normalised number must appear in the normalised source message (handles commas, lakh grouping, `k`, number words). Ungrounded facts are dropped and logged with reason code `UNGROUNDED`.
3. **Supersession** (`resolve.py`): same key and same `ref`, latest `d` wins. Older entries get status `superseded` with a reason naming the newer message. Tie on date: later message id wins.
4. **Authority** (`config/authority.json`): role to allowed keys. A fact outside its role's keys is rejected with `NO_AUTHORITY`.
5. **Relevance:** `noise` and `request` messages never enter the plan. Requests are kept in a wishlist for the UI.

## Token-saving tactics

- One call for the whole pack, not one per message.
- Short system prompt; compact keys; no explanations in output.
- For updates, send only the new message(s) plus a compact index of existing keys and refs, not the full state.
- Temperature 0, `max_tokens` capped to the expected output size.

## Edge cases the fixtures must cover

Roman Urdu prices, Urdu script messages, price written as words, two messages that contradict, a message with no plan relevance, a message from an unknown sender, a message with a unit trap (thousands versus rupees), a message that restates old facts.
