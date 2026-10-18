"""The Agent time and spend panel's collector: every executor run's cost (as its backend reported it) and wall
time, by day, by backend and by study. Shipped with the lab. Prints one JSON object."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HUB = Path(os.environ.get("NEWTS_HUB") or ".").resolve()
sys.path.insert(0, str(HUB / "tools"))
CFG = json.loads(os.environ.get("NEWTS_CONFIG") or "{}")


def main() -> None:
    try:
        from executor import Lab, all_runs  # noqa: PLC0415
        runs = [m for *_x, m in all_runs(Lab(HUB))]
    except Exception:  # noqa: BLE001
        runs = []
    days, backends, studies = {}, {}, {}
    week = time.time() - 7 * 86400
    spent_week = minutes_week = 0.0
    n_week = 0
    for m in runs:
        cost = float((m.get("usage") or {}).get("cost_usd") or 0)
        mins = sum(float(a.get("wall_seconds") or 0) for a in (m.get("attempts") or [])) / 60
        day = str(m.get("created") or m.get("started") or "")[:10]
        if day:
            d = days.setdefault(day, {"day": day, "usd": 0.0, "minutes": 0.0, "runs": 0})
            d["usd"] += cost
            d["minutes"] += mins
            d["runs"] += 1
        b = backends.setdefault(m.get("backend") or "claude", {"backend": m.get("backend") or "claude", "usd": 0.0, "minutes": 0.0, "runs": 0})
        b["usd"] += cost
        b["minutes"] += mins
        b["runs"] += 1
        s = studies.setdefault(m.get("subject") or "the lab", {"study": m.get("subject") or "the lab", "usd": 0.0, "minutes": 0.0, "runs": 0})
        s["usd"] += cost
        s["minutes"] += mins
        s["runs"] += 1
        try:
            t = time.mktime(time.strptime(str(m.get("created"))[:19], "%Y-%m-%dT%H:%M:%S"))
        except (TypeError, ValueError):
            t = 0
        if t >= week:
            spent_week += cost
            minutes_week += mins
            n_week += 1
    series = [dict(v, usd=round(v["usd"], 3), minutes=round(v["minutes"], 1)) for _k, v in sorted(days.items())[-21:]]
    cap = float(((CFG.get("agents") or {}).get("programmatic") or {}).get("daily_usd_brake") or 0)
    print(json.dumps({
        "usd_week": round(spent_week, 2), "minutes_week": round(minutes_week), "runs_week": n_week,
        "series": series, "backends": sorted(backends.values(), key=lambda x: -x["usd"]),
        "studies": sorted(studies.values(), key=lambda x: -x["minutes"])[:12],
        "gauge": {"value": spent_week, "max": cap * 7 if cap else None, "label": "$ / week"},
        "summary": f"${spent_week:,.2f} this week · {n_week} runs · {minutes_week / 60:.1f} agent-hours",
    }))


if __name__ == "__main__":
    main()
