#!/usr/bin/env python3
"""SaaS migration planner engine. Stdlib only.

Usage:
  plan.py --pack idp --template                      print CSV header, valid types
  plan.py inventory.csv --pack idp --source entra --target okta \
          [--start YYYY-MM-DD] [--wave-size 8] [--wave-weeks 2] \
          [--freeze YYYY-MM-DD:YYYY-MM-DD ...] [--out plan.json]

Inventory CSV columns:
  name,type,owner,users,criticality,depends_on,target_support,fixed_date,notes
  type            must be a type key from the pack (see --template)
  criticality     1-5 (5 = outage stops the business)
  depends_on      names separated by ';' (these must migrate first or with this item)
  target_support  native | custom | none | unknown
  fixed_date      free text if tied to a dated process (payroll, close, enrollment)
"""
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

PACK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "packs")
SUPPORT = {"native": 0, "custom": 10, "unknown": 15, "none": 20}
EFFORT_MULT = {"native": 1.0, "custom": 1.5, "unknown": 1.25, "none": 2.0}
LEVELS = [(75, "Critical"), (55, "High"), (35, "Medium"), (0, "Low")]


def arg(name, default=None, multi=False):
    vals = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name and i + 1 < len(sys.argv)]
    if multi:
        return vals
    return vals[0] if vals else default


def load_pack(pid):
    p = os.path.join(PACK_DIR, f"{pid}.json")
    if not os.path.exists(p):
        have = sorted(f[:-5] for f in os.listdir(PACK_DIR) if f.endswith(".json"))
        sys.exit(f"error: unknown pack '{pid}'. Available: {', '.join(have)}")
    return json.load(open(p))


def read_inventory(path, pack):
    errors, items = [], []
    with open(path, newline="") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            name = row.get("name", "")
            if not name:
                errors.append(f"row {n}: missing name")
                continue
            t = row.get("type", "")
            if t not in pack["types"]:
                errors.append(f"row {n} ({name}): unknown type '{t}'")
                continue
            try:
                crit = int(row.get("criticality") or 3)
                assert 1 <= crit <= 5
            except Exception:
                errors.append(f"row {n} ({name}): criticality must be 1-5")
                continue
            try:
                users = int(float(row.get("users") or 0))
            except ValueError:
                errors.append(f"row {n} ({name}): users must be a number")
                continue
            sup = (row.get("target_support") or "unknown").lower()
            if sup not in SUPPORT:
                errors.append(f"row {n} ({name}): target_support must be one of {list(SUPPORT)}")
                continue
            items.append({
                "name": name, "type": t, "owner": row.get("owner", ""), "users": users,
                "criticality": crit, "target_support": sup, "fixed_date": row.get("fixed_date", ""),
                "notes": row.get("notes", ""),
                "depends_on": [d.strip() for d in row.get("depends_on", "").split(";") if d.strip()],
            })
    names = {i["name"] for i in items}
    if len(names) != len(items):
        errors.append("duplicate item names in inventory")
    for i in items:
        for d in i["depends_on"]:
            if d not in names:
                errors.append(f"{i['name']}: depends_on '{d}' is not in the inventory (ignored)")
        i["depends_on"] = [d for d in i["depends_on"] if d in names]
    return items, errors


def score(items, pack):
    fan_in = Counter(d for i in items for d in i["depends_on"])
    for i in items:
        t = pack["types"][i["type"]]
        drivers = []
        base = t["base_risk"]
        crit = i["criticality"] * 5
        users = min(12, round(3 * math.log10(i["users"] + 1)))
        sup = SUPPORT[i["target_support"]]
        date_pts = 10 if i["fixed_date"] else 0
        fan = min(8, 2 * fan_in[i["name"]])
        i["risk"] = min(100, base + crit + users + sup + date_pts + fan)
        i["level"] = next(l for th, l in LEVELS if i["risk"] >= th)
        if base >= 20:
            drivers.append(f"high-risk integration type ({t['label']})")
        if i["criticality"] >= 4:
            drivers.append(f"business criticality {i['criticality']}/5")
        if users >= 9:
            drivers.append(f"{i['users']:,} affected users")
        if i["target_support"] in ("none", "custom", "unknown"):
            drivers.append(f"target support: {i['target_support']}")
        if i["fixed_date"]:
            drivers.append(f"dated constraint: {i['fixed_date']}")
        if fan_in[i["name"]]:
            drivers.append(f"{fan_in[i['name']]} item(s) depend on it")
        i["drivers"] = drivers
        i["dependents"] = fan_in[i["name"]]
        i["effort_days"] = round(t["effort_days"] * EFFORT_MULT[i["target_support"]], 1)
        i["checks"] = t["checks"]
        i["type_label"] = t["label"]
        i["sequence"] = t["sequence"]


def levels(items):
    """Topological level per item. Returns cycles found (names)."""
    by = {i["name"]: i for i in items}
    state, lvl, cyc = {}, {}, set()

    def visit(n, stack):
        if n in lvl:
            return lvl[n]
        if state.get(n) == 1:
            cyc.update(stack[stack.index(n):])
            return 0
        state[n] = 1
        d = 0
        for dep in by[n]["depends_on"]:
            d = max(d, visit(dep, stack + [n]) + 1)
        state[n] = 2
        lvl[n] = d
        return d

    for n in by:
        visit(n, [])
    for n in by:
        by[n]["dep_level"] = lvl[n]
    return sorted(cyc)


def parse_freezes(raw):
    out = []
    for r in raw:
        a, b = r.split(":")
        out.append((datetime.strptime(a, "%Y-%m-%d").date(), datetime.strptime(b, "%Y-%m-%d").date()))
    return out


def next_monday(d):
    return d + timedelta(days=(7 - d.weekday()) % 7 or 7)


def quarter_ok(cutover):
    """True when the cutover falls in the first three weeks of a calendar quarter."""
    q_start = date(cutover.year, 3 * ((cutover.month - 1) // 3) + 1, 1)
    return 0 <= (cutover - q_start).days <= 20


def overlaps(s, e, freezes):
    for fs, fe in freezes:
        if s <= fe and e >= fs:
            return fe
    return None


def build_waves(items, pack, size, weeks, start, freezes):
    blocked = [i for i in items if i["target_support"] == "none"]
    ready = [i for i in items if i["target_support"] != "none"]
    blocked_names = {b["name"] for b in blocked}
    deferred = [i for i in ready if any(d in blocked_names for d in i["depends_on"])]
    for i in deferred:
        i["deferred_reason"] = "depends on an item with no target support"
    ready = [i for i in ready if i not in deferred]

    ready.sort(key=lambda i: (i["dep_level"], i["sequence"], i["risk"]))
    pilot_n = max(3, min(size, math.ceil(len(ready) * 0.1)))
    zero_dep = [i for i in ready if not i["depends_on"]]
    pilot = sorted(zero_dep, key=lambda i: (i["risk"], i["sequence"]))[:pilot_n]
    pilot_set = {i["name"] for i in pilot}
    rest = [i for i in ready if i["name"] not in pilot_set]

    chunks = [("Pilot", pilot)] if pilot else []
    for k in range(0, len(rest), size):
        chunks.append((None, rest[k:k + size]))

    waves, cursor = [], start
    for idx, (label, members) in enumerate(chunks, start=1):
        members.sort(key=lambda i: (i["dep_level"], i["sequence"], i["risk"]))
        s = cursor
        shifted = None
        anchored = [m["name"] for m in members if pack["types"][m["type"]].get("anchor") == "quarter_start"]
        anchor_shift = False
        while True:
            e = s + timedelta(days=weeks * 7 - 1)
            cut = s + timedelta(days=(weeks - 1) * 7 + 1)
            fe = overlaps(s, e, freezes)
            if fe:
                shifted = fe
                nxt = fe + timedelta(days=1)
                s = nxt if nxt.weekday() == 0 else next_monday(nxt)
            elif anchored and not quarter_ok(cut):
                s += timedelta(days=7)
                anchor_shift = True
            else:
                break
        cutover = s + timedelta(days=(weeks - 1) * 7 + 1)
        e = s + timedelta(days=weeks * 7 - 1)
        cursor = e + timedelta(days=1)
        peak = max((m["risk"] for m in members), default=0)
        for m in members:
            m["wave"] = idx
        highs = [m["name"] for m in members if m["level"] in ("High", "Critical")]
        waves.append({
            "number": idx,
            "label": label or ("Final wave" if idx == len(chunks) else f"Wave {idx}"),
            "start": s.isoformat(), "end": e.isoformat(), "cutover": cutover.isoformat(),
            "hypercare_until": (cutover + timedelta(days=7)).isoformat(),
            "shifted_for_freeze": bool(shifted),
            "shifted_for_anchor": anchor_shift,
            "anchored": anchored,
            "items": [m["name"] for m in members],
            "effort_days": round(sum(m["effort_days"] for m in members), 1),
            "peak_risk": peak,
            "gating": [f"Owner sign-off and parallel/shadow run for {n}" for n in highs],
            "comms": [
                {"when": (cutover - timedelta(days=14)).isoformat(), "what": "Announce scope, date, and what users must do"},
                {"when": (cutover - timedelta(days=7)).isoformat(), "what": "Reminder with instructions and helpdesk contact"},
                {"when": (cutover - timedelta(days=1)).isoformat(), "what": "Final notice and go/no-go confirmed"},
                {"when": cutover.isoformat(), "what": "Cutover day: status channel updates"},
                {"when": (cutover + timedelta(days=1)).isoformat(), "what": "Day-after check-in and known-issues note"},
                {"when": (cutover + timedelta(days=7)).isoformat(), "what": "Close hypercare and publish wave results"},
            ],
        })
    return waves, blocked, deferred


def main():
    pid = arg("--pack")
    if not pid:
        sys.exit(__doc__)
    pack = load_pack(pid)
    if "--template" in sys.argv:
        print("name,type,owner,users,criticality,depends_on,target_support,fixed_date,notes")
        print("# valid types:", ", ".join(f"{k} ({v['label']})" for k, v in pack["types"].items()), file=sys.stderr)
        return
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        sys.exit(__doc__)
    inv = sys.argv[1]
    source, target = (arg("--source", "") or "").lower(), (arg("--target", "") or "").lower()
    size = int(arg("--wave-size", 8))
    weeks = int(arg("--wave-weeks", 2))
    start = datetime.strptime(arg("--start"), "%Y-%m-%d").date() if arg("--start") else next_monday(date.today())
    if start.weekday() != 0:
        start = next_monday(start)
    freezes = parse_freezes(arg("--freeze", multi=True))
    out = arg("--out", "plan.json")

    items, errors = read_inventory(inv, pack)
    if errors:
        print("Inventory problems:")
        for e in errors:
            print("  -", e)
        if not items:
            sys.exit(1)
    score(items, pack)
    cycles = levels(items)
    waves, blocked, deferred = build_waves(items, pack, size, weeks, start, freezes)

    pair = f"{source}>{target}"
    gotchas = pack.get("pair_gotchas", {}).get(pair, []) + pack["gotchas"]
    plan = {
        "pack": pack["id"], "title": pack["title"], "summary": pack["summary"],
        "source": source, "target": target, "generated": date.today().isoformat(),
        "settings": {"start": start.isoformat(), "wave_size": size, "wave_weeks": weeks,
                     "freezes": [f"{a}:{b}" for a, b in freezes]},
        "inventory_errors": errors, "cycles": cycles,
        "items": sorted(items, key=lambda i: (i.get("wave", 99), -i["risk"])),
        "waves": waves,
        "needs_decision": [{"name": b["name"], "why": "No target support: replace, retire, or build a workaround (record as an ADR)",
                            "risk": b["risk"], "users": b["users"]} for b in blocked]
                         + [{"name": d["name"], "why": d["deferred_reason"], "risk": d["risk"], "users": d["users"]} for d in deferred],
        "gotchas": gotchas, "discovery": pack["discovery"], "phases": pack["phases"],
        "cutover_checklist": pack["cutover_checklist"], "rollback": pack["rollback"],
        "exit_criteria": pack["exit_criteria"], "stakeholders": pack["stakeholders"],
        "decisions": pack["decisions"],
        "totals": {"items": len(items), "effort_days": round(sum(i["effort_days"] for i in items), 1),
                   "by_level": dict(Counter(i["level"] for i in items))},
    }
    json.dump(plan, open(out, "w"), indent=2)

    print(f"{pack['title']}: {source or '?'} -> {target or '?'}")
    print(f"{len(items)} items, {plan['totals']['effort_days']} effort-days, {len(waves)} waves, "
          f"{len(blocked)} blocked, {len(deferred)} deferred")
    print("Risk: " + ", ".join(f"{l} {plan['totals']['by_level'].get(l, 0)}" for _, l in LEVELS))
    if cycles:
        print("WARNING dependency cycle among:", ", ".join(cycles), "(scheduled in the same wave; review)")
    for w in waves:
        print(f"  {w['label']:<11} {w['start']} -> {w['end']}  cutover {w['cutover']}  {len(w['items'])} items, "
              f"{w['effort_days']}d, peak risk {w['peak_risk']}" + ("  [shifted for freeze]" if w["shifted_for_freeze"] else "")
              + ("  [held for quarter start: " + ", ".join(w["anchored"]) + "]" if w["shifted_for_anchor"] else ""))
    for n in plan["needs_decision"]:
        print(f"  DECISION NEEDED: {n['name']} ({n['why']})")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
