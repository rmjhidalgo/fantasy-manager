# Fantasy Manager

A free, non-commercial helper for **Yahoo Fantasy Basketball** (head-to-head points leagues). It's a hobby project for personal use and a small group of friends.

> **Status:** in development. The Yahoo Fantasy Sports API connection is waiting for Yahoo's approval.

## What it does
- Projects fantasy points for your roster and your weekly opponent
- Recommends your best daily lineup for your league's roster positions
- Ranks free agents by how many points they would add to *your* team, considering the NBA schedule and your league's weekly add limit
- Suggests add/drop moves for this week, next week, the next 5 weeks, or the fantasy playoffs
- Compares trades and plans for the playoff schedule
- Optional: your own Claude Desktop app can answer questions about your team through a local MCP server

## How it works
- **Runs on your computer:** each user runs the app locally, at `http://localhost`.
- **Your own Yahoo sign-in:** each user signs in with their own Yahoo account through Yahoo's official OAuth sign-in. The app only reads leagues and teams that user belongs to.
- **Read-only:** the app never changes your Yahoo team. You make every move yourself on Yahoo.
- **Your data stays local:** data and sign-in tokens are stored only on your own computer. There is no central server, no tracking, no ads and no payments.

## Data used
- From the Yahoo Fantasy Sports API (read-only):
  - league settings, standings, matchups and transactions
  - team rosters
  - player positions, injury status, free agent/waiver status and stats
- Public NBA schedule and game stats.

## Not affiliated
This project is not affiliated with or endorsed by Yahoo or the NBA.
