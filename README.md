# Fantasy Manager

A free, non-commercial helper for **Yahoo Fantasy Basketball** (head-to-head points leagues). It's a hobby project for personal use and a small group of friends.

## What it does
- Projects fantasy points for your roster and your weekly opponent, and your chance to win the matchup
- Recommends your best daily lineup for your league's roster positions
- Ranks free agents by how many points they would add to *your* lineup, and plans streaming adds within your weekly add limit
- Suggests add/drop moves for this week, next week, the next 5 weeks, or the fantasy playoffs, with plain-language reasons
- Trade analyzer and trade finder, schedule grid, player comparison, opponent scouting, scoring profile
- Playoff odds from your league's real schedule, and a morning summary
- Optional: your own Claude Desktop app can answer questions about your team through a local MCP server

## Install (for friends)
1. Download the latest **FantasyManager-x.y.z.zip** from the [Releases page](https://github.com/rmjhidalgo/fantasy-manager/releases/latest).
2. Right-click it → **Extract All…** (for example into your Documents folder).
3. Open the extracted **FantasyManager** folder and double-click **Start Fantasy Manager**.
   If Windows says "Windows protected your PC", click **More info → Run anyway**.
4. Your browser opens the app: follow the welcome steps on screen.

Nothing else to install: the zip includes everything it needs. Windows 10/11 (64-bit). The **READ ME FIRST** file in the zip explains daily use, updating and uninstalling.

## How it works
- **Runs on your computer:** each user runs their own copy at `http://localhost:8000`.
- **You bring your own pages:** you save your own Yahoo Fantasy pages in your browser (Ctrl+S) — your team, matchup, standings, player lists, schedule — and the app reads those saved files. It never logs in to Yahoo and never accesses Yahoo by itself.
- **Read-only:** the app never changes your Yahoo team. You make every move yourself on Yahoo.
- **Your data stays local:** all data is stored only on your own computer (with a daily backup). There is no central server, no accounts, no tracking, no ads and no payments. The only things it downloads are public NBA schedules/box scores from NBA.com and, to tell you about updates, the `VERSION` file of this repository.

## Data used
- From Yahoo pages you save yourself:
  - league settings, standings, matchups, the season schedule and transactions
  - team rosters
  - player positions, status, and free agent/waiver status
- Public NBA schedule and box scores. Injury status comes from the tags on your saved Yahoo pages.

## Optional: ask Claude about your team
If you use Claude Desktop, the app's **Settings** tab can add a small local MCP server to it. Claude then reads the app's numbers (roster, matchup, suggested moves, free agents, trades, playoff odds…) **read-only**, using your own Claude plan. The app itself never calls Claude, stores no Claude login, and works fully without it.

## For developers
- Run from source: `start.bat` (needs Python 3.12+ and Node.js; sets everything up on first run). Backend tests: `backend\.venv\Scripts\python -m pytest` from `backend\`.
- Build the friends' package: `powershell -ExecutionPolicy Bypass -File tools\build_release.ps1` → `release\FantasyManager-<version>.zip`. It bundles a private Python, checks that no personal files are included, and test-loads the app.
- New version: bump `VERSION` and `backend/app/__init__.py`, build, and attach the zip to a GitHub release. Running copies show "Update available" once `VERSION` on `main` is newer.

## Not affiliated
This project is not affiliated with or endorsed by Yahoo or the NBA.
