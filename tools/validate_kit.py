#!/usr/bin/env python3
"""validate_kit.py — keep the criterion catalogue and the config in sync.

The kit has one structural invariant worth automating:

    every criterion id in reference/criteria.md is either wired in
    config/filters.solana.yaml under `criteria:` or explicitly parked under
    `declared_not_applicable:` — and nothing is wired that the catalogue does not
    define.

Without this check the two files drift silently, and a drifted criterion is worse
than a missing one: it looks like coverage.

Usage:
    python tools/validate_kit.py [--kit-root .]

Exit status: 0 = green, 1 = at least one error.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

KINDS = {"kill", "score", "info"}
POLICIES = {"fail_closed", "fail_open", "unknown_ok"}

# If any of these ever stops being fail_closed, the filter has quietly stopped
# protecting anything — which is exactly the failure this file exists to catch.
SAFETY_CRITICAL = {
    "AUTH_MINT", "AUTH_FREEZE",
    "EXT_TRANSFER_HOOK", "EXT_PERMANENT_DELEGATE", "EXT_NON_TRANSFERABLE",
    "EXT_DEFAULT_FROZEN",
    "SELL_ROUTE", "SELL_IMPACT",
    "LP_PRESENT", "LIQ_USD_MIN", "LP_OWNER_WALLET", "POOL_ONE_SIDED",
    "TOP10_EX_LP",
}

REQUIRED_TOP_KEYS = {"version", "chain", "lanes", "thresholds", "scoring",
                     "verdicts", "criteria", "budget"}


def catalogue_ids(criteria_md: Path) -> set[str]:
    """Criterion ids from the catalogue tables: | `ID` | kind | ... |

    The kind cell may carry a footnote marker: an asterisk, usually escaped with a
    backslash so markdown renders a literal star. Strip the decoration rather than
    making authors remember which escape this parser tolerates.
    """
    ids = set()
    for line in criteria_md.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.split("|")]
        # cells[0] is the empty lead, cells[1] name, cells[2] kind
        if len(cells) < 3:
            continue
        name = re.sub(r"[\\*]+$", "", cells[1])
        kind = re.sub(r"[\\*]+$", "", cells[2]).strip().lower()
        if re.fullmatch(r"[A-Z][A-Z0-9_]+", name) and kind in KINDS:
            ids.add(name)
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit-root", default=None,
                    help="kit root (default: parent dir of this script)")
    args = ap.parse_args()

    root = Path(args.kit_root).resolve() if args.kit_root else Path(__file__).resolve().parent.parent
    errors: list[str] = []
    warnings: list[str] = []

    def rel(p: Path) -> str:
        return str(p.relative_to(root)) if root in p.parents or p == root else str(p)

    # ── 1. config parses and has the required shape ──────────────────────────
    cfg_path = root / "config" / "filters.solana.yaml"
    if not cfg_path.exists():
        print(f"FAIL: missing {rel(cfg_path)}")
        return 1
    try:
        import yaml
    except ImportError:
        print("FAIL: PyYAML is required (pip install pyyaml)")
        return 1
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    print(f"[config] parsed {rel(cfg_path)}")
    missing_keys = sorted(REQUIRED_TOP_KEYS - set(cfg or {}))
    if missing_keys:
        errors.append(f"config missing top-level keys: {missing_keys}")
    if not cfg or "criteria" not in cfg:
        print("\n".join(f"ERROR: {e}" for e in errors) or "FAIL: unusable config")
        return 1

    cfg_ids = set(cfg["criteria"])
    parked = {d["id"] for d in cfg.get("declared_not_applicable", []) or []}
    print(f"[config] criteria wired={len(cfg_ids)} parked={sorted(parked)}")

    # ── 2. catalogue ↔ config, both directions ───────────────────────────────
    cat_ids = catalogue_ids(root / "reference" / "criteria.md")
    print(f"[catalogue] criteria defined={len(cat_ids)}")
    unwired = sorted(cat_ids - cfg_ids - parked)
    undefined = sorted(cfg_ids - cat_ids)
    if unwired:
        errors.append("defined in criteria.md but neither wired nor parked in config: "
                      + ", ".join(unwired))
    if undefined:
        errors.append("wired in config but not defined in criteria.md: "
                      + ", ".join(undefined))
    if parked - cat_ids:
        warnings.append("parked ids that the catalogue does not define: "
                        + ", ".join(sorted(parked - cat_ids)))

    # ── 3. every wired criterion declares kind + missing_policy ──────────────
    for cid, spec in cfg["criteria"].items():
        if not isinstance(spec, dict):
            errors.append(f"{cid}: spec is not a mapping")
            continue
        if spec.get("kind") not in KINDS:
            errors.append(f"{cid}: kind must be one of {sorted(KINDS)}")
        if spec.get("missing_policy") not in POLICIES:
            errors.append(f"{cid}: missing_policy must be one of {sorted(POLICIES)}")

    # ── 4. safety-critical criteria must fail closed ─────────────────────────
    for cid in sorted(SAFETY_CRITICAL):
        spec = cfg["criteria"].get(cid)
        if spec is None:
            errors.append(f"safety-critical criterion {cid} is not wired")
        elif spec.get("missing_policy") != "fail_closed":
            errors.append(f"safety-critical criterion {cid} is not fail_closed "
                          f"(got {spec.get('missing_policy')})")

    kills = [c for c, s in cfg["criteria"].items() if s.get("kind") == "kill"]
    kill_open = sorted(set(kills) - {c for c, s in cfg["criteria"].items()
                                     if s.get("missing_policy") == "fail_closed"})
    if kill_open:
        warnings.append("kill criteria that are not fail_closed (by design for "
                        "data-scarce signals, verify each): " + ", ".join(kill_open))

    # ── 5. lane overrides must reference real thresholds ─────────────────────
    known_thr = set(cfg.get("thresholds", {}))
    for lane, spec in (cfg.get("lanes") or {}).items():
        for key in (spec or {}).get("kill_overrides", {}) or {}:
            if key not in known_thr:
                errors.append(f"lane {lane}: kill_overrides key {key!r} is not in thresholds")

    # ── 6. relative markdown links resolve ───────────────────────────────────
    broken = []
    for md in root.rglob("*.md"):
        for m in re.finditer(r"\]\(([^)#]+)(?:#[^)]*)?\)", md.read_text(encoding="utf-8")):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (md.parent / target).exists():
                broken.append(f"{rel(md)} -> {target}")
    if broken:
        errors.append("broken relative links: " + "; ".join(broken))

    # ── report ───────────────────────────────────────────────────────────────
    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print()
    if errors:
        print(f"RESULT: FAIL ({len(errors)} error(s))")
        return 1
    print(f"RESULT: OK — {len(cfg_ids)} criteria wired, {len(cat_ids)} defined, "
          f"{len(kills)} kills, {len(cfg.get('lanes') or {})} lanes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
