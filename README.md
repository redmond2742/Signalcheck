# 🚦 4-Way Flash Schedule Checker

Scans traffic-signal controller configuration exports (`.xls`) and flags any
signal whose **schedule commands 4-way flash**.

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
slightly malformed file wrapper that normal Excel readers reject.

There are two ways to use it:

- **Web app (`flash_app.py`)** – a point-and-click GUI you can run on one
  computer and open from any other computer on the network.
- **Command line (`flash_check.py`)** – for batch/automation use.

---

## What's in this folder

| File | What it is |
|------|------------|
| `flash_app.py` | The web app (Streamlit GUI) |
| `flash_check.py` | The analysis engine + command-line tool |
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
.env/bin/streamlit run flash_app.py        # or:  .venv/bin/streamlit run flash_app.py
```

### Open it
- **On the same computer:** go to <http://localhost:8501> in any browser.
- **From another computer on the network:** use the server's IP address, e.g.
  `http://192.168.1.42:8501`.

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

The app has two tabs:

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
streamlit run flash_app.py --server.port 8600
```

**A file shows 🔴 Error**
It's either not a controller config workbook (the app skips non-matching `.xls`
files) or it's a newer `.xlsx` file. These tools currently read the legacy `.xls`
export format.

---

## Notes / FAQ

- **Which files does it read?** Only `.xls` files. Temporary Excel lock files
  (`~$…`) are ignored automatically.
- **Is anything uploaded to the internet?** No. Everything runs on the computer
  you launch it on; other computers reach it over your local network only.
- **Why 255?** On this controller family pattern **255** is programmed as 4-way
  flash. If your agency uses a different number, change it in the sidebar (app) or
  edit `FLASH_PATTERN` near the top of `flash_check.py`.
