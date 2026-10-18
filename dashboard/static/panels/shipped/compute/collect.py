"""The Compute panel's collector — GPU-hours, jobs and time, for the whole lab and per study.

Shipped with the lab (so it needs no approval). Reads, never writes:
  * every project's runs/*/meta.json (stage, status, started/finished, budget.max_minutes, scheduler job)
  * nvidia-smi on this machine, when there is one (GPUs, utilisation, memory, processes per GPU)
  * Slurm, when lab/config.yaml compute.scheduler.kind is slurm: squeue (your jobs now) and sacct (30 days)
Budgets are instructions, not limits: lab/config.yaml `compute.gpu_hours_budget` (the lab) and a project's
control.yaml `budgets.gpu_hours` (one study). Crossing one raises an alert (a study's may hold its launches,
if the PI lets this panel do that). Prints one JSON object.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

HUB = Path(os.environ.get("NEWTS_HUB") or ".").resolve()
PROJECTS = Path(os.environ.get("NEWTS_PROJECTS") or HUB.parent)
CFG = json.loads(os.environ.get("NEWTS_CONFIG") or "{}")
NOW = time.time()


def _ts(s) -> float | None:
    try:
        return time.mktime(time.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return None


def _yaml_num(text: str, block: str, key: str) -> float | None:
    """A number under `block:` → `key:` in a small YAML file (no pyyaml in an isolated collector)."""
    m = re.search(rf"^{block}:\s*\n((?:[ \t]+.*\n?)*)", text, re.M)
    if not m:
        return None
    k = re.search(rf"^[ \t]+{key}:\s*([0-9.]+)", m.group(1), re.M)
    return float(k.group(1)) if k else None


def _run(argv, timeout=20) -> str:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def registry() -> dict[str, Path]:
    """{study: project dir} from lab/REGISTRY.md (its Project column), else projects/<study>."""
    out = {}
    try:
        lines = (HUB / "lab" / "REGISTRY.md").read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        lines = []
    for ln in lines:
        cells = [c.strip().strip("`") for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.match(r"^[A-Za-z0-9][\w.-]*$", cells[0]) and cells[0] not in ("id", "slug"):
            p = Path(cells[4]) if cells[4] and cells[4] not in ("-", "—") else PROJECTS / cells[0]
            if not p.is_absolute():
                p = (HUB / p).resolve()
            if p.is_dir():
                out[cells[0]] = p
    return out


def gpus_per_run(has_gpu: bool) -> float:
    sc = ((CFG.get("compute") or {}).get("scheduler") or {})
    slurm = sc.get("slurm") or {}
    if sc.get("kind") == "slurm" and slurm.get("gpus_per_run"):
        return float(slurm["gpus_per_run"])
    return 1.0 if has_gpu else 0.0


def nvidia() -> list[dict]:
    if not shutil.which("nvidia-smi"):
        return []
    rows = _run(["nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,uuid",
                 "--format=csv,noheader,nounits"])
    procs = _run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader,nounits"])
    per: dict[str, int] = {}
    for ln in procs.splitlines():
        u = ln.split(",")[0].strip()
        if u:
            per[u] = per.get(u, 0) + 1
    out = []
    for ln in rows.splitlines():
        c = [x.strip() for x in ln.split(",")]
        if len(c) >= 6:
            out.append({"index": c[0], "name": c[1], "util": _f(c[2]), "mem_used": _f(c[3]), "mem_total": _f(c[4]),
                        "procs": per.get(c[5], 0)})
    return out


def _f(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def slurm() -> dict:
    sc = ((CFG.get("compute") or {}).get("scheduler") or {})
    if sc.get("kind") != "slurm" or not shutil.which("squeue"):
        return {}
    user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
    jobs = []
    for ln in _run(["squeue", "-h", "-u", user, "-o", "%i|%j|%T|%M|%l|%b"]).splitlines():
        c = ln.split("|")
        if len(c) >= 4:
            jobs.append({"job": c[0], "name": c[1], "state": c[2].lower(), "elapsed": c[3], "limit": c[4] if len(c) > 4 else ""})
    hours = 0.0
    for ln in _run(["sacct", "-u", user, "-S", "now-30days", "-X", "-n", "-P", "-o", "JobID,ElapsedRaw,AllocTRES"], 40).splitlines():
        c = ln.split("|")
        if len(c) >= 3:
            g = re.search(r"gres/gpu=(\d+)", c[2])
            if g and c[1].isdigit():
                hours += int(g.group(1)) * int(c[1]) / 3600
    return {"jobs": jobs, "gpu_hours_30d": round(hours, 1),
            "running": sum(1 for j in jobs if j["state"] == "running"),
            "queued": sum(1 for j in jobs if j["state"] in ("pending", "configuring"))}


def main() -> None:
    gpus = nvidia()
    per_run_gpus = gpus_per_run(bool(gpus) or bool(((CFG.get("compute") or {}).get("scheduler") or {}).get("kind") == "slurm"))
    studies, running, alerts = [], [], []
    days: dict[str, float] = {}
    total = 0.0
    for slug, pdir in sorted(registry().items()):
        try:
            ctl = (pdir / "control.yaml").read_text(encoding="utf-8-sig")
        except OSError:
            ctl = ""
        budget = _yaml_num(ctl, "budgets", "gpu_hours")
        used, n_run, n_q = 0.0, 0, 0
        for meta in (pdir / "runs").glob("*/meta.json") if (pdir / "runs").is_dir() else []:
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            st = str(m.get("status") or "")
            t0 = _ts(m.get("started"))
            wall = float(m.get("wall_seconds") or 0) or ((NOW - t0) if st == "running" and t0 else 0)
            g = per_run_gpus if str(m.get("stage") or "").upper() in ("PILOT", "FULL") or st == "running" else 0
            h = wall / 3600 * g
            used += h
            if t0:
                day = time.strftime("%Y-%m-%d", time.localtime(t0))
                days[day] = days.get(day, 0.0) + h
            if st == "running":
                n_run += 1
                exp = (m.get("budget") or {}).get("max_minutes")
                hrs = wall / 3600
                over = bool(exp) and hrs * 60 > float(exp) * 1.25
                running.append({"run_id": m.get("run_id") or meta.parent.name, "study": slug, "stage": m.get("stage"),
                                "hours": round(hrs, 2), "expected_h": round(float(exp) / 60, 2) if exp else None, "over": over})
                if over:
                    alerts.append({"level": "warn", "study": slug,
                                   "say": f"{m.get('run_id') or meta.parent.name} has run {hrs:.1f} h, past its expected {float(exp) / 60:.1f} h"})
            elif st == "queued":
                n_q += 1
        total += used
        studies.append({"study": slug, "gpu_hours": round(used, 1), "budget": budget, "running": n_run, "queued": n_q})
        if budget and used > budget:
            alerts.append({"level": "block", "study": slug, "hold": True,
                           "say": f"{slug} is over its GPU budget ({used:.0f} of {budget:.0f} GPU-hours)"})
    lab_budget = _f((CFG.get("compute") or {}).get("gpu_hours_budget"))
    if lab_budget and total > lab_budget:
        alerts.append({"level": "block", "say": f"The lab is over its GPU budget ({total:.0f} of {lab_budget:.0f} GPU-hours)"})
    cap = int((CFG.get("compute") or {}).get("max_concurrent_runs") or 0)
    heavy = [r for r in running if str(r.get("stage") or "").upper() in ("PILOT", "FULL")]
    if cap and len(heavy) > cap:
        alerts.append({"level": "warn", "say": f"{len(heavy)} training runs at once — the lab's share is {cap}"})
    if len(running) >= 2:   # (a desktop's own apps show up as GPU processes too: only the lab's runs count)
        for g in gpus:
            if (g.get("procs") or 0) > 1 and (g.get("util") or 0) > 50:
                alerts.append({"level": "warn", "say": f"GPU {g['index']} is busy with several runs at once — "
                                                       f"{len(running)} lab runs are going"})
    sl = slurm()
    series = [{"day": d, "gpu_hours": round(v, 2)} for d, v in sorted(days.items())[-21:]]
    used_label = f"{total:.0f}" + (f" of {lab_budget:.0f}" if lab_budget else "")
    print(json.dumps({
        "gpu_hours": round(total, 1), "gpu_hours_budget": lab_budget, "studies": studies, "running": running,
        "runs_running": len(running), "jobs": sl.get("jobs") or [], "jobs_running": sl.get("running", len(running)),
        "jobs_queued": sl.get("queued", sum(s["queued"] for s in studies)), "slurm": bool(sl), "gpus": gpus,
        "series": series, "max_concurrent": cap, "alerts": alerts,
        "gauge": {"value": total, "max": lab_budget, "label": "GPU-h", "tone": "bad" if lab_budget and total > lab_budget else ""},
        "summary": f"{used_label} GPU-hours · {len(running)} running" + (f" · {sl.get('queued')} queued" if sl.get("queued") else ""),
    }))


if __name__ == "__main__":
    main()
