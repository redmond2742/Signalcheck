# 🚦 SignalCheck — Traffic Signal Timing Sheet Toolkit

**SignalCheck** is a web app for inspecting and auditing traffic-signal
controller timing-sheet exports (`.xls`). It opens to a home page that links to
each tool, and it's built so new tools can be added easily over time.

It can run on one computer (a "server") and be opened from any other computer on
the same network.

### Tools

| Tool | What it does |
|------|--------------|
| **🚦 4-Way Flash Checker** | Scans controller `.xls` exports and flags any signal whose schedule commands 4-way flash (pattern 255). |
| **🗺️ Cycle Length Map** | Maps every signal's cycle length at any chosen date & time. Upload many timing sheets + a locations CSV, then scrub a calendar/time slider and watch the map recolor. |
| *(more to come)* | New tools appear here automatically as they're added. |

#### How the 4-Way Flash Checker works
It follows the same chain an engineer would check by hand:

1. **Actions (4.5)** – finds every Action whose **Pattern = 255** (255 = 4-way flash).
2. **Adv Schedule (4.3)** – reads the **Plan** column to see which Day Plans each
   schedule entry (TOD) links to. Entries with no weekday enabled never fire and
   are treated as inactive.
3. **Day Plan (4.4)** – checks whether a linked Day Plan actually runs one of the
   flash actions.
4. A signal is flagged **⚠️ FLASH** when an *active* schedule entry links to a Day
   Plan that runs a flash action.

It works on these controllers' legacy `.xls` exports even though they use a
slightly malformed file wrapper that normal Excel readers reject. Each tool's
analysis engine can also be used from the command line (see section 5).

---

## What's in this folder

| File | What it is |
|------|------------|
| `app.py` | **The web app to run** — SignalCheck home page + navigation |
| `home.py` | The landing page (auto-built from the tool list) |
| `tool_registry.py` | The list of tools — **the one place you edit to add a tool** |
| `tools/` | One file per tool's UI (e.g. `tools/flash_check_tool.py`, `tools/cycle_map_tool.py`) |
| `flash_check.py` | The 4-way-flash analysis engine + command-line tool |
| `cycle_schedule.py` | The date/time → cycle-length resolver engine (Cycle Length Map) |
| `live_map.py` + `map_component/` | Interactive Leaflet map that reports its zoom/pan (Leaflet vendored for offline use) |
| `live_time_slider.py` + `time_slider_component/` | Time slider that streams live while dragging and shows transition tick marks |
| `st_compat.py` | Small Streamlit version-compatibility shim |
| `flash_app.py` | Optional standalone launcher for just the flash checker |
| `requirements.txt` | The Python packages it needs |
| `setup.bat` | One-click **Windows** installer (creates the environment + installs packages) |
| `run_app.bat` | One-click launcher for **Windows** |
| `run_app.command` | One-click launcher for **macOS** |
| `.streamlit/config.toml` | App settings (network address, port, theme) |
| `README.md` | This file |

---

## 1. Install (one time)

### Windows (easy way)

1. **Install Python** (if you don't already have it)
   - Download the latest Python 3 from <https://www.python.org/downloads/windows/>
     (3.10–3.13 are all fine).
   - **Important:** on the first installer screen, tick
     **“Add python.exe to PATH”**, then click *Install Now*.

2. **Double-click `setup.bat`.**
   It creates a private Python environment in `.venv` and installs everything.
   When you see **“Setup complete!”** you're done. You only do this once.

   > If Windows SmartScreen warns about running the file, click *More info →
   > Run anyway*.

### Windows (manual way)

If you'd rather do it by hand instead of `setup.bat`:

1. In File Explorer, open the folder that contains these files, click the address
   bar, type `cmd`, and press **Enter** (a Command Prompt opens in this folder).
2. Run:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

### macOS

```bash
cd /path/to/this/folder
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> On this Mac it's already installed in the `.env` environment, so you can skip
> straight to running it.

---

## 2. Run the web app

### Windows
Double-click **`run_app.bat`** (or run it from the Command Prompt).

It opens a window that shows the addresses to use, for example:
```
On THIS computer, open:    http://localhost:8501
On OTHER computers, open one of the IPv4 addresses below, e.g. http://192.168.x.x:8501
   IPv4 Address. . . . . . . . . . . : 192.168.1.42
```

### macOS
Double-click **`run_app.command`**, or in Terminal:
```bash
.env/bin/streamlit run app.py        # or:  .venv/bin/streamlit run app.py
```

### Open it
- **On the same computer:** go to <http://localhost:8501> in any browser.
- **From another computer on the network:** use the server's IP address, e.g.
  `http://192.168.1.42:8501`.

You'll land on the **SignalCheck home page**; click a tool to open it, and use the
sidebar (top-left **»**) to switch between Home and the tools at any time.

To stop the app, press **Ctrl+C** in the window (or just close it).

---

## 3. Let other computers connect (network access)

The app already listens on all network interfaces, so the only thing that
usually blocks other computers is the **firewall** on the machine running it.

**Windows Firewall:** the first time you launch the app, Windows pops up a
*“Windows Defender Firewall has blocked some features”* dialog. Tick **Private
networks** and click **Allow access**. (If you missed it: Control Panel →
*Windows Defender Firewall* → *Allow an app through firewall* → allow Python.)

**Find the server's IP address:**
- Windows: run `ipconfig` and look for **IPv4 Address** (e.g. `192.168.1.42`).
- macOS: System Settings → Network, or run `ipconfig getifaddr en0`.

Then other people open `http://<that-ip>:8501`.

> Tip: a server's IP can change over time. For a permanent address, ask IT to
> give the machine a **static IP** or DHCP reservation.

---

## 4. Using the app

From the **home page**, click **🚦 4-Way Flash Checker** (or pick it in the
sidebar). That tool has two tabs:

### 📤 Upload files
Drag and drop one or more `.xls` controller exports onto the upload box (you can
select many at once). This works from **any** computer that has the app open in a
browser — the files are sent to the server and analyzed there.

### 📁 Scan a server folder
Type the path to a folder **on the computer running the app** (handy for a shared
network drive that's mounted on that machine), optionally tick *Include
sub-folders*, and click **Scan folder**.

### Reading the results
At the top you get counts:

| Badge | Meaning |
|-------|---------|
| ⚠️ **FLASH** | An active schedule runs 4-way flash — **this is what you're looking for.** |
| 🟡 **Disabled-only** | A flash plan is referenced, but only from a schedule slot with no weekday enabled (never actually runs). |
| 🟢 **OK** | No scheduled flash. |
| 🔴 **Error** | The file couldn't be read (reason shown in the table). |

Below that is a sortable table of every file. For each ⚠️ flash signal there's an
expandable **“When does each signal flash?”** section showing exactly which
schedule entry, which day(s), which Day Plan, which action, and at what time.

Click **⬇️ Download CSV summary** to save the whole table as a spreadsheet.

### Settings (left sidebar)
Click the **»** at the top-left to open the sidebar. You can change the **flash
pattern number** if a different controller family uses something other than 255.

---

## 4b. Using the 🗺️ Cycle Length Map

This tool shows what cycle length every signal is running at a chosen moment.

**1. Upload data (sidebar):**
- **Timing sheets** — one `.xls` per controller (select many at once).
- **Signal locations CSV** — places them on the map. Click **⬇️ CSV template**
  for the format. It needs an **id**, **latitude**, and **longitude** column (a
  **name** column is optional); headers are detected flexibly:

  ```csv
  id,name,latitude,longitude
  31,Main + Creekside,37.7058,-121.8744
  42,1st & Oak,37.7100,-121.8800
  ```

  The **id** is matched to the number in each timing-sheet **file name**
  (e.g. `…TSP_BBU_31.xls` → ID `31`).

**2. Pick a date & time:** use the 📅 calendar and the 🕑 time slider. They default
to today / now; click **⏱ Now** to snap back. The time slider updates the map
**live as you drag** (you don't have to let go of the knob). Vertical **tick marks**
on the slider mark every time of day that a signal changes cycle length on the
selected date — so you can jump straight to the transitions. The tick marks only
count the signals **currently visible in the map view**, so as you **zoom or pan**
the map, the ticks update to match what you're looking at. The map keeps your
zoom/pan as you scrub time.

**3. Read the map:** each signal is a dot colored by what it's running at that time:

| Dot | Meaning |
|-----|---------|
| 🟢→🟠 gradient | **Coordinated** — green = shorter cycle, orange = longer cycle (legend shows the range) |
| ⚪ gray | **Free** (pattern 254, or any pattern with a 0 cycle) |
| 🔴 red | **Flash** (pattern 255) |

Hover a dot for the intersection name, plan, action, pattern, and cycle. The table
below lists every controller (including any whose ID didn't match a location).

> The map's background tiles need internet access; the colored dots still render
> without it.

> **Pattern sheet variations:** the cycle-length column in `Patterns(2.4)` is read
> whether your export labels it **`Cycle`** or **`Cycle Time`**.

---

## 5. Command-line use (optional)

For scripting or quick one-offs, use `flash_check.py` instead of the app:

```bat
REM Windows (with the venv active)
python flash_check.py "C:\path\to\folder"
python flash_check.py "C:\path\to\folder" --recursive --out flash_report.csv
python flash_check.py "C:\path\to\one file.xls"
```

```bash
# macOS / Linux
python flash_check.py "/path/to/folder" --recursive
```

It prints a status line per file and writes `flash_summary.csv` (or whatever you
pass to `--out`).

| Option | Meaning |
|--------|---------|
| `path` | Folder, single `.xls` file, or wildcard (default: current folder) |
| `-r`, `--recursive` | Also look inside sub-folders |
| `-o`, `--out` | Where to write the CSV summary |

---

## 6. Troubleshooting

**“python is not recognized …” (Windows)**
Python isn't on your PATH. Re-run the Python installer, choose *Modify*, and make
sure **“Add python.exe to PATH”** is ticked — or reinstall and tick it on the
first screen.

**“Missing dependency 'xlrd'” / “No module named streamlit”**
The packages aren't installed in the Python you're using. Activate the venv first
(`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` on macOS), then
re-run `pip install -r requirements.txt`. Using `python -m pip install ...`
instead of plain `pip` guarantees it installs into the Python you're running.

**Other computers can't open the page**
1. Confirm the app window is still running on the server.
2. Check you're using the server's **IPv4** address and port `:8501`.
3. Allow the app through the server's firewall (see section 3).
4. Make sure both computers are on the same network/VLAN.

**“Port 8501 is already in use”**
Another copy is already running, or something else uses that port. Either close
the other window, or run on a different port:
```
streamlit run app.py --server.port 8600
```

**A file shows 🔴 Error**
It's either not a controller config workbook (the app skips non-matching `.xls`
files) or it's a newer `.xlsx` file. These tools currently read the legacy `.xls`
export format.

---

## 7. Adding a new tool (for developers)

The suite is built to grow. Adding a tool takes two steps:

1. **Create the tool's page.** Copy `tools/_template_tool.py` to
   `tools/your_tool.py` and build its UI (it's a normal Streamlit script).
   - Don't call `st.set_page_config` — `app.py` does that once for the whole suite.
   - Prefix any `st.session_state` keys with something unique so tools don't
     collide.
   - Put reusable analysis logic in its own module (like `flash_check.py`) so it
     can power a command-line tool too.

2. **Register it.** Add an entry to the `TOOLS` list in `tool_registry.py`:
   ```python
   {
       "key": "yourtool",
       "title": "Your Tool Name",
       "icon": "🧰",
       "page": "tools/your_tool.py",
       "tagline": "One short line for the home-page card.",
       "status": "live",      # or "soon" to show it as Coming soon
   }
   ```

That's all — the new tool automatically gets a card on the home page and an entry
in the sidebar. To **rebrand** the whole suite (name, tagline, icon), edit the
`SUITE_*` values at the top of `tool_registry.py`.

---

## Notes / FAQ

- **Which files does it read?** Only `.xls` files. Temporary Excel lock files
  (`~$…`) are ignored automatically.
- **Is anything uploaded to the internet?** No. Everything runs on the computer
  you launch it on; other computers reach it over your local network only.
- **Why 255?** On this controller family pattern **255** is programmed as 4-way
  flash. If your agency uses a different number, change it in the sidebar (app) or
  edit `FLASH_PATTERN` near the top of `flash_check.py`.
