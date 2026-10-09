# pipeline — how a token becomes a verdict

> Design note up front: this is a **graph with two bounded loops**, not one big
> polling loop. A single loop degrades because it re-pays for the same work every
> cycle: it re-fetches everything, re-scores everything, and the cost per useful
> candidate grows without bound. The graph splits *cheap rejection* from
> *expensive verification* and only pays for the second stage on survivors.

---

## The graph

```
S0 SCOPE ─► S1 DISCOVER ─► S2 NORMALIZE ─► S3 DEDUPE ─┐
                                                       │
        ┌──────────────────────────────────────────────┘
        ▼
   S4 SCREEN  (cheap, hard kills)          ──► rejected[]  (record kept, one line each)
        │ survivors
        ▼
   BUDGET GATE  ──► if calls remain = 0: emit WATCH for the rest, do not fabricate
        │
        ▼
   S5 ENRICH  (per-chain adapter, tiered fan-out)
        │
        ▼
   S6 SCORE  (deterministic)  ──► S7 DECIDE ──► S8 REPORT
                                                      │
                        ┌─────────────────────────────┴───────────┐
                        ▼                                         ▼
                  L1: re-scan queue                       (run ends)
                  (WATCH only, delta check)
```

### Stages

| Stage | In | Does | Out | Cost |
|---|---|---|---|---|
| **S0 SCOPE** | run request | Load `config/*.yaml`; fix chain, lane, `position_size_usd`, budget, time window | run config | 0 |
| **S1 DISCOVER** | run config | Run the collectors for this lane (see below). Discovery is *dumb on purpose* — it collects, it does not judge. | raw candidates | low, many |
| **S2 NORMALIZE** | raw candidates | Map every collector's shape to one identity: `chain`, `address`, `symbol`, `age_minutes`, `seen_in[]` | normalized | 0 |
| **S3 DEDUPE** | normalized | Key = `chain:address`. Merge `seen_in[]`, never merge conflicting numeric fields — keep both with their sources. | unique candidates | 0 |
| **S4 SCREEN** | unique candidates | Only `kind: kill` criteria that are answerable from **1–2 cheap calls** (mint account, pair lookup). Survivors get a `screen_score`. | survivors + reject list | low, per token |
| **BUDGET GATE** | survivors | Rank survivors by `screen_score`; spend the remaining enrichment budget top-down. | enriched set | 0 |
| **S5 ENRICH** | enriched set | Chain adapter fills the record in tiers (below). Fan-out is parallel but rate-limited per source. | Candidate Records | high, few |
| **S6 SCORE** | records | Apply `kind: score` criteria. Pure arithmetic, no model. | scored records | 0 |
| **S7 DECIDE** | scored records | Map score + any remaining kills to a Verdict. | verdicts | 0 |
| **S8 REPORT** | verdicts | Evidence bundle + run summary. | report | 0 |

### Why the split matters

S4 exists so that the expensive stage never sees the long tail. On a busy chain the
ratio should be roughly **100 discover : 10 screen : 1 enrich**. If you ever find
yourself enriching 50% of what you discovered, a kill criterion is missing or its
source is too expensive to be used at screen time — fix the criterion, not the
budget.

---

## Collectors (S1), by lane

| Lane | Collector | What it is for |
|---|---|---|
| `new_launch` | new-pair stream from the DEX aggregator + launchpad program logs | every new pool / mint, unfiltered |
| `graduation` | launchpad program logs (curve completion / migration event) | tokens leaving a bonding curve into a real AMM pool |
| `traction` | trending / mover feeds + pool liquidity deltas | **older** tokens waking up — this is where "old token starts getting volume" lives |
| `watchlist` | the previous run's `WATCH` set | re-check, not re-discover |

`traction` is the lane people get wrong. It is not a launch feed sorted by volume —
it is a **delta** over time: liquidity grew, unique buyers grew, volume/liquidity
crossed a threshold, holders grew while price was flat. Collect it as a time series
(the same address observed across runs) and evaluate the delta in S6. A single
snapshot cannot tell "waking up" from "always noisy".

---

## Enrichment tiers (S5)

Fill in this order. Each tier is a budget boundary: if the budget dies mid-run, the
record is still valid at the tier it reached, and every unvisited tier's criteria
resolve to `unknown`.

| Tier | Fills | Roughly |
|---|---|---|
| **T1 core** | mint/supply/decimals, authorities, token extensions, holder distribution, pool + liquidity, sell route | 2–5 calls |
| **T2 behavioural** | unique buyers vs trades, volume/liquidity, wash pattern, deployer identity + deployer history, launch-window bundle share | 5–30 calls (indexer) |
| **T3 contextual** | metadata/socials validity, narrative, age, listing/CEX presence, boost/paid-promo signals | 1–5 calls + human/OSINT |

`T2` is where the honest answers live and where the budget goes. A record that only
reached `T1` can still be `WATCH`; it should not be `CANDIDATE`.

---

## The two bounded loops

Everything else is one pass. Exactly two things may repeat:

**L1 — re-scan (scheduled, delta only).** Only `WATCH` verdicts are eligible. On
re-scan, compare against the *stored* previous record and evaluate the delta:
`liquidity_delta`, `holder_delta`, `volume_liq_ratio` change, `route` change,
`authority` change. Never re-enrich from zero. Bounds: `rescan_max_age_hours`,
`rescan_max_attempts`. A token that stays flat after N attempts drops to `REJECT`
with reason `stale_watch` — that is a *correct* outcome, and it keeps the queue from
becoming a graveyard.

**L2 — data-gap escalation (exactly one hop).** A `kill` criterion that lands on
`unknown` may try **one** alternate source named in `reference/sources.md`. If the
alternate is also silent, the criterion resolves per `missing_policy`. There is no
third try: a source outage must surface as `unknown`, never as a retry storm.

**Anti-pattern (explicitly forbidden):** re-running S5 on the same token inside the
same window because "we might learn more". More calls do not produce more truth;
they produce rate-limit bans and non-reproducible runs.

---

## Cost and rate-limit discipline

| Resource | Rule |
|---|---|
| RPC | cheapest first; `getAccountInfo` before anything indexed. Never poll a public RPC in a tight loop. |
| DEX aggregator API | free tier is generous but rated (~hundreds of req/min). One lookup per token per run; batch where the API allows. |
| Indexer (paid) | the scarce resource. Reserved for `T2` survivors only. Track credits per run. |
| Launchpad program logs | subscribe/webhook rather than re-scanning history when available; history scans are the classic cost blowup. |

Every run records `run.costs` per source. If a source's cost per surviving candidate
rises, that is a signal the kill criteria upstream got looser — check S4 before
blaming the source.

---

## Reproducibility

Same config + same `as_of` timestamp ⇒ same verdicts. Therefore:

- pin the config (`config_hash` in the report),
- record every source response's `observed_at`,
- never let a model's judgement enter S4/S6/S7,
- store the record, not just the verdict — a verdict without its record cannot be
  re-audited later, and this class of research is judged in hindsight.

---

## Run summary (S8)

Emit alongside the verdicts:

```yaml
run:
  started_at: "2026-10-09T12:00:00Z"
  chain: solana
  lane: traction
  config_hash: "<sha256 of the resolved config>"
  discovered: 412
  after_dedupe: 388
  killed: 361
  enriched: 27        # T1+, budget-limited
  verdicts: {REJECT: 361, WATCH: 19, RESEARCH: 6, CANDIDATE: 2}
  rejected_by_criterion: {EXT_TRANSFER_HOOK: 84, SELL_ROUTE: 71, AUTH_FREEZE: 65, ...}
  costs: {rpc_credits: 1180, indexer_credits: 240, api_calls: 96}
  degraded_sources: ["birdeye (quota)"]
  unverified: ["governance/multisig status for 27 records: no source configured"]
```

`rejected_by_criterion` is not decoration — it is how the operator knows whether the
filter still matches their intent, and `degraded_sources` is how a quietly broken
run is told apart from a genuinely quiet market.
