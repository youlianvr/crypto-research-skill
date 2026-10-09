# record-schema — the contract between stages

The Candidate Record is the only thing that travels between stages. It is also the
only thing that may be turned into prose. Two rules:

1. A stage may only add fields, never overwrite a value that already carries a
   different source — keep both, the disagreement is data.
2. Every measured value carries `source`, `observed_at`, and `method`. A bare number
   in this record is a bug.

---

## 1. Candidate Record

```jsonc
{
  "identity": {
    "chain": "solana",
    "address": "<mint/contract>",
    "token_program": "spl_token | token_2022",
    "symbol": "…",
    "name": "…",
    "age_minutes": 4820,
    "seen_in": ["new_launch", "traction"],
    "first_seen_at": "2026-10-08T04:11:07Z"
  },

  "authorities": {
    "mint":     { "value": null,  "source": "rpc",     "observed_at": "…", "method": "getAccountInfo/jsonParsed" },
    "freeze":   { "value": null,  "source": "rpc",     "observed_at": "…", "method": "getAccountInfo/jsonParsed" },
    "metadata_mutable": { "value": true, "source": "rpc", "observed_at": "…", "method": "metadata account" }
  },

  "extensions": [
    { "type": "transfer_fee", "detail": { "bps": 200 }, "source": "rpc", "observed_at": "…" }
  ],

  "supply":  { "raw": "…", "decimals": 9, "anomaly": false, "source": "rpc" },

  "holders": {
    "count": 1840,
    "top10_excluding_pools_pct": 22.4,
    "top1_excluding_pools_pct": 6.1,
    "pool_owners_identified": true,
    "known_custody_pct": 3.9,
    "growth_rate_24h_pct": 12.7,
    "source": "indexer",
    "method": "holders excluding discovered pool/vault owners"
  },

  "liquidity": {
    "pools": [{ "address": "…", "dex": "…", "quote": "SOL", "usd": 84000, "kind": "standard_amm" }],
    "usd": 84000,
    "lp_locked_or_burned": null,          // null ⇒ n/a on a standard AMM, NOT "no"
    "lp_held_by_deployer": false,
    "one_sided": false,
    "source": "aggregator+rpc"
  },

  "market": {
    "price_usd": 0.00042, "fdv_usd": 420000, "market_cap_usd": 420000,
    "volume_24h_usd": 310000,
    "fdv_over_liquidity": 5.0, "source": "aggregator"
  },

  "tradability": {
    "route_exists": true,
    "price_impact_pct": 1.8,
    "simulated": { "ran": true, "err": null, "source": "rpc", "observed_at": "…" }
  },

  "trades": {
    "buys": 940, "sells": 810, "buys_over_sells": 1.16,
    "volume_over_liquidity": 3.69,
    "unique_buyers": 610, "unique_buyers_over_trades": 0.65,
    "roundtrip_wallets_pct": 8.2,
    "source": "aggregator+indexer"
  },

  "deployer": {
    "address": "…",
    "identity_confidence": "high",       // low when derived from a launchpad fee payer
    "current_hold_pct": 1.4,
    "prior_launch_count": 2,
    "prior_rugged_tokens": 0,
    "funding_provenance": "cex_withdrawal",
    "source": "indexer"
  },

  "launch": { "bundled_or_single_slot_share_pct": 11.0, "source": "indexer" },

  "socials": { "site": "…", "x": "…", "oldest_account_age_days": 41, "source": "metadata+osint" },
  "context": { "boost_or_paid_listing": false, "cex_listings": [] },

  "unknowns": ["liquidity.lp_locked_or_burned"],   // n/a vs unknown kept distinct
  "na":       ["extensions.non_transferable"],      // does not apply on this chain
  "flags":    [{ "id": "POOL_EXCLUDED_BY_INDEXER", "note": "could not re-verify pool owners via RPC" }],

  "observed_window": { "from": "…", "to": "…" },
  "costs": { "rpc": 14, "indexer": 6, "aggregator": 3 },
  "config_hash": "…"
}
```

### Field conventions

| Rule | Reason |
|---|---|
| `null` inside a value object ⇒ **revoked / absent by design**; `unknown` ⇒ unread | collapsing these is the adapter's #1 lie (see `solana-adapter.md` §10) |
| `na` array ⇒ criterion does not apply here | keeps "not applicable" from being reported as "we don't know" |
| `unknowns` ⇒ applies but unread, **and blocks `CANDIDATE`** | unknown is not a pass |
| `identity_confidence: low` ⇒ no kill may fire off derived deployer fields | the fee-payer trap |
| `method` string ⇒ human can re-derive the number later | auditing |

---

## 2. Verdict

```jsonc
{
  "identity": { "chain": "solana", "address": "…", "symbol": "…" },
  "verdict": "RESEARCH",
  "lane": "traction",
  "score": { "total": 61, "max": 85, "contributions": [
    { "id": "HOLDER_GROWTH", "points": 12 },
    { "id": "SELL_IMPACT",   "points": 15 }
  ]},
  "kills": [],                                  // non-empty ⇒ verdict must be REJECT
  "blocking_unknowns": [],
  "headline": "one sentence, no adjectives the record does not support",
  "evidence": [
    { "criterion": "SELL_ROUTE", "value": "ok (impact 1.8% at $2k)", "source": "aggregator+rpc", "observed_at": "…" }
  ],
  "unknowns": ["…"],
  "next_checks": ["transaction-level unique-buyer re-count", "…"],
  "what_would_change_this": ["freeze authority restored", "liquidity < $25k", "…"],
  "rescan": { "eligible": true, "after": "2026-10-09T18:00:00Z", "attempts": 0 }
}
```

### Verdict semantics

| Verdict | Means | Required condition |
|---|---|---|
| `REJECT` | does not match the operator's filter | at least one `kill` hit, **or** score below the lane floor |
| `WATCH` | plausible, not yet researched | no kills, but `blocking_unknowns` non-empty or tier < T2 |
| `RESEARCH` | worth human time now | no kills, no blocking unknowns, T2 complete, score ≥ research floor |
| `CANDIDATE` | matches the operator's written definition | above the candidate floor, and the operator's own `candidate_requires` list is fully satisfied |

`kills` non-empty while `verdict != REJECT` is an invalid record — reject the record,
do not "explain" it.

---

## 3. The anti-hallucination contract

The model in this pipeline is allowed to:

- write `headline`, `next_checks`, `what_would_change_this`;
- summarise `evidence` rows that exist;
- propose a hypothesis for a human to test.

The model is **not** allowed to:

- produce a number that is not in the record;
- upgrade a `WATCH` to `RESEARCH` on the strength of narrative;
- state a social, a team, a roadmap or a partnership that the record does not contain;
- soften a `kill` into a caveat.

If a run's prose contains a claim that cannot be traced to an `evidence` row, that run
is defective regardless of whether the claim happens to be true — the point of the
record is that the *next* person can re-derive it.

---

## 4. Storage

- One record per `chain:address` per run window; keep history, do not mutate.
- The `L1` re-scan loop reads the previous record and writes a **new** one with a
  `delta` block — never an edit in place. Delta-only comparison is what keeps the
  re-scan affordable, and the history is what turns this from a scanner into a
  research desk.
- Retention: records are cheap (small JSON); verdicts without records are worthless.
  Keep the record even when the verdict was `REJECT` — the rejection is a data point
  about the filter, which is what the operator is actually tuning.
