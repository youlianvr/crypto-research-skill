# criteria — the catalogue of checks

This file is the *catalogue*. It defines every check the engineer knows how to run,
what it means, and what happens when the data is missing. The **thresholds** are
not here — they live in `config/filters.solana.yaml`, so the operator can tune the
filter without rewriting it.

Each criterion has a stable `id`. Records and reports reference criteria by id, so
a verdict can always be traced back to the checks that produced it.

---

## Semantics

| `kind` | Meaning | Effect on the verdict |
|---|---|---|
| `kill` | A disqualifier. One hit ⇒ `REJECT`, regardless of score. | veto |
| `score` | A weighted signal. Contributes to the total. | points |
| `info` | Recorded for the human, never scores. | none |

`missing_policy` — what to do when the field is unobtainable:

| Policy | Behaviour | Use for |
|---|---|---|
| `FAIL_CLOSED` | treat as a kill hit, reason `unknown:<id>` | safety-critical fields you must not assume safe |
| `FAIL_OPEN` | ignore, add a `flag` | nice-to-have signals |
| `UNKNOWN_OK` | record `unknown`, keep going, and **block the `CANDIDATE` verdict** | important but non-fatal fields |

The `field` column is **adapter-defined**: the criterion is chain-agnostic, the
adapter maps it onto that chain's reality. `AUTH_MINT` means "the privilege that can
create new supply is permanently gone" — how that is expressed on Solana, on a
proxy-upgradeable EVM token, or on a Token-2022 mint is the adapter's problem, and
`reference/solana-adapter.md` handles Solana.

---

## A. Supply & authority

| id | kind | field | default | missing | Why |
|---|---|---|---|---|---|
| `AUTH_MINT` | kill | `authorities.mint` revoked | required null | FAIL_CLOSED | an active mint authority can inflate at will |
| `AUTH_FREEZE` | kill | `authorities.freeze` revoked | required null | FAIL_CLOSED | freeze lets the issuer lock holders out of selling |
| `AUTH_METADATA_MUTABLE` | score | `metadata.mutable` | −5 if true | FAIL_OPEN | mutable metadata can swap a logo/name post-launch |
| `AUTH_OWNER_RENOUNCED` | kill\* | `authorities.contract_owner` | required renounced/proxy-safe | FAIL_CLOSED | *EVM-lane criterion; on chains without an upgradeable owner it resolves `n/a`* |
| `SUPPLY_ANOMALY` | kill | `supply.anomaly` | none | UNKNOWN_OK | mint-many-times / re-mint patterns, absurd supply vs claimed |

`AUTH_OWNER_RENOUNCED` is an **EVM-lane** criterion. It is declared under
`declared_not_applicable` in `config/filters.solana.yaml` rather than left out, so
that the catalogue-to-config mapping stays auditable: an id that is in neither the
config's `criteria:` block nor its `declared_not_applicable` list means the two files
have drifted apart.

## B. Token semantics / transfer restrictions

The single highest-value block on modern Solana. A token can pass every market check
and still be un-sellable at the protocol level.

| id | kind | field | default | missing | Why |
|---|---|---|---|---|---|
| `EXT_TRANSFER_HOOK` | kill | `extensions.transfer_hook` absent | required absent | FAIL_CLOSED | a hook program runs on every transfer and can simply revert sells |
| `EXT_PERMANENT_DELEGATE` | kill | `extensions.permanent_delegate` absent | required absent | FAIL_CLOSED | delegate can move/burn tokens from any wallet, forever |
| `EXT_NON_TRANSFERABLE` | kill | `extensions.non_transferable` false | required false | FAIL_CLOSED | literally cannot be transferred |
| `EXT_DEFAULT_FROZEN` | kill | `extensions.default_account_state` unfrozen | required unfrozen | FAIL_CLOSED | new holders' accounts arrive frozen |
| `EXT_TRANSFER_FEE` | score | `extensions.transfer_fee_bps` | −1 per 100 bps | UNKNOWN_OK | a fee on transfer taxes every exit; fine if tiny, fatal if large |
| `EXT_INTEREST_BEARING` | info | `extensions.interest_bearing` | — | FAIL_OPEN | benign usually, but distorts "supply" readings |
| `EXT_CONFIDENTIAL_TRANSFER` | score | `extensions.confidential_transfer` | −3 if true | FAIL_OPEN | you cannot verify what you cannot see |

## C. Holder distribution

| id | kind | field | default | missing | Why |
|---|---|---|---|---|---|
| `TOP10_EX_LP` | kill | `holders.top10_excluding_pools_pct` | ≤ 30 | FAIL_CLOSED | concentration ⇒ one wallet can end the token |
| `TOP1_EX_LP` | score | `holders.top1_excluding_pools_pct` | ≤ 10 | UNKNOWN_OK | single-wallet overhang |
| `LP_ACCOUNTED` | kill | `holders.pool_owners_identified` true | required | UNKNOWN_OK | **if you did not exclude pool accounts, the concentration number is meaningless** — see the adapter's trap list |
| `HOLDERS_MIN` | kill | `holders.count` | lane-dependent | UNKNOWN_OK | a "community" of 12 wallets is a launch, not a distribution |
| `HOLDER_GROWTH` | score | `holders.growth_rate` | + points | UNKNOWN_OK | traction lane's primary signal |
| `CEX_CUSTODY_UNRESOLVED` | info | `holders.known_custody_pct` | — | FAIL_OPEN | an exchange wallet is not a whale exit |

## D. Liquidity & market structure

| id | kind | field | default | missing | Why |
|---|---|---|---|---|---|
| `LP_PRESENT` | kill | `liquidity.pools` non-empty | required | FAIL_CLOSED | no pool ⇒ nothing to research |
| `LIQ_USD_MIN` | kill | `liquidity.usd` | lane-dependent | FAIL_CLOSED | thin liquidity ⇒ your own exit moves the price |
| `LP_LOCKED` | score | `liquidity.lp_locked_or_burned` | + points | UNKNOWN_OK | **read the adapter: "locked/burned LP" is not universal — on many AMMs the LP is held by the pool itself** |
| `LP_OWNER_WALLET` | kill | `liquidity.lp_held_by_deployer` false | required false | FAIL_CLOSED | deployer holding the LP can pull the floor |
| `FDV_LIQ_RATIO` | score | `market.fdv_over_liquidity` | ≤ 30 | FAIL_OPEN | an FDV far above liquidity prices a token you cannot sell |
| `POOL_ONE_SIDED` | kill | `liquidity.one_sided` false | required false | FAIL_CLOSED | one-sided pools are a rug shape, not a market |
| `MCAP_MIN` | kill | `market.market_cap_usd` | ≥ 25000 (`traction`) | UNKNOWN_OK | a floor under the noise; **must resolve `n/a` in `new_launch`** — there a tiny cap is the point, not a defect |

## E. Trade behaviour (the fraud filter)

| id | kind | field | default | missing | Why |
|---|---|---|---|---|---|
| `SELL_ROUTE` | kill | `tradability.route_exists` (sell → quote asset) | required true | FAIL_CLOSED | **the cheapest real honeypot test**; buy-only is the whole trap |
| `SELL_IMPACT` | kill | `tradability.price_impact_pct` at `position_size_usd` | ≤ 5% | FAIL_CLOSED | a route that exists but eats you is not a route |
| `BUY_SELL_BALANCE` | score | `trades.buys_over_sells` | 0.5–3.0 band | UNKNOWN_OK | extreme one-way flow flags wash or trap |
| `VOL_LIQ_RATIO` | score | `trades.volume_over_liquidity` | band, lane-dependent | UNKNOWN_OK | too low = dead, absurdly high = manufactured |
| `UNIQUE_BUYERS_RATIO` | kill\* | `trades.unique_buyers_over_trades` | ≥ 0.15 | UNKNOWN_OK | many trades from few wallets = wash trading |
| `AVG_TRADE_SIZE_SPREAD` | score | `trades.size_distribution` | — | FAIL_OPEN | a flat size histogram is a bot signature |
| `REPEATED_ROUNDTRIPS` | score | `trades.roundtrip_wallets_pct` | ≤ 20 | UNKNOWN_OK | same wallet buy→sell→buy in a loop is volume theatre |
| `LAUNCH_BUNDLE_SHARE` | kill | `launch.bundled_or_single_slot_share_pct` | ≤ 25 | UNKNOWN_OK | bundled/atomic launch buys are how insiders front the market |
| `AGE_MIN` | kill | `age_minutes` | lane-dependent | UNKNOWN_OK | blocks lightning rugs and also blocks "check immediately" tokens |

## F. Deployer integrity

| id | kind | field | default | missing | Why |
|---|---|---|---|---|---|
| `DEV_HOLD_PCT` | kill | `deployer.current_hold_pct` | ≤ 5 | UNKNOWN_OK | deployer holding a large bag is the classic exit |
| `DEV_PRIOR_RUGS` | kill | `deployer.prior_rugged_tokens` | == 0 | UNKNOWN_OK | same wallet, same scam, new ticker |
| `DEV_PRIOR_LAUNCHES` | info | `deployer.prior_launch_count` | — | FAIL_OPEN | serial launcher context; not a verdict on its own |
| `DEV_FUNDING_SOURCE` | score | `deployer.funding_provenance` | — | FAIL_OPEN | funded from a known mixing/shill cluster |
| `DEV_LINKED_TO_ACTIVE_TOKEN` | score | `deployer.overlaps_with_live_tokens` | — | FAIL_OPEN | deployer running several tokens at once splits attention and exit liquidity |

## G. Context & narrative (recorded, weakly scored — never load-bearing)

| id | kind | field | default | missing | Why |
|---|---|---|---|---|---|
| `SOCIAL_PRESENT` | score | `socials.has_official_site_and_social` | + points | FAIL_OPEN | weak, easily faked; keep the weight low |
| `SOCIAL_AGE` | score | `socials.oldest_account_age_days` | ≥ 7 | FAIL_OPEN | account age is the cheapest way to spot a fabricated narrative |
| `PAID_PROMO_SIGNALS` | info | `context.boost_or_paid_listing` | — | FAIL_OPEN | paid boosts are not disqualifying, but the operator should know |
| `LISTING_STATUS` | info | `context.cex_listings` | — | FAIL_OPEN | context for exit routes |

---

## Lane presets (which criteria even run)

A criterion that does not apply to the lane resolves to `n/a`, not to `unknown` —
the two must not be confused in the report.

| Criterion group | `new_launch` | `graduation` | `traction` | `watchlist` |
|---|---|---|---|---|
| A supply & authority | full | full | full | full |
| B transfer semantics | full | full | full | full |
| C distribution | `HOLDERS_MIN` low | normal | growth-weighted | delta only |
| D liquidity & mcap | low floor, `MCAP_MIN` n/a | graduated floor | high floor + `MCAP_MIN` | delta |
| E trade behaviour | bundle + sell route | sell route + flow | **primary** (unique buyers, vol/liq, roundtrips) | delta |
| F deployer | full | full | full | full |
| G context | info only | info only | `HOLDER_GROWTH` + socials | delta |

---

## Maintaining this catalogue

- **A kill criterion that never fires is dead weight.** `rejected_by_criterion` in
  the run summary exists to find these. Either the threshold is too loose for the
  current market, or the source silently returns a default — check the source
  before the threshold.
- **A kill criterion that fires on everything is a broken source**, not a bear
  market. Same check.
- When adding a criterion, add its `missing_policy` in the same edit. A criterion
  without a missing policy *always* fails open under pressure, which is how a
  safety check quietly stops protecting anything.
- Do not add a criterion whose field has no `(field, source)` pair in the adapter.
  Un-sourceable criteria are the failure mode this whole file is designed against.
