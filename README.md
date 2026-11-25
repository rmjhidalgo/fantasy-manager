# Fantasy Manager

A free, non-commercial helper for **Yahoo Fantasy Basketball** (head-to-head points leagues). It's a hobby project for personal use and a small group of friends.

> **Status:** in development.

## What it does
- Projects fantasy points for your roster and your weekly opponent
- Recommends your best daily lineup for your league's roster positions
- Ranks free agents by how many points they would add to *your* team, considering the NBA schedule and your league's weekly add limit
- Suggests add/drop moves for this week, next week, the next 5 weeks, or the fantasy playoffs
- Compares trades and plans for the playoff schedule
- Optional: your own Claude Desktop app can answer questions about your team through a local MCP server

## How it works
- **Runs on your computer:** each user runs the app locally, at `http://localhost`.
- **You bring your own pages:** you save your own Yahoo Fantasy pages in your browser (Ctrl+S) — your team, matchup, standings, player lists — and the app reads those saved files. It never logs in to Yahoo and never accesses Yahoo by itself.
- **Read-only:** the app never changes your Yahoo team. You make every move yourself on Yahoo.
- **Your data stays local:** all data is stored only on your own computer. There is no central server, no tracking, no ads and no payments.

## Data used
- From Yahoo pages you save yourself:
  - league settings, standings, matchups and transactions
  - team rosters
  - player positions, status, and free agent/waiver status
- Public NBA schedule, game stats and injury report.

## Not affiliated
This project is not affiliated with or endorsed by Yahoo or the NBA.
