"""Audit spec conformance: what was run is what the frozen plan said, or the difference is disclosed.

    uv run --with pyyaml python checks/audit_spec_conformance.py studies/<slug>/paper

The plan is the project's frozen data and eval blocks: control.yaml `data:` (source, version, sha256,
split_seed) and configs/base.yaml `eval:` (primary_metric, optional benchmark / validation / test). What
ran is each cited run's `runs/<run_id>/config.resolved.yaml` (control.yaml < base.yaml < experiment yaml).
For every run a claim in claims.yaml cites:
  1. Its dataset, split, metric and benchmark must equal the plan's. A difference is a FAIL unless the
     claim carries a one-line `deviation:` (then MANUAL: a human confirms the paper says it too).
  2. A headline claim's `metric:` must be the plan's primary metric (same `deviation:` escape).
  3. A run configured with subsampled or synthetic data is a FAIL unless the claim has a `deviation:` or
     the paper (main.tex) says so; disclosed, it is MANUAL.
A plan that declares no dataset or no primary metric, or a cited run without a resolved config, is MANUAL:
there is nothing to compare against.

Exit: 0 clean · 2 needs human review · 1 a real violation. Wired: a `spec` audit in workflow/rules.yaml,
listed by the checkpoint that lists `eval` and `prereg`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import labfiles  # noqa: E402 — the lab's files, read one way (tools/labfiles.py)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HUB = Path(__file__).resolve().parents[1]
PLAN_KEYS = ("data.source", "data.version", "data.sha256", "data.split_seed",
             "eval.primary_metric", "eval.benchmark", "eval.validation", "eval.test")
# config keys that mean the run did not use the real, full data, and the words a paper uses to own up to it
SUBSTITUTIONS = {
    "synthetic data": (re.compile(r"synthetic", re.I), re.compile(r"synthetic|simulated", re.I)),
    "subsampled data": (re.compile(r"subsampl|subset|max_(samples|rows|examples)|sample_frac", re.I),
                        re.compile(r"subsampl|subset|random sample", re.I)),
}


def _get(tree, dotted: str):
    for key in dotted.split("."):
        tree = tree.get(key) if isinstance(tree, dict) else None
    return tree


def _flatten(tree, prefix: str = ""):
    for key, value in tree.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _flatten(value, path + ".")
        else:
            yield path, value


def _frozen(project: Path) -> dict:
    """The frozen blocks: control.yaml `data` and configs/base.yaml `eval`."""
    return {"data": labfiles.load_yaml(project / "control.yaml").get("data") or {},
            "eval": labfiles.load_yaml(project / "configs" / "base.yaml").get("eval") or {}}


def _substitutions(config: dict) -> set[str]:
    """Which kinds of data substitution a run config asks for (a flag that is on, a source that says so)."""
    found = set()
    for path, value in _flatten(config):
        off = value is None or value is False or value in ("", 0, "full") or value == 1.0 and isinstance(value, float)
        for kind, (key_re, _) in SUBSTITUTIONS.items():
            if (key_re.search(path.rsplit(".", 1)[-1]) and not off) or (
                    path == "data.source" and isinstance(value, str) and key_re.search(value)):
                found.add(kind)
    return found


def _runs(claim: dict) -> list[str]:
    return sorted({m.group(1) for rel in claim.get("artifacts") or []
                   if (m := re.match(r"runs/([^/]+)/", str(rel).replace("\\", "/")))})


def audit(paper_dir: Path) -> int:
    slug = paper_dir.parent.name
    have_fail = have_manual = False
    print(f"## Spec-conformance audit — studies/{slug}\n")

    project = labfiles.project_dir(HUB, slug)
    if not project:
        print("- plan: no project found (MANUAL).\n")
        return 2
    frozen = _frozen(project)
    plan = {k: v for k in PLAN_KEYS if (v := _get(frozen, k)) not in (None, "")}
    planned = _substitutions(frozen)    # data the plan itself says is synthetic or subsampled is not a substitution
    absent = [name for name, declared in (("dataset (control.yaml data:)", any(k.startswith("data.") for k in plan)),
                                          ("primary metric (configs/base.yaml eval.primary_metric)", "eval.primary_metric" in plan))
              if not declared]
    if absent:
        print(f"- plan: MANUAL — the frozen plan does not declare: {'; '.join(absent)}; nothing to compare runs against there.")
        have_manual = True

    claims = [c for c in (labfiles.load_yaml(paper_dir / "claims.yaml").get("claims") or []) if isinstance(c, dict)]
    claims = [c for c in claims if _runs(c)]
    tex = paper_dir / "main.tex"
    text = tex.read_text(encoding="utf-8-sig", errors="replace") if tex.exists() else ""
    unchecked = set()
    for claim in claims:
        cid, deviation = claim.get("id"), str(claim.get("deviation") or "").strip()
        findings = []   # (what differs, whether the paper owns up to it without a `deviation:`)
        if claim.get("headline") and claim.get("metric") and "eval.primary_metric" in plan \
                and str(claim["metric"]) != str(plan["eval.primary_metric"]):
            findings.append((f"headline metric {claim['metric']!r}, planned {plan['eval.primary_metric']!r}", False))
        for rid in _runs(claim):
            config = labfiles.load_yaml(project / "runs" / rid / "config.resolved.yaml")
            if not config:
                unchecked.add(rid)
                continue
            findings += [(f"run {rid}: {key} is {_get(config, key)!r}, planned {plan[key]!r}", False)
                         for key in plan if _get(config, key) != plan[key]]
            findings += [(f"run {rid} used {kind}", bool(SUBSTITUTIONS[kind][1].search(text)))
                         for kind in sorted(_substitutions(config) - planned)]
        if not findings:
            continue
        undisclosed = [what for what, in_paper in findings if not (deviation or in_paper)]
        if undisclosed:
            print(f"- claim {cid}: **FAIL** — undisclosed: {'; '.join(undisclosed)} "
                  "(add a one-line `deviation:` to the claim and say it in the paper).")
            have_fail = True
        else:
            print(f"- claim {cid}: MANUAL — disclosed ({deviation or 'in the paper'}); confirm the paper says it: "
                  f"{'; '.join(what for what, _ in findings)}.")
            have_manual = True
    if unchecked:
        print(f"- runs: MANUAL — no runs/<id>/config.resolved.yaml for {', '.join(sorted(unchecked)[:8])}; can't compare them to the plan.")
        have_manual = True
    if not claims:
        print("- claims: none cite a run artifact — MANUAL (nothing to compare against the plan).")
        have_manual = True
    elif not (have_fail or have_manual):
        print(f"- {len(claims)} claim(s): the runs behind them match the frozen plan, with no undisclosed substitution ✓")
    print()
    return 1 if have_fail else (2 if have_manual else 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paper_dir", help="e.g. studies/<slug>/paper")
    a = ap.parse_args()
    paper_dir = (HUB / a.paper_dir) if not Path(a.paper_dir).is_absolute() else Path(a.paper_dir)
    return audit(paper_dir)


if __name__ == "__main__":
    sys.exit(main())
