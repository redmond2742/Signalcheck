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

import collections as _collections
import csv as _csv
import datetime as _dt
import io
import math
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
    """Return (cycles, offsets): {pattern_int: cycle_int}, {pattern_int: offset_int}.

    The cycle-length column header varies between exports — some sheets label it
    'Cycle', others 'Cycle Time'. We accept either (any header starting 'cycle').
    The 'Offset' column (seconds) is read when present."""
    sh = fc.find_sheet(wb, "Patterns(2.4)", "Patterns(")
    if sh is None:
        raise LookupError("Patterns(2.4) sheet not found")
    hdr_row, cyc_col, off_col = None, None, None
    for r in range(min(sh.nrows, 15)):
        row = [fc.cell(sh, r, c).lower() for c in range(sh.ncols)]
        if "pattern" not in row:
            continue
        for i, h in enumerate(row):
            if cyc_col is None and h.startswith("cycle"):    # 'cycle' or 'cycle time'
                cyc_col = i
            if off_col is None and h.startswith("offset"):
                off_col = i
        if cyc_col is not None:
            hdr_row = r
            break
    if hdr_row is None:
        raise LookupError('could not locate Pattern / "Cycle" (or "Cycle Time") header '
                          "in Patterns(2.4) sheet")
    cycles, offsets = {}, {}
    for r in range(hdr_row + 1, sh.nrows):
        lbl = fc.cell(sh, r, 0)
        if not lbl.lower().startswith("pattern"):
            continue
        pat = _to_int(lbl.split()[-1])
        if pat is None:
            continue
        cycles[pat] = _to_int(fc.cell(sh, r, cyc_col))
        if off_col is not None:
            offsets[pat] = _to_int(fc.cell(sh, r, off_col))
    return cycles, offsets


def build_model(wb, filename):
    """Build a compact, picklable model from an opened workbook."""
    name, ident = fc.get_meta(wb)
    act_to_pat, _ = fc.parse_flash_actions(wb)  # {action_str: pattern_str}
    action_to_pattern = {}
    for a, p in act_to_pat.items():
        ai, pi = _to_int(a), _to_int(p)
        if ai is not None:
            action_to_pattern[ai] = pi
    cycles, offsets = _parse_patterns(wb)
    return {
        "file": filename,
        "name": name,
        "workbook_id": ident,
        "file_id": id_from_filename(filename),
        "schedule": _parse_schedule(wb),
        "day_plans": _parse_day_plans(wb),
        "action_to_pattern": action_to_pattern,
        "pattern_to_cycle": cycles,
        "pattern_to_offset": offsets,
        "error": None,
    }


def build_model_bytes(filename, data):
    """Build a model from raw uploaded bytes; capture errors into the model."""
    try:
        return build_model(fc.load_workbook_bytes(data), filename)
    except Exception as exc:
        return {"file": filename, "name": "", "workbook_id": "",
                "file_id": id_from_filename(filename), "schedule": [], "day_plans": {},
                "action_to_pattern": {}, "pattern_to_cycle": {}, "pattern_to_offset": {},
                "error": f"{type(exc).__name__}: {exc}"}


def build_model_file(path):
    try:
        return build_model(fc.load_workbook(path), os.path.basename(path))
    except Exception as exc:
        return {"file": os.path.basename(path), "name": "", "workbook_id": "",
                "file_id": id_from_filename(path), "schedule": [], "day_plans": {},
                "action_to_pattern": {}, "pattern_to_cycle": {}, "pattern_to_offset": {},
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
    label (str), plan, tod, action, pattern, offset (seconds or None).
    """
    base = {"state": "none", "cycle": None, "label": "—", "plan": None,
            "tod": None, "action": None, "pattern": None, "offset": None}
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
    offset = model.get("pattern_to_offset", {}).get(pattern) if state == "coord" else None
    return {"state": state, "cycle": cycle, "label": label, "plan": best["plan"],
            "tod": best["tod"], "action": action, "pattern": pattern, "offset": offset}


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


def segment_bounds(transitions, minute):
    """Given a signal's transition minutes (from transition_minutes) and a minute
    of day, return (start, end): the interval [start, end) around `minute` during
    which the signal holds its current cycle/state. 0 and 1440 bound the day."""
    start, end = 0, 1440
    for m in sorted(transitions):
        if m <= minute:
            start = m
        elif m > minute:
            end = m
            break
    return start, end


# ----------------------------------------------------------------------------- corridors
def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in miles."""
    radius = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def cycles_compatible(c1, c2, allow_half=True):
    """Two coordinated cycles belong to the same corridor if they're equal, or
    (optionally) one is half the other (a signal double-cycling within the corridor)."""
    if not c1 or not c2:
        return False
    if c1 == c2:
        return True
    if allow_half:
        return c1 == 2 * c2 or c2 == 2 * c1
    return False


def street_names(name):
    """Split an intersection name into its FULL cross-street names.

    'Foothill Bl & Stoneridge Dr'  -> ['Foothill Bl', 'Stoneridge Dr']
    'Main + Creekside'             -> ['Main', 'Creekside']

    Keeps the whole street name (e.g. 'Foothill Bl'), not a fragment like 'Bl'
    or 'N', so corridors are matched/labelled by the full street name."""
    out = []
    for part in re.split(r"[+&/,@]|\bat\b|\band\b", name or "", flags=re.IGNORECASE):
        cleaned = " ".join(part.split()).strip(" -.")
        if len(cleaned) >= 2:
            out.append(cleaned)
    return out


def _street_keys(name):
    """Lower-cased set of full cross-street names, for matching."""
    return {s.lower() for s in street_names(name)}


def corridor_label(names):
    """Best-effort corridor name: the full street name shared by the most member
    signals (e.g. 'Foothill Bl & A' + 'Foothill Bl & B' -> 'Foothill Bl').
    Falls back to 'Corridor' when nothing is shared."""
    counter = _collections.Counter()
    display = {}
    for nm in names:
        for street in dict.fromkeys(street_names(nm)):   # de-dupe within one name
            key = street.lower()
            counter[key] += 1
            display.setdefault(key, street)
    if counter:
        key, count = counter.most_common(1)[0]
        if count >= 2:
            return display[key]
    return "Corridor"


def _ordered_path(members):
    """Order member points so the connecting line is as short as possible.

    Connects signals purely by proximity (a short open path / approximate
    shortest Hamiltonian path), independent of any ID or input order. Uses
    nearest-neighbor seeding followed by 2-opt improvement to remove backtracks
    and crossings, so the corridor line threads cleanly through the signals
    whatever the corridor's orientation."""
    pts = [(m["lat"], m["lon"]) for m in members]
    n = len(pts)
    if n <= 2:
        return list(members)

    def dist(a, b):
        return haversine_miles(pts[a][0], pts[a][1], pts[b][0], pts[b][1])

    def total(order):
        return sum(dist(order[i], order[i + 1]) for i in range(len(order) - 1))

    # Nearest-neighbor from each start (capped for big corridors), keep the shortest.
    starts = range(n) if n <= 12 else [min(range(n), key=lambda i: pts[i][1])]
    best = None
    for start in starts:
        unvisited = set(range(n))
        unvisited.discard(start)
        order = [start]
        while unvisited:
            last = order[-1]
            nxt = min(unvisited, key=lambda j: dist(last, j))
            order.append(nxt)
            unvisited.discard(nxt)
        if best is None or total(order) < total(best):
            best = order

    # 2-opt: reverse segments while it shortens the open path.
    order = best
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            for k in range(i + 1, n):
                if i == 0 and k == n - 1:
                    continue
                before = after = 0.0
                if i > 0:
                    before += dist(order[i - 1], order[i])
                    after += dist(order[i - 1], order[k])
                if k < n - 1:
                    before += dist(order[k], order[k + 1])
                    after += dist(order[i], order[k + 1])
                if after + 1e-12 < before:
                    order[i:k + 1] = order[i:k + 1][::-1]
                    improved = True
    return [members[i] for i in order]


def progression_speed_mph(offset_a, offset_b, cycle, distance_miles):
    """Implied progression speed for a link between two coordinated signals.

    Uses the offset difference (seconds, taken as the smaller signed value modulo
    the cycle, since offsets are cyclic) as the travel time across the link, and
    the straight-line distance. Returns (speed_mph, offset_diff_sec) or (None, _)
    when it can't be computed (missing offsets, zero cycle, or zero offset diff)."""
    if offset_a is None or offset_b is None or not cycle:
        return None, None
    raw = (offset_b - offset_a) % cycle
    signed = raw if raw <= cycle / 2 else raw - cycle   # nearest direction, in (-c/2, c/2]
    seconds = abs(signed)
    if seconds <= 0:
        return None, 0
    feet = distance_miles * 5280.0
    return (feet / seconds) * (3600.0 / 5280.0), seconds


def corridor_links(corridor):
    """Per-link progression analysis along a corridor's ordered path.

    Returns a list of {from, to, distance_ft, offset_diff, speed_mph} for each
    consecutive pair of signals."""
    ms = corridor.get("ordered_members", [])
    links = []
    for a, b in zip(ms, ms[1:]):
        dist_mi = haversine_miles(a["lat"], a["lon"], b["lat"], b["lon"])
        cyc = min(a.get("cycle") or 0, b.get("cycle") or 0)
        speed, diff = progression_speed_mph(a.get("offset"), b.get("offset"), cyc, dist_mi)
        links.append({
            "from": a.get("name", ""), "to": b.get("name", ""),
            "distance_ft": dist_mi * 5280.0, "offset_diff": diff, "speed_mph": speed,
        })
    return links


def build_corridors(signals, max_miles, allow_half=True, min_size=2):
    """Group signals into corridors.

    signals : list of dicts {id, name, lat, lon, cycle, seg_start, seg_end}.
              Only coordinated signals (cycle > 0) should be passed in.
    Two signals are linked when they are within `max_miles` of each other AND:
      * they run the SAME cycle, or
      * (if allow_half) one runs half the other's cycle AND they share a common
        full street name (a half-cycle signal must be on the corridor street).

    A signal that runs a HALF/double cycle relative to its corridor's main cycle
    is only kept if it sits on the corridor's street (shares the corridor's full
    street name); otherwise it is dropped from the corridor.

    Returns a list of corridor dicts: {label, size, members, cycles, cycle_main,
    start, end, path} sorted by size then cycle. start/end are the minutes during
    which every member holds its current cycle (the window the corridor is stable);
    path is the ordered [lat, lon] points for drawing the corridor line."""
    n = len(signals)
    streets = [_street_keys(s["name"]) for s in signals]

    def adjacent(i, j):
        return haversine_miles(signals[i]["lat"], signals[i]["lon"],
                               signals[j]["lat"], signals[j]["lon"]) <= max_miles

    def linked(i, j):
        ci, cj = signals[i]["cycle"], signals[j]["cycle"]
        if not ci or not cj:
            return False
        if ci == cj:
            return adjacent(i, j)                       # same cycle: adjacency only
        if allow_half and (ci == 2 * cj or cj == 2 * ci):
            return adjacent(i, j) and bool(streets[i] & streets[j])   # half: shared street
        return False

    def components(indices):
        """Connected components (by linked()) over the given signal indices."""
        idx = list(indices)
        parent = {i: i for i in idx}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                if linked(idx[a], idx[b]):
                    ra, rb = find(idx[a]), find(idx[b])
                    if ra != rb:
                        parent[ra] = rb
        out = {}
        for i in idx:
            out.setdefault(find(i), []).append(i)
        return list(out.values())

    corridors = []
    for raw in components(range(n)):
        # The corridor's main cycle is the largest cycle present; its street is
        # the full street name shared by the most members.
        main_cycle = max(signals[i]["cycle"] for i in raw)
        primary = corridor_label([signals[i]["name"] for i in raw])
        primary_key = primary.lower() if primary != "Corridor" else None
        # Drop half/double members that are NOT on the corridor street.
        kept = [i for i in raw
                if signals[i]["cycle"] == main_cycle
                or (primary_key and primary_key in streets[i])]
        # Pruning can disconnect the group, so re-form components on survivors.
        for sub in components(kept):
            if len(sub) < min_size:
                continue
            members = [signals[i] for i in sub]
            cycles = sorted({m["cycle"] for m in members}, reverse=True)
            ordered = _ordered_path(members)
            corridors.append({
                "label": corridor_label([m["name"] for m in members]),
                "size": len(members),
                "members": members,
                "ordered_members": ordered,
                "cycles": cycles,
                "cycle_main": max(cycles),
                "start": max(m["seg_start"] for m in members),
                "end": min(m["seg_end"] for m in members),
                "path": [[m["lat"], m["lon"]] for m in ordered],
            })

    corridors.sort(key=lambda c: (-c["size"], -c["cycle_main"], c["label"]))

    # disambiguate duplicate labels (e.g. two separate 'Main' segments)
    seen = {}
    for c in corridors:
        seen[c["label"]] = seen.get(c["label"], 0) + 1
        if seen[c["label"]] > 1:
            c["label"] = f"{c['label']} ({seen[c['label']]})"
    return corridors


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
