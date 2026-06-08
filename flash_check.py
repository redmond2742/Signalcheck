#!/usr/bin/env python3
"""
flash_check.py  --  Detect scheduled 4-way flash in traffic-signal controller
                    configuration workbooks (.xls export).

Logic (per file):
  1. Actions(4.5):     map each Action number -> Pattern.  Any Action whose
                       Pattern == 255 is a "flash action" (255 = 4-way flash).
  2. Adv Schedule(4.3): the "Plan" column links each TOD schedule entry to a
                       Day Plan.  A TOD entry that has no weekday turned ON can
                       never fire, so it is treated as inactive.
  3. Day Plan(4.4):    each Day Plan runs a list of Actions at scheduled times.
  4. Result:           if an *active* TOD links to a Day Plan that runs a flash
                       action, the signal has 4-way flash programmed.

The script walks a folder (or a single file / glob), prints a summary line per
file, lists the details for any hit, and writes a CSV summary.

Reading legacy .xls:  these controller exports are BIFF files wrapped in a
slightly malformed OLE container that trips xlrd's corruption guard.  We fall
back to pulling the raw "Workbook" stream out with olefile and handing the BIFF
bytes straight to xlrd.

Dependencies:  xlrd>=2.0, olefile   (pip install xlrd olefile)

Usage:
  python flash_check.py /path/to/folder
  python flash_check.py /path/to/folder --recursive --out flash_summary.csv
  python flash_check.py "one file.xls"
"""

import argparse
import csv
import glob
import io
import os
import sys

try:
    import xlrd
except ImportError:
    sys.exit("Missing dependency 'xlrd'.  Install with:  pip install xlrd olefile")
try:
    import olefile
except ImportError:
    sys.exit("Missing dependency 'olefile'.  Install with:  pip install xlrd olefile")


# The pattern number that means "4-way flash" on this controller family.
FLASH_PATTERN = "255"

# Sink for xlrd's diagnostic chatter (it prints a corruption dump to stdout by
# default for these malformed-OLE exports, even when it recovers).
_QUIET = open(os.devnull, "w")


# ----------------------------------------------------------------------------- helpers
def norm(value):
    """Normalize a cell to a clean integer-string when it looks numeric.
    '25.0' -> '25', 'Action 25' kept as-is, blanks -> ''."""
    s = str(value).strip()
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s


def cell(sheet, r, c):
    try:
        return str(sheet.cell_value(r, c)).strip()
    except IndexError:
        return ""


def load_workbook(path):
    """Open a workbook from a path, including legacy .xls with a malformed OLE wrapper."""
    try:
        return xlrd.open_workbook(path, logfile=_QUIET, ignore_workbook_corruption=True)
    except Exception:
        with open(path, "rb") as fh:
            return load_workbook_bytes(fh.read())


def load_workbook_bytes(data):
    """Open a workbook from raw bytes (e.g. an uploaded file), with the same
    malformed-OLE fallback as load_workbook()."""
    try:
        return xlrd.open_workbook(file_contents=data, logfile=_QUIET)
    except Exception:
        # Pull the raw BIFF stream out of the OLE container and parse that directly.
        ole = olefile.OleFileIO(io.BytesIO(data))
        try:
            for stream_name in ("Workbook", "Book"):
                if ole.exists(stream_name):
                    return xlrd.open_workbook(
                        file_contents=ole.openstream(stream_name).read(), logfile=_QUIET)
            raise RuntimeError("no Workbook/Book stream found in OLE container")
        finally:
            ole.close()


def find_sheet(wb, *prefixes):
    """Return the first sheet whose name starts with one of the given prefixes
    (case-insensitive).  Returns None if not found."""
    lowered = [p.lower() for p in prefixes]
    for name in wb.sheet_names():
        nl = name.lower()
        if any(nl.startswith(p) for p in lowered):
            return wb.sheet_by_name(name)
    return None


def find_header_row(sheet, must_contain, limit=15):
    """Find the first row (within the first `limit` rows) that contains every
    label in `must_contain`.  Returns (row_index, [cell values]) or (None, None)."""
    want = [w.lower() for w in must_contain]
    for r in range(min(sheet.nrows, limit)):
        row = [cell(sheet, r, c).lower() for c in range(sheet.ncols)]
        if all(w in row for w in want):
            return r, [cell(sheet, r, c) for c in range(sheet.ncols)]
    return None, None


def get_meta(wb):
    """Pull the intersection 'Name:' and 'ID:' fields from the workbook header rows."""
    name, ident = "", ""
    for sheet_name in wb.sheet_names():
        sh = wb.sheet_by_name(sheet_name)
        for r in range(min(sh.nrows, 6)):
            v = cell(sh, r, 0)
            if not name and v.lower().startswith("name:"):
                name = v.split(":", 1)[1].strip()
            if not ident and v.lower().startswith("id:"):
                ident = v.split(":", 1)[1].strip()
        if name and ident:
            break
    return name, ident


# ----------------------------------------------------------------------------- parsers
def parse_flash_actions(wb, flash_pattern=FLASH_PATTERN):
    """Actions(4.5): return {action_number: pattern} and the set of action
    numbers whose pattern == flash_pattern."""
    flash_pattern = norm(flash_pattern)
    sh = find_sheet(wb, "Actions(4.5)", "Actions(")
    if sh is None:
        raise LookupError("Actions(4.5) sheet not found")
    hdr_row, hdr = find_header_row(sh, ["Action", "Pattern"])
    if hdr_row is None:
        raise LookupError("could not locate Action/Pattern header in Actions sheet")
    action_col = [c.lower() for c in hdr].index("action")
    pattern_col = [c.lower() for c in hdr].index("pattern")

    act_to_pat, flash_actions = {}, set()
    for r in range(hdr_row + 1, sh.nrows):
        label = cell(sh, r, action_col)
        if not label.lower().startswith("action"):
            continue
        num = norm(label.split()[-1])
        pat = norm(cell(sh, r, pattern_col))
        act_to_pat[num] = pat
        if pat == flash_pattern:
            flash_actions.add(num)
    return act_to_pat, flash_actions


def parse_schedule(wb):
    """Adv Schedule(4.3): return list of dicts {tod, plan, active} where active
    means at least one weekday column is ON."""
    sh = find_sheet(wb, "Adv Schedule(4.3)", "Adv Schedule")
    if sh is None:
        raise LookupError("Adv Schedule(4.3) sheet not found")
    hdr_row, hdr = find_header_row(sh, ["Plan", "Sun"])
    if hdr_row is None:
        raise LookupError("could not locate Plan/Sun header in Adv Schedule sheet")
    lower = [c.lower() for c in hdr]
    plan_col = lower.index("plan")
    dow_cols = [lower.index(d) for d in ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]]
    dow_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    entries = []
    for r in range(hdr_row + 1, sh.nrows):
        tod = cell(sh, r, 0)
        if not tod.lower().startswith("tod"):
            continue
        plan = norm(cell(sh, r, plan_col))
        if not plan or plan == "0":
            continue
        on_days = [dow_names[i] for i, c in enumerate(dow_cols) if cell(sh, r, c).upper() == "ON"]
        entries.append({"tod": tod, "plan": plan, "active": bool(on_days), "days": on_days})
    return entries


def parse_day_plans(wb):
    """Day Plan(4.4): return {plan_number: [(time_str, action), ...]} for events
    whose action is non-zero."""
    sh = find_sheet(wb, "Day Plan(4.4)", "Day Plan(")
    if sh is None:
        raise LookupError("Day Plan(4.4) sheet not found")
    hdr_row, hdr = find_header_row(sh, ["Param"])
    if hdr_row is None:
        raise LookupError("could not locate Param header in Day Plan sheet")
    lower = [c.lower() for c in hdr]
    param_col = lower.index("param")
    table_col = lower.index("table") if "table" in lower else param_col - 1
    event_start = param_col + 1

    # Group the Hour / Minute / Action rows by table (plan) number.
    tables = {}
    for r in range(hdr_row + 1, sh.nrows):
        param = cell(sh, r, param_col)
        if param not in ("Hour", "Minute", "Action"):
            continue
        plan = norm(cell(sh, r, table_col))
        if not plan:
            continue
        values = [norm(cell(sh, r, c)) for c in range(event_start, sh.ncols)]
        tables.setdefault(plan, {})[param] = values

    plan_events = {}
    for plan, rows in tables.items():
        hours = rows.get("Hour", [])
        minutes = rows.get("Minute", [])
        actions = rows.get("Action", [])
        events = []
        for i, action in enumerate(actions):
            if not action or action == "0":
                continue
            hh = hours[i] if i < len(hours) and hours[i] else "0"
            mm = minutes[i] if i < len(minutes) and minutes[i] else "0"
            try:
                time_str = f"{int(hh):02d}:{int(mm):02d}"
            except ValueError:
                time_str = f"{hh}:{mm}"
            events.append((time_str, action))
        plan_events[plan] = events
    return plan_events


# ----------------------------------------------------------------------------- per-file
def _new_result(filename):
    return {
        "file": filename,
        "name": "",
        "id": "",
        "flash_actions": "",
        "has_flash": False,          # via an ACTIVE schedule entry
        "flash_inactive_only": False,  # flash exists but only on disabled TOD slots
        "flash_plans": "",
        "details": [],
        "error": "",
    }


def analyze_workbook(wb, filename, flash_pattern=FLASH_PATTERN):
    """Run the full analysis on an already-opened workbook. Returns a result dict."""
    result = _new_result(filename)
    result["name"], result["id"] = get_meta(wb)
    act_to_pat, flash_actions = parse_flash_actions(wb, flash_pattern)
    result["flash_actions"] = ",".join(sorted(flash_actions, key=lambda x: int(x))) \
        if flash_actions else ""
    schedule = parse_schedule(wb)
    plan_events = parse_day_plans(wb)

    if not flash_actions:
        return result  # this controller has no action mapped to the flash pattern

    active_plans, flash_plans = set(), set()
    for entry in schedule:
        events = plan_events.get(entry["plan"], [])
        hits = [(t, a) for (t, a) in events if a in flash_actions]
        if not hits:
            continue
        flash_plans.add(entry["plan"])
        if entry["active"]:
            active_plans.add(entry["plan"])
        for time_str, action in hits:
            result["details"].append({
                "tod": entry["tod"],
                "days": ",".join(entry["days"]) if entry["days"] else "(no weekday set)",
                "active": entry["active"],
                "plan": entry["plan"],
                "time": time_str,
                "action": action,
            })

    result["has_flash"] = bool(active_plans)
    result["flash_inactive_only"] = bool(flash_plans) and not active_plans
    result["flash_plans"] = ",".join(sorted(flash_plans, key=lambda x: int(x)))
    return result


def analyze_file(path, flash_pattern=FLASH_PATTERN):
    """Analyze a workbook on disk. Errors are captured into the result dict."""
    try:
        return analyze_workbook(load_workbook(path), os.path.basename(path), flash_pattern)
    except Exception as exc:  # keep going across a batch even if one file is bad
        result = _new_result(os.path.basename(path))
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def analyze_bytes(filename, data, flash_pattern=FLASH_PATTERN):
    """Analyze a workbook from raw bytes (e.g. an uploaded file)."""
    try:
        return analyze_workbook(load_workbook_bytes(data), filename, flash_pattern)
    except Exception as exc:
        result = _new_result(filename)
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


# ----------------------------------------------------------------------------- output
CSV_HEADER = ["file", "intersection", "controller_id", "has_scheduled_flash",
              "flash_on_disabled_slots_only", "flash_actions", "flash_day_plans",
              "trigger_detail", "error"]


def result_to_csv_row(res):
    detail = "; ".join(
        f"{d['tod']}({d['days']})->Plan {d['plan']} Action {d['action']} @ {d['time']}"
        for d in res["details"] if d["active"]
    )
    return [res["file"], res["name"], res["id"],
            "YES" if res["has_flash"] else "no",
            "YES" if res["flash_inactive_only"] else "no",
            res["flash_actions"], res["flash_plans"], detail, res["error"]]


def results_to_csv(results):
    """Return a CSV string for a list of result dicts."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADER)
    for res in results:
        w.writerow(result_to_csv_row(res))
    return buf.getvalue()


# ----------------------------------------------------------------------------- driver
def gather_files(target, recursive):
    if os.path.isdir(target):
        pattern = "**/*.xls" if recursive else "*.xls"
        files = glob.glob(os.path.join(target, pattern), recursive=recursive)
    else:
        files = glob.glob(target)  # a single file or a glob expression
    # .xls only (skip temporary Excel lock files like ~$...)
    return sorted(f for f in files if f.lower().endswith(".xls")
                  and not os.path.basename(f).startswith("~$"))


def main():
    ap = argparse.ArgumentParser(description="Detect scheduled 4-way flash (pattern 255) in controller .xls exports.")
    ap.add_argument("path", nargs="?", default=".",
                    help="folder, single .xls file, or glob (default: current folder)")
    ap.add_argument("-r", "--recursive", action="store_true", help="recurse into subfolders")
    ap.add_argument("-o", "--out", default="flash_summary.csv", help="CSV summary output path")
    args = ap.parse_args()

    files = gather_files(args.path, args.recursive)
    if not files:
        sys.exit(f"No .xls files found at: {args.path}")

    print(f"Scanning {len(files)} file(s) for scheduled 4-way flash (pattern {FLASH_PATTERN})...\n")
    rows = []
    flash_count = 0
    for path in files:
        res = analyze_file(path)
        rows.append(res)

        if res["error"]:
            print(f"  [ERROR] {res['file']}: {res['error']}")
            continue

        label = res["name"] or res["file"]
        if res["has_flash"]:
            flash_count += 1
            print(f"  [FLASH] {label}")
            print(f"          file: {res['file']}")
            print(f"          flash actions: {res['flash_actions']}   flash day plans: {res['flash_plans']}")
            for d in res["details"]:
                if d["active"]:
                    print(f"            - {d['tod']} ({d['days']}) -> Day Plan {d['plan']} "
                          f"runs Action {d['action']} at {d['time']}")
        elif res["flash_inactive_only"]:
            print(f"  [flash configured but on disabled TOD slots only] {label}  "
                  f"(actions {res['flash_actions']}, plans {res['flash_plans']})")
        elif not res["flash_actions"]:
            print(f"  [ ok  ] {label}  (no action maps to pattern {FLASH_PATTERN})")
        else:
            print(f"  [ ok  ] {label}  (flash actions {res['flash_actions']} exist but no day plan runs them)")

    # ---- CSV summary ----
    with open(args.out, "w", newline="") as fh:
        fh.write(results_to_csv(rows))

    errors = sum(1 for r in rows if r["error"])
    print(f"\nDone. {flash_count} of {len(files)} file(s) have 4-way flash on an active schedule.")
    if errors:
        print(f"{errors} file(s) could not be read (see CSV 'error' column).")
    print(f"Summary written to: {args.out}")


if __name__ == "__main__":
    main()
