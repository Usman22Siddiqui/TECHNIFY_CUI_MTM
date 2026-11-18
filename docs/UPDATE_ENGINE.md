# Update Engine Spec

## Fresh run versus update (no flags allowed)

Computed in `run.py` from the incoming file and `state/state.json`:

1. No state file: **fresh**.
2. Some incoming message hashes already in state: **update**, using only the unseen hashes (handles a cumulative file).
3. No overlap and 4 or more messages: **fresh**. Archive the old state to `state/archive/` and start clean (this is how the unseen judging pack must behave on a laptop that already ran the sample pack).
4. No overlap and 3 or fewer messages: **update**.

The threshold is a documented heuristic. Confirm at the help desk how follow-up messages are delivered and adjust the rule in `config/defaults.toml`, not in code.

## Update flow

```
new message(s)
 -> reading call (area = reading), compact existing-key index as context
 -> schema check, grounding check
 -> copy state to a candidate
 -> supersession + authority on the candidate
 -> changed facts -> affected areas (input-hash comparison)
 -> recompute only affected areas, in dependency order
 -> validate full candidate plan (six checks)
 -> all pass: commit candidate
    any fail: reject message, keep old plan, write reason
 -> trace shows: calls (1), recomputed areas, unchanged areas, verdict
```

At most 5 calls and 1 minute. In practice: exactly 1 call.

## Rejection reason codes (all templated, bilingual)

| Code | Meaning | Example trigger |
|---|---|---|
| `UNGROUNDED` | Extracted number not found in the message | Model hallucination |
| `NO_AUTHORITY` | Sender role may not change this key | A vendor changing the order quantity |
| `BREAKS_CHECK` | Candidate plan fails a validator check | Quantity below headcount, capacity below headcount, budget exceeded |
| `OUT_OF_DATE` | A newer message already sets this fact | Old price arriving late |
| `CONTRADICTS_AUTHORITY` | Conflicts with a higher-authority fact | Non-admin lowering the approved student count |
| `UNIT_ANOMALY` | Value is orders of magnitude off the known range | Thousands versus rupees |
| `REQUEST_ONLY` | A wish, not a decision | Entertainment request |
| `NOT_RELEVANT` | No plan area affected | Personal note |

Reason template (English line, Urdu line stored alongside):
`REJECTED msg #<id> (<role>): <code>. <rule that failed>. Plan unchanged.`

## Plausible-but-wrong patterns to defend against

The brief says two of three follow-up messages change the task and one is plausible but wrong. The generic defences are:
1. Anything that makes the validator fail (`BREAKS_CHECK`).
2. Anything outside the sender's authority (`NO_AUTHORITY`).
3. Anything that contradicts a higher-authority fact with no authority of its own.
4. Quantity or capacity messages that conflict with the derived headcount.
5. Stale facts.

## Legitimate changes to accept

A changed price or committed cost from the right role should recompute only budget (and food or venue if their inputs changed). A changed headcount-driving fact from the authority role recomputes judging, headcount, venue, food, schedule and budget as their inputs change. A new constraint (for example generator needed) recomputes venue and downstream areas.

## Prediction slip

Before one follow-up, the team writes which areas will make model calls. In this design only `reading` calls a model, so the slip reads `reading`. The trace additionally lists `recomputed (code): <areas>` so the judge sees which areas actually changed. Raise this at the help desk if the organisers expect area-tagged calls.

## Tests

Practice messages from the brief (a printing cost change and a round-down order message), plus fixtures for each reason code, a cumulative file, a one-message file, and the fresh-after-update case.
