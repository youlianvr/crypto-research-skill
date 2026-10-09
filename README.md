# crypto-research-skill

A **token research engineer** kit: an agent skill that turns a blockchain's raw launch
firehose into a short, evidenced candidate list, so that nothing scans every token a
chain produces.

Built for Aluma's crypto intelligence project (memecoin / spot / perpetual / stocks /
oracle / AI-token / RWA / DePIN), starting with **Solana**. The engines, pools, RPC and
volume feeds already exist there; this kit is the **research layer** that decides what
deserves the engines' attention.

Status: **design + configuration draft, Solana-first.** No adapter code, no live source
probes, no installed MCP servers. See *Not done yet* below.

---

## The problem this solves

"Scan Solana for new tokens" is not a filter — it is a firehose with a cost attached.
The operator needs to say *what kind of token* is worth scanning, per chain, and have
an agent enforce that definition honestly.

Three ideas carry the whole kit:

1. **Criteria are data with a source.** Every check names the exact on-chain field and
   the exact source it reads. A criterion without a `(field, source)` pair does not
   exist here. This is what makes the skill grounded in chain technology instead of
   folklore.
2. **The pipeline is a graph, not a loop.** Cheap hard kills first, expensive
   verification only on survivors, and exactly two bounded loops: a delta-only
   re-scan of `WATCH` tokens, and a single-hop source escalation. A single big polling
   loop re-pays for the same work every cycle and its cost per candidate grows without
   bound.
3. **`unknown` is a first-class result.** Each criterion declares what happens when its
   data is missing, so a dead source can never silently turn into a pass.

## Layout

| Path | What |
|---|---|
| [`SKILL.md`](SKILL.md) | entry point: hard rules, vocabulary, routing |
| [`reference/pipeline.md`](reference/pipeline.md) | the discovery→verdict graph, cost, rate limits, the two loops |
| [`reference/criteria.md`](reference/criteria.md) | the criterion catalogue: kill vs score, missing policies, lane applicability |
| [`reference/solana-adapter.md`](reference/solana-adapter.md) | Solana grounding: which on-chain field answers what, and the traps |
| [`reference/sources.md`](reference/sources.md) | data sources, the local MCP shortlist, and the safety rules for them |
| [`reference/record-schema.md`](reference/record-schema.md) | the Candidate Record and Verdict contract, plus the anti-hallucination rules |
| [`config/filters.solana.yaml`](config/filters.solana.yaml) | **the operator's file** — lanes, thresholds, weights, verdict floors |
| [`agent/research-engineer.md`](agent/research-engineer.md) | the role prompt that makes an agent this engineer |
| [`tools/validate_kit.py`](tools/validate_kit.py) | checks catalogue ↔ config consistency, safety-critical missing policies, and broken links |

## How to use it

**As an agent skill** — point the agent at `SKILL.md`, and give it
`config/filters.solana.yaml` as the definition it must enforce. The reference files are
read on demand by the routing table, not all at once.

**As a specification for implementation** — the pieces map cleanly onto a small
service: `S1` collectors, `S4` screen, `S5` adapter, `S6/S7` scoring and verdict, `S8`
report. The record schema is the interface between them; build to that and the stages
can be implemented or replaced independently.

**Install elsewhere** — the kit is self-contained: Markdown + YAML plus one optional
Python helper, no absolute paths outside this folder. It can be copied into another
project as-is. The documents need nothing installed; only
[`tools/validate_kit.py`](tools/validate_kit.py) needs `PyYAML`
(`pip install pyyaml`), and the kit still works without running it.

## Before the first run

0. **Run the consistency check.** `python tools/validate_kit.py` — it fails if a
   criterion exists in the catalogue but is neither wired nor parked in the config,
   or if a safety-critical field stopped failing closed. Run it after every edit to
   `config/filters.solana.yaml`; the two files drift silently otherwise, and a drifted
   criterion looks like coverage while providing none.
1. **Calibrate the filter.** Run `traction` once with the defaults and read
   `rejected_by_criterion`. A criterion that never fires is dead weight; one that fires
   on everything means its source is broken. Tune
   [`config/filters.solana.yaml`](config/filters.solana.yaml), not the prose.
2. **Pin the on-chain identifiers.** Fill `config/bridge.yaml` per
   [`reference/solana-adapter.md`](reference/solana-adapter.md) §11 — token programs,
   metadata program, the launchpads and AMMs you accept. Verify each from source; never
   from memory.
3. **Decide the source set.** Minimal viable: own RPC + one DEX aggregator + one
   indexer. Everything else in
   [`reference/sources.md`](reference/sources.md) is optional and should earn its place.

## Not done yet (honest gaps)

- **No adapter code.** Block B (`EXT_*`) and the sellability test are specified, not
  implemented — and they are the highest-value part.
- **No live probe of any source.** The MCP entries in `reference/sources.md` are
  catalog claims from a local hub snapshot (2026-10-01), never installed or called.
  Treat every capability line as unverified until you call it.
- **Defaults are uncalibrated.** The thresholds are conservative starting points for
  memecoin-class lanes, not measured ones. One exception: `MCAP_MIN` carries a starting
  value taken from a public practitioner source rather than invented here — see
  [`reference/sources.md`](reference/sources.md) §8, which also explains how the rest
  of the numbers should eventually be earned.
- **Other chains are stubs.** Base / BSC / Ethereum need their own criterion block
  (honeypot simulation, owner renounce, proxy, blacklist, tax, max-tx, LP lock) — a new
  adapter, not a copy of the Solana numbers.
- **RWA / DePIN / oracle / stocks tokens are out of scope here.** They need a different
  lane family (fundamentals, revenue, TVL, unlocks) with the same contract: sourced
  criteria, deterministic scoring, explicit unknowns.
