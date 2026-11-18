# Judge Q&A Prep

Two judges, one member drawn by lot, two questions each. All three members must be able to answer everything here in their own words.

## Parts, purpose, and what breaks

| Part | Purpose | Without it |
|---|---|---|
| Parser | Splits the file, hashes messages | No update detection |
| `llm.py` | Single door to the model; honest trace | Tokens or areas misreported; disqualification |
| Reading call | Turns Roman Urdu and English into structured facts | Code cannot read language |
| Grounding | Drops numbers not in the source | Hallucinated figures reach the plan |
| Resolver | Latest price wins; authority; noise dropped | Stale price, vendor changes headcount |
| Planner | Exact arithmetic and schedule | Rounding errors, wasted tokens |
| Validator | Six checks gate every commit | Wrong message breaks the plan |
| Dependency recompute | Only affected areas recompute | Slower updates, more work |
| State file | Remembers facts and plan | No updates after first run |
| Report and i18n | Plan, trace, rejections, Urdu / English | UI points lost |

## Questions to expect

**Why is the model only used for reading?**
Language is the only part code cannot do. Arithmetic must be exact and free of tokens.

**Why one call for the whole pack?**
Per-message calls repeat the system prompt each time. One call is cheaper and the model sees conflicts side by side.

**How do you know the model's numbers are real?**
Each fact carries a verbatim quote. The grounding step checks the number appears in that message after normalising Pakistani formats. Ungrounded facts are dropped and traced.

**What happens with a constraint kind you have never seen?**
It becomes a generic constraint (area, subject, operator, value). Known subjects are enforced by code. Unknown subjects are shown as unhandled, never ignored silently.

**How do you catch the wrong message?**
Three nets: sender authority, validator on the candidate plan, supersession by date. A candidate that fails any of six checks is discarded and the old plan stays.

**Why not let the model judge whether a message is wrong?**
It would cost tokens, can be talked into agreeing, and cannot explain by rule. The checks are rules you can read.

**Why is the reason a template?**
It cites the exact rule and message id, is the same every run, and exists in English and Urdu with no extra tokens.

**What does an update do?**
One reading call on the new message, apply to a copy of state, find areas whose inputs changed, recompute those, validate, commit or reject.

**Why does your prediction say reading only?**
Planning is code. Only reading uses a model, so only that area can appear. The trace also lists recomputed areas.

**How are tokens counted?**
Copied from the provider's usage field per call. Totals are sums of recorded counts.

**Why is the headcount more than the student count?**
Students plus staff plus the judges actually needed. Everyone present needs a seat and a meal.

**Why are fewer judges than confirmed used?**
Each judge covers at most a fixed number of teams at a fixed time per team, so only the needed number are placed; the rest are reserves. The worst-case cost with all confirmed judges is shown beside it.

**What would you add with more time?**
Prayer-time lookup beyond the bundled table, a local paste UI, and a second small model to cross-check extraction when the grounding check flags many drops.

## Rehearsal

Each member explains the whole flow in 90 seconds, then answers three random questions from this file. Swap and repeat. Be ready to open the trace and point at the line that proves each answer.
