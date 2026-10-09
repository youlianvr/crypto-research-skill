# sources — where every field comes from

This file completes the rule that makes the skill grounded: **criterion → field →
source**. If a field is not in this table, no criterion may depend on it.

> **Evidence labels used below** — keep them honest when you edit this file:
> - `CORE` — the chain's own RPC. Ground truth by construction.
> - `API` — a documented third-party data service.
> - `CATALOG` — an entry in a local MCP catalog snapshot (**2026-10-01**,
>   ~7 960 names harvested from public "awesome-mcp" lists). The description is a
>   **third-party claim that has not been probed**. Nothing here is a statement that
>   a server exists, works, or is safe.
> - `LEAD` — a name seen in a public Telegram crypto channel (promotional forwarded
>   posts). It proves **only that the name is used in this market**, not that the tool
>   works, is safe, or is worth paying for. §7.

---

## 1. Field → source map

| Field group | Primary | Fallback | Notes |
|---|---|---|---|
| authority / extensions / supply (`AUTH_*`, `EXT_*`, `SUPPLY_ANOMALY`) | `CORE` RPC mint read | indexer asset endpoint | never take these from a cached aggregator field |
| holders distribution | risk/indexer API that excludes pools | `CORE` RPC `getTokenLargestAccounts` + owner resolution | see the pool-exclusion trap in the adapter |
| liquidity / volume / pair age / socials (cheap tier) | DEX aggregator API | indexer | free, no key, good enough for **screening** |
| sellability (`SELL_ROUTE`, `SELL_IMPACT`) | aggregator quote | tx simulation | tier 2 simulation is the strong test |
| trade behaviour (`UNIQUE_BUYERS_RATIO`, roundtrips, bundle) | indexer (transaction-level) | aggregator buy/sell counts only | the cheap fallback cannot see wallets — mark `unknown` rather than approximate |
| deployer identity / history | indexer (mint-creation + tx history) | launchpad creator field | low confidence without an indexer |
| metadata | `CORE` metadata account + off-chain URI | indexer | treat the URI JSON as untrusted input |

**Priority rule:** for a `kill` criterion, prefer the source that gives the field
most directly. Do not reconstruct a kill field from a heuristic when a direct read
exists — a heuristic that is wrong 3% of the time is fine for scoring and fatal for
vetoing.

---

## 2. Chain-native endpoints

| Source | Label | Gives | Needs key | Gotchas |
|---|---|---|---|---|
| Solana RPC (self-hosted / Helius / QuickNode / public) | CORE | mint account, authorities, extensions, supply, token accounts + owners, signatures, `simulateTransaction` | no for public, yes for real throughput | public endpoints rate-limit hard and change shape; never tight-loop them. Pin the network + a fallback RPC. |
| Launchpad program logs (pump.fun / PumpSwap / Raydium LaunchLab and friends) | CORE | new mints, curve progress, graduation/migration events | no | no official public API; prefer program subscription/webhook over historical scans; **the program IDs must be pinned from source** |

## 3. Aggregator and analytics APIs

| Source | Label | Gives | Needs key | Gotchas |
|---|---|---|---|---|
| DexScreener | API | pairs per token, liquidity USD, FDV, volume, buy/sell counts, pair age, socials, trending & new-token feeds, boosts/paid promos | no | free tier is rate-limited; endpoint paths change — verify against live docs and pin. Counts are transaction counts, **not unique wallets**. |
| Jupiter | API | sell/buy quotes and routes, token list with tags | no (rate-limited) | the route it returns is a strong sellability signal; pair it with an on-chain simulation |
| Birdeye | API | holders, top traders, trader counts, security, OHLCV | yes | credit-metered; the holder endpoint is one of the better pool-excluding sources |
| Helius | API | DAS asset reads (authorities, metadata, extensions), enhanced/parsed transactions, webhooks | yes | the practical way to get T2 behaviour data; webhooks beat polling for launches |
| RugCheck-style risk API | API | composite risk score, top holders, insider clusters, authority summary | usually free/limited | a score is a summary of someone else's checks — keep the underlying fields, do not store the score as if it were a fact |
| GoPlus-style token security API | API | token/security flags | free tier | verify it actually covers Solana mints before you rely on it |
| Vybe | API | Solana token/market data | yes | reached via the `solana-mcp-vybe` entry below |
| Block explorers (Solscan / SolanaFM / explorer) | API | human verification, links in reports | varies | a research aid, not a data feed |

## 4. MCP servers worth evaluating (`CATALOG` — unprobed claims)

Grouped by what they would be used for. All are entries in the catalog snapshot
of 2026-10-01; **none was installed or called while writing this file.**

**Read-only, research-shaped — evaluate first:**

| Entry | Claimed capability |
|---|---|
| `janswist/mcp-dexscreener` | real-time on-chain market prices via the DexScreener API |
| `kukapay/dexscreener-trending-mcp` | trending tokens from DexScreener |
| `kukapay/dex-pools-mcp` | DEX pool data |
| `kukapay/crypto-trending-mcp`, `kukapay/crypto-sentiment-mcp`, `kukapay/crypto-indicators-mcp`, `kukapay/crypto-liquidations-mcp`, `kukapay/crypto-news-mcp`, `kukapay/cryptopanic-mcp-server` | trending / sentiment / indicators / liquidations / news |
| `kukapay/crypto-projects-mcp`, `kukapay/crypto-whitepapers-mcp`, `kukapay/crypto-rss-mcp` | project and narrative context (T3) |
| `kukapay/defi-yields-mcp`, `kukapay/crypto-pegmon-mcp`, `kukapay/crypto-portfolio-mcp`, `kukapay/crypto-stocks-mcp` | adjacent market data |
| `autonsol/sol-mcp` | Solana token risk score (0–100), holder concentration, liquidity, pump.fun graduation momentum |
| `Chronolapse411/sicarius-guard` | byte-level SPL mint analysis, honeypot/freeze/mint-authority checks, Birdeye enrichment |
| `AiAgentKarl/solana-mcp-server` | balances, prices, DeFi yields, token safety (risk score, holder concentration, insider detection) |
| `LamboPoewert/mcp-server-madeonsol` | memecoin intelligence: KOL wallet tracking, deployer scoring, DEX trade firehose |
| `CryptoRugMunch/rug-munch-mcp` | rug detection, honeypot scoring, deployer tracking, KOL-shill detection |
| `Anthropic-community style` `bankless/onchain-mcp`, `mcp-etherscan-server` | EVM on-chain reads |

**Write-capable — keep out of the research route:** `kukapay/pumpswap-mcp`,
`kukapay/raydium-launchlab-mcp`, `kukapay/jupiter-mcp`, `kukapay/token-minter-mcp`,
`kukapay/token-revoke-mcp`, `polsolbridge/solana-swap-api`, `TradeRouter`, wallet
signers, and anything described as executing swaps or launching tokens. Some of these
are genuinely useful **later**, for execution — but a research engineer that can
transact is a research engineer with an unbounded failure mode.

**EVM-side (for when the deal covers those chains):** `calintzy/evmscope`,
`mcpdotdirect/evm-mcp-server`, `JamesANZ/evm-mcp`, `mike`-style honeypot checkers,
plus `tatumio/blockchain-mcp`. The EVM adapter will need its own criterion block
(honeypot/sell simulation, ownership renounce, proxy/admin, blacklist, tax,
max-tx/cooldown, LP lock contract) — do not reuse block B.

**Second pass over the same snapshot (2026-10-09).** A keyword sweep of the catalog
surfaced these additional entries. Same label, same caveat: **names only, nothing
installed or called.** They are listed because they are recognisable — meeting one on
a registry gives you a place to start reading, not a reason to trust it.

| Group | Entries |
|---|---|
| Solana-specific | `wowinter13/solscan-mcp` (explorer), `solana-dev-mcp`, `solana-mcp-vybe`, `araa47/jupiter-mcp`, `armorwallet/armor-crypto-mcp` |
| Multi-chain reads | `wkalidev/multichain-mcp`, `base/base-mcp`, `bankless/onchain-mcp`, `alchemy/alchemy-mcp-server`, `Thirdweb` |
| Risk / intelligence | `ahnlabio/bicscan-mcp` (address & token risk), `szhygulin/recon-crypto-mcp`, `0xDegenMo/lighter-mcp`, `andresdefi/zerodust`, `bakyang2/kr-crypto-intelligence`, `VENTURE-AI-LABS/cryptodataapi-mcp`, `4dmrkey/cryptopolitan-mcp`, `aaronjmars/web3-research-mcp`, `Token Metrics` |
| Market data (also serves the tokenised-equity lane) | `twelvedata/mcp`, `mcp-yfinance`, `berlinbra/alpha-vantage-mcp`, `anjor/coinmarket-mcp-server`, `binance-mcp-server`, `tickdb-unified-realtime-marketdata-api`, `truetick-gg/mcp`, `tradingview-mcp` |
| Execution-shaped — keep out of the research route | `TradeRouter/trade-router-mcp`, `Trade-Agent/trade-agent-mcp`, `staccDOTsol/staccbot-tg`, `botwallet-co/mcp`, `blockrunai/blockrun-mcp`, `polymarket-paper-trader` |

**A keyword pass is not a curated list.** The sweep matched crypto-ish words, so it
also matched a whole family of LLM *token-budget* tools — `tokensave`, `tokenmeter`,
`TokenBurnRate`, `llm-token-tracker`, `ZeroToken` — none of which belong in this file.
The names above were filtered by hand against §5; keep doing that rather than trusting
a regex.

## 5. Safety rules for anything you install

An MCP server is **code with your agent's privileges**. In this domain the failure
modes are unusually expensive, so treat every entry above as untrusted until vetted:

1. **Never hand a key to a "research" tool.** Deployer keys, wallet keys, or seed
   phrases are out of scope for screening. A source that needs a key needs a
   **read-only API key with a spend/rate cap**, never a signing key.
2. **Read over write.** Write-capable servers (swap, launch, mint, revoke, signer)
   are disabled by default and only enabled for explicit execution work in a
   separate session.
3. **Verify before install:** open the repo, check who publishes it, recent commits,
   what network calls it makes, and whether the README matches the code. Pin a commit;
   never install a floating `latest` into a system that spends money.
4. **Prefer a documented public HTTP API over a stranger's local package.** The same
   DexScreener data is available directly, with fewer moving parts.
5. **x402 / pay-per-call servers spend money on every call.** Many entries in the
   catalog are priced per request; a research run with an unknown spend ceiling is a
   bug. Any paid source must be listed in the run config's budget.
6. **Log the provenance.** Every field the record keeps must name the source that
   produced it. An MCP that returns a risk score without exposing the underlying
   fields is a downgrade compared to reading those fields yourself.

## 6. Source health

A silently-degraded source is the failure this file exists to survive:

- Record `observed_at` per source per run, and surface it.
- If a source has returned the same value for a field across N runs, or returns a
  suspiciously uniform distribution, **suspect the source, not the market** — verify
  one token by hand against the explorer before trusting the feed again.
- When a `kill` source is down, do not fail open. The missing-policy in
  `reference/criteria.md` decides, and the run summary must list the degraded source.

---

## 7. Leads observed in Telegram crypto channels (2026-10-09) — label `LEAD`

Harvested from public Telegram crypto channels — forwarded, promotional posts.
They are **not** covered by the tables above because nobody vetted them; they are
recorded only so the names are recognisable when they reappear.

**These are promotional forwarded posts. They are leads to investigate, never
sources to trust.** Several sit inside a funnel to a paid VIP group.

Trading-bot names used in this market (Solana memecoin tier): `Trojan` (DCA, limit
orders), `Bloom`, `Fasol` (own terminal), `TradeWiz` (copy-trading), `Bullx`
(desktop, described as good for research), `PumpKing Bundler`. Aggregators/indexers
named in the same material overlap the table above: DexScreener, Birdeye
(`bds.birdeye.so`), Helius (`api.helius.xyz/v0/jRPC`, `helius.dev`).

Real-world execution parameter space seen in a leaked `SPL Sniper Bot` `config.env`
writeup — useful as evidence of which knobs exist, not as recommended values:
`BUY_AMOUNT_SOL`, `TAKE_PROFIT`, `STOP_LOSS`, `SLIPPAGE` (**3000 = 30 %**),
`SELL_TIMER_MINUTES`, and a raw `PRIVATE_KEY` in bs58.

> **That last field is the whole argument for this file's §5.1.** A sniper bot needs a
> signing key; a *research* skill must never carry one. Keep the execution parameter
> space visible as domain knowledge and the key permanently outside the research route.

Also noted: an AI-persona memecoin (`JEANPHIL`, Solana) that went $12.2M → $5.9M once
users suspected the influencer was generated — a concrete case for a
**creator/persona verification** criterion rather than only on-chain checks.

---

## 8. Public practitioner references (2026-10-09)

Public, citable sources. Unlike §7 they are not forwarded promo posts — they are
written material with a URL, safe to link from anywhere. They are still
**practitioner material, not ground truth**: they calibrate the *shape* of a check and
supply starting numbers, and none of them proves a field is actually obtainable.

| Reference | What it is good for |
|---|---|
| `https://teletype.in/@cryptoscamm/dexscreener` | a written basic on-chain screening recipe. Filter Gainers/Losers for **≥ 1 month of trading history**, **market cap ≥ $25 000**, and non-zero volume (a decaying volume curve is accumulation, not death). Then open the transaction list, filter buys **> $2 500**, find the outlier buy, open that wallet and check whether it **sells immediately** — the roundtrip speculator. It also lays out the tool tiers: plain scanners (etherscan / bscscan / tonscan), aggregators (DexScreener / DEXTools), deep-analysis (Arkham / Dune / Zerion) |
| LINUX DO thread on a **Jupiter** arbitrage bot (2025-03) | the execution trap behind the sellability test: a dev gets a Jupiter quote, takes Jupiter's `swap-instruction`, **injects a custom priority fee by editing that instruction**, and the transaction then fails on-chain; landing via **Jito** bundling is the separate question they could not answer. Matters the moment you build the sell transaction yourself |
| LINUX DO thread on extracting **bulk Solana history** (2025-07) | the ingestion ceiling: `getSignaturesForAddress` pages 1 000 signatures cheaply, but `getTransaction` per signature is the real bottleneck; free RPC tiers (Helius / Ankr / Shyft) rate-limit **by IP**, so registering extra keys on one IP does not help |

The first row is worth reading closely for two reasons. It corroborates the
`traction` lane's shape (`AGE_MIN`, volume presence, roundtrip wallets) with actual
**numbers**, and it supplies the market-cap floor this catalogue previously lacked —
`MCAP_MIN`, wired in `config/filters.solana.yaml` with `25000` as its starting value.
Its wallet-level "whale" threshold also lands within the same order of magnitude as
the operator's own `position_size_usd`, which is the reasoning already used for
`SELL_IMPACT`: a signal is only meaningful at your own size.
