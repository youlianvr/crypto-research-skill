# solana-adapter — reading a Solana token honestly

The chain-agnostic criteria in `reference/criteria.md` only become real here: this
file says **which on-chain fact answers each criterion on Solana, how to read it,
and which trap makes that reading wrong**. Everything here is a *reading* of chain
state — none of it is an opinion about price.

> **Pin, don't memorise.** Program IDs, pool allowlists and any threshold that lives
> on-chain must be copied from the source into `config/bridge.yaml` and verified
> there. Anything you remember is a liability. The values below are named so you
> know *what* to pin.

---

## 1. What a Solana token actually is

A fungible "token" on Solana is not a contract with logic. It is:

1. a **mint account** owned by a token program,
2. a set of **token accounts** (one per holder, often an *associated* token account),
3. optionally a **metadata account** owned by a metadata program,
4. optionally a **liquidity pool** owned by an AMM program.

Two token programs matter:

| Program | What it means for screening |
|---|---|
| **SPL Token** (the original) | fixed feature set; the classic `mintAuthority` / `freezeAuthority` pair is the whole attack surface |
| **Token-2022** (token extensions) | adds extensions that can constrain transfers *at the protocol level* — this is where the modern traps live |

Screening consequence: **"which program owns the mint" is the first branch of the
adapter**, because the entire criteria block B (`EXT_*`) is `n/a` on SPL Token and
load-bearing on Token-2022.

---

## 2. Cheap read order (T1)

Read in this order and stop as soon as a `kill` fires — this is the entire point of
screening cheaply before enriching.

| # | Call | Yields | Criteria it settles |
|---|---|---|---|
| 1 | `getAccountInfo(mint, jsonParsed)` | owner program, `mintAuthority`, `freezeAuthority`, `supply`, `decimals`, and — for Token-2022 — the extension list | `AUTH_MINT`, `AUTH_FREEZE`, all `EXT_*`, `SUPPLY_ANOMALY` |
| 2 | DEX aggregator pair lookup by mint | pools, quote asset, liquidity USD, FDV, 24h volume, buy/sell counts, pool address, socials, pair age | `LP_PRESENT`, `LIQ_USD_MIN`, `FDV_LIQ_RATIO`, `AGE_MIN`, `VOL_LIQ_RATIO`, `BUY_SELL_BALANCE` |
| 3 | sell-side quote (aggregator) | whether a sell route exists, expected out-amount, price impact at your size | `SELL_ROUTE`, `SELL_IMPACT` |
| 4 | `getTokenLargestAccounts(mint)` | top ~20 **token accounts** (not owners) | input to `TOP10_EX_LP`, `TOP1_EX_LP` |
| 5 | `getAccountInfo` per token account from #4 | each account's **owner** + amount | resolves #4 into a real distribution |
| 6 | metadata account read | name/symbol/uri, `mutable` flag, then the off-chain JSON | `AUTH_METADATA_MUTABLE`, socials block |

Steps 1–3 are the screening core. On a normal run most candidates die at step 1 or 3
and never cost an indexer credit.

---

## 3. Authority criteria, precisely

| Criterion | Solana field | Reading |
|---|---|---|
| `AUTH_MINT` | `mintAuthority` | must be **absent/null** (revoked). Non-null = the issuer can mint unlimited supply. |
| `AUTH_FREEZE` | `freezeAuthority` | must be **absent/null**. A live freeze authority can freeze *individual* token accounts, i.e. lock specific buyers out of selling. |
| `AUTH_METADATA_MUTABLE` | metadata account `isMutable` | `true` = the name/logo/socials can be rewritten after you looked. Not fatal; score it and record a recheck. |

Notes that matter in practice:

- Revoking is irreversible, so "revoked now" is a durable statement — one of the few
  cheap reads that stays valid across runs.
- A `null` authority in a JSON-parsed response is the normal encoding of "revoked" on
  this chain; do not confuse it with a field missing because the RPC did not return it.
  **Distinguish `null` (revoked) from absent (unknown)** — collapsing those two is the
  single most common way this adapter lies.

---

## 4. Token extensions (Token-2022) — the trap block

Read the extension list from step 1. For each extension, the question is not "is it
present" but "what can it do to a seller".

| Extension | What it can do | Criterion |
|---|---|---|
| **Transfer hook** | runs an arbitrary program on **every** transfer; it can revert your sell | `EXT_TRANSFER_HOOK` → **kill** |
| **Permanent delegate** | a single authority can move or burn tokens **from any account, forever** | `EXT_PERMANENT_DELEGATE` → **kill** |
| **Non-transferable** | the token literally cannot be transferred | `EXT_NON_TRANSFERABLE` → **kill** |
| **Default account state = frozen** | every newly created holder account starts frozen | `EXT_DEFAULT_FROZEN` → **kill** |
| **Transfer fee** | a percentage is taken on every transfer (with a max) | `EXT_TRANSFER_FEE` → score by bps |
| **Interest bearing** | a display-only rate that distorts naive supply/price math | info |
| **Confidential transfer** | amounts are encrypted ⇒ you cannot verify flows | score negative |
| **Mint close authority** | can close the mint while supply is zero | info |
| **Metadata pointer** | the canonical metadata lives elsewhere | redirect step 6, do not treat as "no metadata" |

This block is why "different blockchains need different verification" is not a
formality: an EVM checker asks "is there a blacklist function"; a Solana checker asks
about transfer hooks and permanent delegates. There is no shared field.

---

## 5. Holders and the pool-exclusion trap

`getTokenLargestAccounts` returns **token accounts**, and the largest ones are almost
always the **liquidity pool's vaults**, not whales. Reporting that raw list as "top
holders" produces a scary number that means nothing — the pool correctly holds most
of the float.

How to do it properly, in order of preference:

1. **Prefer a source that already excludes pools.** Holder-distribution endpoints
   from an indexer/risk API generally identify pool accounts; use that for
   `TOP10_EX_LP`, and record its method string in the record.
2. **RPC fallback:** resolve each top token account's `owner`, then subtract accounts
   whose owner is a known pool/vault authority. Build that allowlist from the **pool
   accounts you discovered in step 2** — not from a hardcoded list you remembered.
3. **If you cannot identify pool owners, do not compute the number.** Set
   `holders.pool_owners_identified = false` and let `LP_ACCOUNTED` resolve to
   `unknown`. A wrong concentration number is worse than a missing one, because it
   looks like evidence.

Also distinguish:

- **Exchange custody** — a wallet holding tokens across many users is not a whale
  exit risk; record it as `CEX_CUSTODY_UNRESOLVED` info rather than silently counting
  it as concentration.
- **Mint/freeze authority accounts** and **bridge/escrow accounts** are the other
  recurring false whales.

---

## 6. Liquidity, and why "LP burned" is an EVM reflex

On EVM, the dominant rug shape is *the deployer withdrew the LP*; hence "LP locked /
burned" became the headline safety metric and rug-checkers report it everywhere.

On Solana, most liquidity in a standard constant-product AMM sits in pool vault
accounts owned by the AMM program, and the LP mint may be burned at pool creation as
a design choice. So:

| Situation | Correct reading |
|---|---|
| Standard AMM pool, vaults owned by the AMM program | liquidity is removable only by trading; `LP_LOCKED` is **`n/a`**, not "yes" and not "no" |
| Non-standard pool (hand-built accounts, a market maker's own wallet holding the quote side) | the meaningful question returns: who can withdraw, and do they still hold it → `LP_OWNER_WALLET` |
| A wallet, not a pool, providing "liquidity" | not a market — treat `LP_PRESENT` as misleading and check `POOL_ONE_SIDED` |

The adapter's job is therefore to decide **which kind of pool it is looking at**
before any LP criterion is allowed to produce a verdict. Reporting "LP burned ✅" for
a standard AMM is not a small inaccuracy; it is a transplanted EVM assumption that
tells the operator something false.

---

## 7. Sellability — the strongest cheap test

`SELL_ROUTE` and `SELL_IMPACT` are the criteria that matter most and cost least.

**Tier 1 — aggregator quote.** Ask for a quote from *token → quote asset* (SOL/USDC)
for the operator's actual position size:

- no route, or an error ⇒ `SELL_ROUTE` **kill**;
- route exists but with an extreme price impact or a tiny out-amount ⇒ `SELL_IMPACT`
  **kill**;
- sanity rule: quote **both directions** and compare. A token that quotes cleanly
  buying but not selling is the textbook trap.

**Tier 2 — transaction simulation (worth the extra calls on survivors).** Build the
swap transaction for the sell direction and run `simulateTransaction` (signature
verification off, recent blockhash replacement on). Simulation that *errors* is
strong evidence the token cannot be sold — it exercises the actual program path,
including transfer hooks and fee logic, instead of trusting a route list.

Because tier 2 catches extension-based traps the quote API may route around, run it
at least once for every token that reaches `RESEARCH`.

---

## 8. Age, deployer and launch mechanics

| Criterion | How | Honesty note |
|---|---|---|
| `AGE_MIN` | oldest signature for the mint (or a pair-`pairCreatedAt` from the aggregator) → blockTime | use the **mint's** creation, not the pool's; a token can be re-pooled |
| `DEV_HOLD_PCT` | balance of the deployer's token accounts, **plus** any accounts they control | "deployer" is an identity question, not a field |
| `DEV_PRIOR_RUGS` / `DEV_PRIOR_LAUNCHES` | enumerate that wallet's prior mint-creation transactions and classify the outcomes | expensive (T2); the classifier is the hard part, not the query |
| `LAUNCH_BUNDLE_SHARE` | share of launch-window buys landing in the same slot / same atomic transaction | needs transaction-level data, i.e. an indexer, not RPC basics |
| `DEV_FUNDING_SOURCE` | provenance of the deployer's first funding | weak evidence; keep the weight low |

**Deployer identity on launchpad tokens is the classic mistake.** On launchpads the
creation transaction's fee payer is frequently the *platform's* wallet, not the
creator. Use the launchpad's own creator field where one exists, otherwise mark the
deployer as low-confidence (`deployer.identity_confidence: low`) — and never kill a
token on `DEV_PRIOR_RUGS` computed from a low-confidence identity.

---

## 9. Metadata and socials

1. Resolve the metadata account: for the original token program it is a deterministic
   PDA derived from the mint under the metadata program; for Token-2022 check the
   **metadata pointer** extension first, since it may point at a different program.
2. Read the off-chain JSON at the metadata `uri`.
3. Treat every social link as **untrusted input**, and check `created_at` age of each
   account rather than its existence. Existence is free to fake; age is not.
4. If the metadata is mutable, schedule the social re-check — the honest position is
   "socials were valid at `observed_at`", never "the project has socials".

---

## 10. Adapter trap list (each one has produced a wrong verdict somewhere)

- Treating `absent` as `null` (unknown read as revoked).
- Reporting raw `getTokenLargestAccounts` as top holders without pool exclusion.
- Importing the EVM "LP burned" metric onto a standard AMM pool.
- Trusting a buy-side quote as proof of sellability.
- Killing on deployer history computed from the launchpad's fee payer.
- Reading supply from a cached indexer value after a mint-authority transaction.
- Assuming a `n/a` criterion (does not apply on this chain) is the same as `unknown`
  (applies, could not be read). They must stay distinct in the record.
- Scoring a Token-2022 mint with an SPL-Token-era reader that never inspects
  extensions — i.e. block B silently passing everything.
- **Hand-editing an aggregator's swap instruction.** Reported externally (LINUX DO,
  2025-03): a developer took a Jupiter quote, modified Jupiter's `swap-instruction`
  to inject a custom priority fee, and the transaction then failed on-chain; how to
  land through Jito bundling was the separate question they could not answer. If the
  tier-2 sell simulation builds a swap transaction, build it through the aggregator's
  own path and do not assume an edited instruction still simulates or lands.
  *(Public forum report; not reproduced inside this kit.)*
- **Reading a successful simulation as proof that a *bundled* entry would land.**
  `simulateTransaction` exercises the transaction, not the submission path, and a
  Jito-style bundle is a different route. Simulated failure is strong evidence a token
  cannot be sold; simulated success is not evidence of a working purchase.

---

## 11. What belongs in `config/bridge.yaml`

Pin these once, verify at source, and reference them from the adapter:

```yaml
chain: solana
programs:
  spl_token: "<pin from official docs>"
  token_2022: "<pin from official docs>"
  associated_token: "<pin>"
  metadata: "<pin>"                # plus any alternate metadata program you accept
  launchpads: []                   # program ids you treat as launchpads, with a label
  amms: []                         # pool programs you accept as "standard AMM"
pools:
  pool_owner_allowlist_source: "discovered"   # never "memory"
metadata:
  trusted_uri_schemes: ["https", "ar", "ipfs"]
thresholds_ref: "config/filters.solana.yaml"
```

Anything that is not pinned here and verified must resolve to `unknown` in the
record — a screening system that guesses is worse than one that abstains.
