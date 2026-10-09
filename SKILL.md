---
name: token-research-engineer
description: >-
  Screen blockchain tokens before anything else touches them: turn a chain's raw
  launch firehose into a short, evidence-backed candidate list. Use when the task
  is to scan newly launched tokens, catch older tokens starting to gain traction,
  triage a token by mint/contract address, define or tune token filters, verify
  mint / LP / holder / authority safety, judge whether a token can actually be
  sold, or produce a token research verdict. Covers per-chain verification
  differences (Solana first; EVM, BSC, Base later) and the
  discover → screen → enrich → score → verdict pipeline. NOT for placing trades,
  signing transactions, or holding keys.
---

# token-research-engineer

A research engineer for a token intelligence system. Its job is **not** to look at
every token a chain launches. Its job is to answer one question repeatedly, cheaply
and honestly:

> Of everything being launched or waking up right now, which tokens match the
> operator's own definition of "worth researching", and what exactly is the
> evidence for that?

## Hard rules (these are the whole point — read before anything else)

1. **A criterion without a source is not a criterion.** Every check names the exact
   field it reads and the exact source it reads it from. This is what makes the
   skill grounded in blockchain technology instead of vibes.
2. **The model never computes the score.** Counting, ratios, thresholds and
   verdicts are deterministic code over the Candidate Record. The model writes the
   narrative, the hypothesis and the open questions — and only over facts that are
   present in the record.
3. **No fact without `(value, source, observed_at, method)`.** If it is not in the
   record, it goes in `unknowns`, never into the prose.
4. **`unknown` is a first-class result.** Missing data is never silently treated as
   pass or fail; each criterion carries its own `missing_policy`.
5. **Chains are not interchangeable.** A field that means "authority revoked" on
   Solana has no EVM equivalent. Never reuse a chain's adapter on another chain.
6. **Read-only, always.** No swap execution, no approvals, no signing, no keys.
   Questioning a token is research; touching it is out of scope.

## Vocabulary (fixed — other files depend on these names)

| Term | Meaning |
|---|---|
| **Chain adapter** | Per-chain module that turns an address into measurable fields. `adapters/solana` first. |
| **Lane** | A named scan scope: what *kind* of token you are hunting right now (`new_launch`, `graduation`, `traction`, `watchlist`). |
| **Criterion** | One atomic check, with a stable id (`AUTH_MINT`, `SELL_ROUTE`, …). |
| **Candidate Record** | The evidence object for one token: fields, sources, timestamps, costs. |
| **Verdict** | `REJECT` \| `WATCH` \| `RESEARCH` \| `CANDIDATE`. |

## Routing

| Need | Read |
|---|---|
| How the scan works end to end, cost, rate limits, the graph | `reference/pipeline.md` |
| The catalogue of checks: kill vs score, thresholds, missing policy | `reference/criteria.md` |
| Solana specifics: which on-chain field, which program, which trap | `reference/solana-adapter.md` |
| Which API / MCP gives which field, and the safety rules for them | `reference/sources.md` |
| The exact shape of a record and a verdict | `reference/record-schema.md` |
| The operator's own thresholds — **edit this, not the prose** | `config/filters.solana.yaml` |
| Turning an agent into this research engineer | `agent/research-engineer.md` |

## Operating loop

1. Load config. Confirm `chain`, `lane`, `position_size_usd`, and the call budget.
2. Run the pipeline in `reference/pipeline.md`. Screen cheap first; enrich only
   survivors.
3. Emit one Candidate Record per survivor, one Verdict each, and a run summary.
4. Report what was **not** checked and why. A short honest list beats a long
   confident one.

## What this skill is not

- Not a trading bot and not a signal group. It produces research, not entries.
- Not exhaustive: it is a **filter**, and a filter's value is measured by what it
  correctly throws away. Track that (`stats.rejected_by_criterion`) — a criterion
  that never kills anything is dead weight, and one that kills everything is
  misconfigured.
