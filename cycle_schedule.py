#!/usr/bin/env python3
"""
cycle_schedule.py  --  Resolve "what cycle length is each controller running at a
given date & time" from controller .xls timing-sheet exports.

The chain for any datetime:
  Adv Schedule(4.3)  : which schedule entry (TOD) matches this day-of-week / month /
                       day-of-month -> a Day Plan number.
  Day Plan(4.4)      : within that plan, the event (hour:minute) in effect gives an
                       Action number.
  Actions(4.5)       : Action -> Pattern.
  Patterns(2.4)      : Pattern -> Cycle length.

Specials (not in Patterns(2.4)):
  Pattern 254 = Free (0 cycle length)
  Pattern 255 = Flash
  Any pattern whose cycle is 0 (or missing) is treated as Free.

Schedule precedence
-------------------
Multiple schedule entries can match one date (e.g. the weekly "every Monday"
entry AND a "Memorial Day" entry).  The controller's intent is that the more
specific entry wins, so we select the MATCHING entry with the FEWEST enabled
day/month/date bits (ties broken by the higher TOD index).  This is what makes a
holiday entry override the weekly default and the all-on catch-all.

Reuses the robust .xls reader and sheet helpers from flash_check.py.
"""

import csv as _csv
import datetime as _dt
import io
import os
import re

import flash_check as fc

DOW_HEADERS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
MON_HEADERS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

PATTERN_FREE = 254
PATTERN_FLASH = 255


# ----------------------------------------------------------------------------- helpers
def _to_int(value):
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def id_from_filename(filename):
    """Pull the controller/location ID from a file name, e.g.
    'Main + Creekside  TSP_BBU_31.xls' -> '31'. Uses the LAST run of digits."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    nums = re.findall(r"\d+", stem)
    return nums[-1] if nums else None


def norm_id(value):
    """Canonical key for matching IDs: numeric IDs compare without leading zeros."""
    s = str(value).strip()
    digits = re.sub(r"\D", "", s)
    if digits:
        return str(int(digits))
    return s.lower()


# A ready-to-fill template users can download from the tool.
LOCATIONS_TEMPLATE = (
    "id,name,latitude,longitude\n"
    "31,Main + Creekside,37.6789,-121.7654\n"
    "42,1st & Oak,37.6810,-121.7702\n"
)


def parse_locations_csv(data):
    """Parse a locations CSV into {norm_id: {lat, lon, name, raw_id}}.

    Flexible header detection: ID column (id / controller / signal / ...),
    latitude (lat / latitude / y), longitude (lon / lng / longitude / x),
    optional name. Returns (locations_dict, error_message_or_None).
    """
    if isinstance(data, (bytes, bytearray)):
        text = data.decode("utf-8-sig", errors="replace")
    else:
        text = data
    reader = _csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return {}, "The CSV has no header row."

    def find(exact, contains=None):
        for f in reader.fieldnames:
            if f and f.strip().lower() in exact:
                return f
        if contains:
            for f in reader.fieldnames:
                if f and contains in f.strip().lower():
                    return f
        return None

    id_col = find({"id", "controller", "controller_id", "controllerid", "signal",
                   "signal_id", "asset", "asset_id", "location_id", "number", "no",
                   "cabinet"}, contains="id")
    lat_col = find({"lat", "latitude", "y"}, contains="lat")
    lon_col = find({"lon", "lng", "long", "longitude", "x"}, contains="lon")
    name_col = find({"name", "intersection", "location", "description", "street",
                     "signal_name"}, contains="name")
    if not (id_col and lat_col and lon_col):
        return {}, ("Could not find ID / latitude / longitude columns. "
                    f"Headers seen: {reader.fieldnames}")

    out = {}
    for row in reader:
        raw = str(row.get(id_col, "")).strip()
        if not raw:
            continue
        try:
            lat = float(str(row[lat_col]).strip())
            lon = float(str(row[lon_col]).strip())
        except (ValueError, TypeError, KeyError):
            continue
        out[norm_id(raw)] = {
            "lat": lat, "lon": lon,
            "name": (str(row.get(name_col, "")).strip() if name_col else ""),
            "raw_id": raw,
        }
    return out, None


# ----------------------------------------------------------------------------- model build
def _parse_schedule(wb):
    sh = fc.find_sheet(wb, "Adv Schedule(4.3)", "Adv Schedule")
    if sh is None:
        raise LookupError("Adv Schedule(4.3) sheet not found")
    hdr_row, hdr = fc.find_header_row(sh, ["Plan", "Sun"])
    if hdr_row is None:
        raise LookupError("could not locate Plan/Sun header in Adv Schedule sheet")
    low = [h.lower() for h in hdr]
    plan_col = low.index("plan")
    dow_cols = [low.index(d) for d in DOW_HEADERS]
    mon_cols = [low.index(m) for m in MON_HEADERS]
    # Day-of-month headers are "01".."31"
    dom_col = {}
    for i, h in enumerate(hdr):
        hs = h.strip()
        if hs.isdigit() and 1 <= int(hs) <= 31:
            dom_col[int(hs)] = i

    entries = []
    idx = 0
    for r in range(hdr_row + 1, sh.nrows):
        tod = fc.cell(sh, r, 0)
        if not tod.lower().startswith("tod"):
            continue
        idx += 1
        plan = _to_int(fc.cell(sh, r, plan_col))
        if plan is None:
            continue
        on = lambda c: fc.cell(sh, r, c).upper() == "ON"
        dow = [on(c) for c in dow_cols]
        mon = [on(c) for c in mon_cols]
        dom = [on(dom_col[d]) for d in range(1, 32)]
        # specificity: fewer enabled bits = more specific
        spec = sum(dow) + sum(mon) + sum(dom)
        # an entry that can never fire (no DOW, no month, or no date enabled) is skipped
        if not any(dow) or not any(mon) or not any(dom):
            continue
        entries.append({"tod": tod, "idx": idx, "plan": plan,
                        "dow": dow, "mon": mon, "dom": dom, "spec": spec})
    return entries


def _parse_day_plans(wb):
    """Return {plan_int: [(minute_of_day, action_int), ...] sorted by time}."""
    raw = fc.parse_day_plans(wb)  # {plan_str: [("HH:MM", action_str), ...]}
    plans = {}
    for plan_str, events in raw.items():
        plan = _to_int(plan_str)
        if plan is None:
            continue
        seq = []
        for time_str, action_str in events:
            action = _to_int(action_str)
            if action is None:
                continue
            try:
                hh, mm = time_str.split(":")
                minute = int(hh) * 60 + int(mm)
            except ValueError:
                minute = 0
            seq.append((minute, action))
        seq.sort()
        plans[plan] = seq
    return plans


def _parse_patterns(wb):
    """Return {pattern_int: cycle_int}.

    The cycle-length column header varies between exports — some sheets label it
    'Cycle', others 'Cycle Time'. We accept either (any header starting 'cycle')."""
    sh = fc.find_sheet(wb, "Patterns(2.4)", "Patterns(")
    if sh is None:
        raise LookupError("Patterns(2.4) sheet not found")
    hdr_row, cyc_col = None, None
    for r in range(min(sh.nrows, 15)):
        row = [fc.cell(sh, r, c).lower() for c in range(sh.ncols)]
        if "pattern" not in row:
            continue
        for i, h in enumerate(row):
            if h.startswith("cycle"):          # 'cycle' or 'cycle time'
                hdr_row, cyc_col = r, i
                break
        if hdr_row is not None:
            break
    if hdr_row is None:
        raise LookupError('could not locate Pattern / "Cycle" (or "Cycle Time") header '
                          "in Patterns(2.4) sheet")
    out = {}
    for r in range(hdr_row + 1, sh.nrows):
        lbl = fc.cell(sh, r, 0)
        if not lbl.lower().startswith("pattern"):
            continue
        pat = _to_int(lbl.split()[-1])
        cyc = _to_int(fc.cell(sh, r, cyc_col))
        if pat is not None:
            out[pat] = cyc
    return out


def build_model(wb, filename):
    """Build a compact, picklable model from an opened workbook."""
    name, ident = fc.get_meta(wb)
    act_to_pat, _ = fc.parse_flash_actions(wb)  # {action_str: pattern_str}
    action_to_pattern = {}
    for a, p in act_to_pat.items():
        ai, pi = _to_int(a), _to_int(p)
        if ai is not None:
            action_to_pattern[ai] = pi
    return {
        "file": filename,
        "name": name,
        "workbook_id": ident,
        "file_id": id_from_filename(filename),
        "schedule": _parse_schedule(wb),
        "day_plans": _parse_day_plans(wb),
        "action_to_pattern": action_to_pattern,
        "pattern_to_cycle": _parse_patterns(wb),
        "error": None,
    }


def build_model_bytes(filename, data):
    """Build a model from raw uploaded bytes; capture errors into the model."""
    try:
        return build_model(fc.load_workbook_bytes(data), filename)
    except Exception as exc:
        return {"file": filename, "name": "", "workbook_id": "",
                "file_id": id_from_filename(filename), "schedule": [], "day_plans": {},
                "action_to_pattern": {}, "pattern_to_cycle": {},
                "error": f"{type(exc).__name__}: {exc}"}


def build_model_file(path):
    try:
        return build_model(fc.load_workbook(path), os.path.basename(path))
    except Exception as exc:
        return {"file": os.path.basename(path), "name": "", "workbook_id": "",
                "file_id": id_from_filename(path), "schedule": [], "day_plans": {},
                "action_to_pattern": {}, "pattern_to_cycle": {},
                "error": f"{type(exc).__name__}: {exc}"}


# ----------------------------------------------------------------------------- resolve
def _classify(pattern, pattern_to_cycle):
    """Map a pattern number to (state, cycle, label)."""
    if pattern == PATTERN_FLASH:
        return "flash", None, "Flash"
    if pattern == PATTERN_FREE:
        return "free", 0, "Free"
    cycle = pattern_to_cycle.get(pattern)
    if cycle is None:
        return "free", None, "Free"        # pattern not defined -> running free
    if cycle == 0:
        return "free", 0, "Free"
    return "coord", cycle, f"{cycle}s"


def resolve(model, when):
    """Resolve the controller state at datetime `when`.

    Returns dict: state ('coord'|'free'|'flash'|'none'|'error'), cycle (int|None),
    label (str), plan, tod, action, pattern.
    """
    base = {"state": "none", "cycle": None, "label": "—",
            "plan": None, "tod": None, "action": None, "pattern": None}
    if model.get("error"):
        base.update(state="error", label="Unreadable")
        return base

    dow_idx = (when.weekday() + 1) % 7  # python Mon=0..Sun=6  ->  0=Sun..6=Sat
    best = None
    for e in model["schedule"]:
        if e["dow"][dow_idx] and e["mon"][when.month - 1] and e["dom"][when.day - 1]:
            if (best is None
                    or e["spec"] < best["spec"]
                    or (e["spec"] == best["spec"] and e["idx"] > best["idx"])):
                best = e
    if best is None:
        # No schedule entry applies -> controller runs free.
        base.update(state="free", cycle=None, label="Free")
        return base

    events = model["day_plans"].get(best["plan"], [])
    minute = when.hour * 60 + when.minute
    action = None
    for mn, act in events:
        if mn <= minute:
            action = act
    if action is None and events:
        action = events[-1][1]  # wrap: last event of the day carries past midnight

    pattern = model["action_to_pattern"].get(action) if action is not None else None
    state, cycle, label = _classify(pattern, model["pattern_to_cycle"])
    return {"state": state, "cycle": cycle, "label": label,
            "plan": best["plan"], "tod": best["tod"], "action": action, "pattern": pattern}


def transition_minutes(model, date):
    """Minutes-of-day at which this controller's resolved cycle/state changes on
    `date`. Cheap: the schedule (and thus the day plan) is fixed for the date, so
    we only evaluate at that plan's event times. Used to put tick marks on the
    time slider."""
    if model.get("error"):
        return []
    midnight = _dt.datetime.combine(date, _dt.time(0, 0))
    plan = resolve(model, midnight).get("plan")   # one schedule match for the day
    if plan is None:
        return []
    events = model["day_plans"].get(plan, [])
    if not events:
        return []
    # last action per minute wins (matches resolve semantics)
    by_minute = {}
    for mn, action in sorted(events):
        by_minute[mn] = action

    a2p = model["action_to_pattern"]
    p2c = model["pattern_to_cycle"]

    def key_for(action):
        state, cycle, _ = _classify(a2p.get(action), p2c)
        return (state, cycle)

    out = []
    prev = key_for(by_minute[max(by_minute)])      # state carried over midnight
    for mn in sorted(by_minute):
        if not (0 <= mn < 1440):
            continue
        k = key_for(by_minute[mn])
        if k != prev:
            if mn > 0:                              # 00:00 isn't a mid-day transition
                out.append(mn)
            prev = k
    return out


def day_timeline(model, date):
    """Return [(minute_of_day, resolve_result), ...] at each point the state changes
    over the given date — handy for a 24-hour strip."""
    out = []
    last = None
    for minute in range(0, 24 * 60, 5):
        when = _dt.datetime.combine(date, _dt.time(minute // 60, minute % 60))
        res = resolve(model, when)
        key = (res["state"], res["cycle"], res["pattern"])
        if key != last:
            out.append((minute, res))
            last = key
    return out


# ----------------------------------------------------------------------------- quick CLI test
if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "/Users/matt/Downloads/Main + Creekside              TSP_BBU_31.xls"
    m = build_model_file(path)
    print("file:", m["file"], "| id:", m["file_id"], "| name:", m["name"], "| err:", m["error"])
    print("schedule entries:", len(m["schedule"]), "| day plans:", len(m["day_plans"]))
    for when in [_dt.datetime(2026, 6, 8, 12, 0), _dt.datetime(2026, 6, 8, 3, 0),
                 _dt.datetime(2026, 5, 25, 12, 0), _dt.datetime(2026, 7, 4, 10, 0),
                 _dt.datetime(2026, 12, 25, 9, 0)]:
        print(when.strftime("%a %Y-%m-%d %H:%M"), "->", resolve(m, when))
