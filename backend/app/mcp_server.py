"""Local MCP server: lets Claude Desktop / Claude Code read Fantasy Manager's numbers.

Claude starts this program itself (see the AI assistant section on the app's Settings tab).
It asks the running Fantasy Manager app for everything over http://127.0.0.1, so Claude
sees exactly the numbers on your screens. Every tool is read-only: Claude can't change
anything in the app or on Yahoo. You make every move on Yahoo yourself.

Run by hand (for testing):  python -m app.mcp_server   (from the backend folder)
"""

import logging
import os
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

API = os.environ.get("FM_API", "http://127.0.0.1:8000").rstrip("/")
HEADERS = {"x-fm-client": "mcp"}
logging.getLogger("httpx").setLevel(logging.WARNING)  # don't log every request to the app

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

INSTRUCTIONS = """Fantasy Manager is the user's own app for their Yahoo Fantasy Basketball league (head-to-head points).
It works from Yahoo pages the user saves (Ctrl+S) plus NBA box scores and schedules, and projects fantasy points (FP).
- All tools are read-only. The user makes every move on Yahoo; suggest, don't claim to act.
- Numbers are projections: mention when data is old (see get_data_freshness), and that injury news comes from saved Yahoo tags.
- "Gain" = extra points that would end up in the user's daily lineups, worked out with a lineup optimizer.
- Players marked "not on a saved page" may be on waivers and have estimated positions.
- Dates are US Eastern (NBA game days). Yahoo links are included so the user can open the right page."""

mcp = MCPServer("Fantasy Manager", instructions=INSTRUCTIONS)


class AppNotRunning(RuntimeError):
    pass


def _get(path: str, **params: Any) -> Any:
    try:
        r = httpx.get(f"{API}{path}", params={k: v for k, v in params.items() if v is not None}, headers=HEADERS, timeout=60)
    except httpx.HTTPError as e:
        raise AppNotRunning("Fantasy Manager isn't running. Start it with start.bat, then ask again.") from e
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text[:200]
        raise RuntimeError(f"Fantasy Manager answered: {detail}")
    return r.json()


def _r(x: float | None, nd: int = 1) -> float | None:
    return round(x, nd) if isinstance(x, (int, float)) else x


# ---------------------------------------------------------------- teams + freshness

@mcp.tool(annotations=READ_ONLY)
def list_teams() -> dict:
    """The leagues/teams imported into the app, and which one is active (the one every other tool uses)."""
    return {"teams": _get("/api/leagues")["leagues"]}


@mcp.tool(annotations=READ_ONLY)
def get_active_team() -> dict:
    """The active team: league name, scoring weights, roster slots, add limit, playoff weeks, and the standings."""
    o = _get("/api/overview")
    s = o.get("settings") or {}
    return {
        "league": o.get("league"),
        "scoring": s.get("scoring"),
        "roster_positions": s.get("roster_positions"),
        "max_adds_per_week": s.get("max_adds_per_week"),
        "playoff_weeks": s.get("playoff_weeks"),
        "trade_end_date": s.get("trade_end_date"),
        "standings": [
            {k: x[k] for k in ("rank", "name", "wins", "losses", "ties", "points_for", "is_me")} for x in o.get("standings") or []
        ],
    }


@mcp.tool(annotations=READ_ONLY)
def get_data_freshness() -> dict:
    """When each kind of data was last imported (UTC), plus NBA data status. Old data means less reliable answers."""
    o = _get("/api/overview")
    nba = _get("/api/nba/status")
    return {
        "imported": o.get("freshness"),
        "nba_data_refreshed": nba.get("refreshed_at"),
        "nba_error": nba.get("last_error"),
        "unmatched_players": [u["name"] for u in nba.get("unmatched", [])],
    }


# ---------------------------------------------------------------- my team

@mcp.tool(annotations=READ_ONLY)
def get_roster() -> dict:
    """The user's roster: slot, positions, injury tag, projected FP per game, Yahoo season FP/G, games left this week, minutes trend."""
    o = _get("/api/overview")
    out = {r["player_id"]: r for r in _get("/api/outlook").get("roster", [])}
    rows = []
    for r in o.get("my_roster") or []:
        p = out.get(r["player_id"], {})
        rows.append({
            "name": r["name"], "slot": r["slot"], "nba_team": r["nba_team"], "positions": r["positions"], "status": r["status"],
            "proj_fp_per_game": _r(p.get("fpts")), "season_fp_per_game": _r(r.get("fpts")), "games_left_this_week": p.get("games_left"),
            "chance_to_play": p.get("play_prob"), "minutes_last_14_days": p.get("recent_mpg"), "minutes_season": p.get("season_mpg"),
        })
    return {"players": rows}


@mcp.tool(annotations=READ_ONLY)
def get_matchup() -> dict:
    """This week's matchup: scores, projected finals, chance to win, day-by-day expected points, and each team's players with games left."""
    d = _get("/api/matchup")
    m = d.get("matchup")
    if not m:
        return {"matchup": None, "note": "No matchup imported yet (save the Yahoo Matchup page)."}

    def side(s: dict) -> dict:
        return {
            "team": s["name"], "score_now": s["current"], "projected_final": s["final_expected"],
            "likely_range": [s["final_p10"], s["final_p90"]], "games_left": s["games_left"],
            "days": [{"date": x["date"], "expected": x["expected"], "players_playing": x["starters"], "benched_with_game": x["conflicts"]}
                     for x in s["days"]],
            "players": [{"name": p["name"], "status": p["status"], "proj_fp": _r(p["fpts"]), "games_to_play": p["starts"],
                         "games_benched": p["benched"]} for p in s["players"]],
        }

    return {
        "week": m["week"], "dates": [m["start_date"], m["end_date"]], "score_saved_at": m["as_of"],
        "chance_to_win": m["win_prob"], "me": side(m["me"]), "opponent": side(m["opp"]), "notes": m["notes"],
        "win_chance_history": [{"at": h["at"], "chance": h["win_prob"]} for h in d.get("history", [])],
        "yahoo_url": m["yahoo_url"],
    }


@mcp.tool(annotations=READ_ONLY)
def get_lineup(day: str | None = None) -> dict:
    """Best lineup for a day (YYYY-MM-DD, US Eastern; default today), compared with the lineup on the user's saved team page."""
    d = _get("/api/lineup", day=day)
    return {
        "date": d["date"], "best_expected": d["best_expected"], "current_expected": d["current_expected"],
        "changes": [{"name": p["name"], "change": p["change"]} for p in d["players"] if p["change"] in ("start", "bench")],
        "lineup": [{"slot": p["best_slot"], "name": p["name"], "game": p["game"] and p["game"]["opponent"],
                    "locked": p["locked"], "expected": p["expected"]} for p in d["players"] if p["best_slot"]],
        "il_moves": d["il_moves"], "yahoo_url": d["yahoo_url"],
    }


@mcp.tool(annotations=READ_ONLY)
def get_alerts() -> dict:
    """Current alerts: injuries, IL moves, lineup problems today, adds left, old data. Includes 'next man up' teammates for injured players."""
    return {"alerts": [
        {k: a[k] for k in ("level", "title", "detail") if k in a} | ({"next_man_up": a["next_man_up"]} if a.get("next_man_up") else {})
        for a in _get("/api/alerts")["alerts"]
    ]}


# ---------------------------------------------------------------- moves

@mcp.tool(annotations=READ_ONLY)
def get_suggested_moves(horizon: Literal["A", "B", "C", "D"] = "A") -> dict:
    """The app's suggested add/drops with reasons. horizon: A = this week (chance to win), B = next week,
    C = next 5 weeks, D = playoff weeks. Respects adds left, untouchable players and waiver timing."""
    d = _get("/api/suggestions", horizon=horizon)
    return {
        "horizon": f"{d['horizon']} · {d['horizon_name']} ({d['label']})",
        "days": [d["days"][0], d["days"][-1]] if d["days"] else [],
        "adds_budget": d["budget"],
        "points_without_moves": d["baseline"], "points_with_moves": d["with_moves"],
        "chance_to_win": {"before": d["win_before"], "after": d["win_after"]},
        "il_moves_first": [m["name"] for m in d["il_moves"]],
        "moves": [
            {"type": m["type"], "add": m["add"]["name"], "add_availability": m["add"]["kind"], "drop": m["drop"] and m["drop"]["name"],
             "from": m["first_day"], "gain_points": m["gain"], "win_chance_change": m["win_change"], "games": m["games"],
             "reasons": m["reasons"], "yahoo_url": m["yahoo_url"]}
            for m in d["moves"]
        ] or "Hold: no move is worth an add for this horizon.",
        "drop_candidates": [x["name"] for x in d.get("drop_candidates", [])],
        "warnings": d.get("warnings", []), "notes": d["notes"],
    }


@mcp.tool(annotations=READ_ONLY)
def search_free_agents(window: Literal["week", "7", "14"] = "week", position: Literal["PG", "SG", "SF", "PF", "C"] | None = None,
                       availability: Literal["FA", "W", "?"] | None = None, min_games: int = 0, limit: int = 15) -> dict:
    """Available players ranked by points they'd add to the user's lineup over a window (rest of week / next 7 / next 14 days).
    availability: FA = free agent, W = on waivers, ? = not on a saved page (worked out from NBA data)."""
    d = _get("/api/free-agents", window=window, position=position)
    out = []
    for p in d["players"]:
        if (availability and p["kind"] != availability) or p["games"] < min_games:
            continue
        out.append({
            "name": p["name"], "nba_team": p["nba_team"], "positions": p["positions"], "positions_estimated": p["positions_estimated"],
            "status": p["status"], "availability": p["kind"], "waiver_until": p["waiver_until"], "games": p["games"],
            "proj_fp_per_game": p["fpts"], "fp_last_14_days": p["window_fp"].get("L14"), "fp_season": p["window_fp"].get("S"),
            "minutes_last_14_days": p["recent_mpg"], "minutes_season": p["season_mpg"], "pct_rostered": p["pct_rostered"],
            "gain_points": p["gain"], "drop": p["drop_name"], "yahoo_url": p["yahoo_url"],
        })
        if len(out) >= max(1, min(limit, 50)):
            break
    return {"window": d["window_label"], "players": out}


@mcp.tool(annotations=READ_ONLY)
def get_streaming_plan() -> dict:
    """A chain of add/drops for the rest of this week within the adds left, and the points it adds."""
    d = _get("/api/streaming")
    return {
        "adds_left": d["adds_left"], "points_gain": d["gain"],
        "moves": [{"date": m["date"], "add": m["add"]["name"], "drop": m["drop"] and m["drop"]["name"], "games": m["game_dates"],
                   "gain": m["gain"], "yahoo_url": m["yahoo_url"]} for m in d["moves"]] or "Hold: no stream is worth an add.",
    }


@mcp.tool(annotations=READ_ONLY)
def get_move_log() -> dict:
    """Moves the user opened on Yahoo from the app's suggestions and whether they happened, plus the user's recent Yahoo transactions."""
    d = _get("/api/move-log")
    return {
        "logged_moves": [{k: m[k] for k in ("created_at", "source", "add_name", "drop_name", "gain", "status", "note")} for m in d["moves"]],
        "recent_transactions": [t["description"] + f" ({t['when']})" for t in d["transactions"]],
    }


# ---------------------------------------------------------------- strategy

def _find_rostered(teams: list[dict], name: str) -> tuple[dict, dict]:
    """(team, player) for a rostered player, by (part of) his name."""
    key = name.strip().lower()
    hits = [(t, p) for t in teams for p in t["players"] if key in p["name"].lower()]
    exact = [(t, p) for t, p in hits if p["name"].lower() == key]
    hits = exact or hits
    if not hits:
        raise ValueError(f"No rostered player matches '{name}'.")
    if len({p["id"] for _, p in hits}) > 1:
        raise ValueError(f"'{name}' matches several players: {', '.join(p['name'] for _, p in hits[:6])}. Be more specific.")
    return hits[0]


@mcp.tool(annotations=READ_ONLY)
def analyze_trade(give: list[str], get: list[str], horizon: Literal["A", "B", "C", "D"] = "C") -> dict:
    """Points each team's lineups gain or lose from a trade over a horizon (A this week, B next week, C next 5 weeks,
    D playoffs). give = the user's players (names), get = players from ONE other team. Counts the 2-day review period
    and drops needed to fit roster spots."""
    teams = _get("/api/teams")["teams"]
    me = next(t for t in teams if t["is_me"])
    give_ids = []
    for n in give:
        t, p = _find_rostered([me], n)
        give_ids.append(p["id"])
    others = [t for t in teams if not t["is_me"]]
    got = [_find_rostered(others, n) for n in get]
    if len({t["id"] for t, _ in got}) != 1:
        raise ValueError("The players to get must all be on the same team.")
    d = _get("/api/trade/analyze", other_team=got[0][0]["id"], give=give_ids, get=[p["id"] for _, p in got], horizon=horizon)

    def side(s: dict) -> dict:
        return {"team": s["name"], "points_change": s["gain"], "drops_needed": [x["name"] for x in s["drops"]]}

    return {
        "horizon": f"{d['horizon']} ({d['label']})", "takes_effect": d["effective"], "trade_deadline": d["deadline"],
        "verdict": d["verdict"], "me": side(d["my_team"]), "them": side(d["their_team"]),
        "players": [{"side": s, "name": p["name"], "status": p["status"], "proj_fp_per_game": p["fpts"], "games_in_horizon": p["games"]}
                    for s, ps in (("give", d["give"]), ("get", d["get"])) for p in ps],
        "notes": d["notes"],
    }


@mcp.tool(annotations=READ_ONLY)
def find_trades(horizon: Literal["A", "B", "C", "D"] = "C", limit: int = 8) -> dict:
    """1-for-1 trade ideas where BOTH teams' lineups gain points over the horizon (so the other manager has a reason to accept).
    Never offers the user's untouchable players."""
    d = _get("/api/trade/find", horizon=horizon, limit=max(1, min(limit, 30)))
    return {
        "horizon": f"{d['horizon']} ({d['label']})", "takes_effect": d["effective"], "trade_deadline": d["deadline"],
        "ideas": [{"with": t["team"]["name"], "give": t["give"]["name"], "get": t["get"]["name"], "my_gain": t["my_gain"],
                   "their_gain": t["their_gain"], "get_status": t["get"]["status"]} for t in d["trades"]] or "No trade helps both sides.",
        "notes": d["notes"],
    }


@mcp.tool(annotations=READ_ONLY)
def get_schedule(team: str | None = None) -> dict:
    """Games per NBA team for each remaining matchup week (back-to-backs and playoff weeks marked), and how many games
    the user's roster has each week. team = an NBA team code (e.g. LAL) to see just that team."""
    d = _get("/api/schedule")
    labels = [c["label"] + (" (playoffs)" if c["playoff"] else "") for c in d["columns"]]
    rows = [r for r in d["teams"] if not team or r["team"] == team.upper()]
    return {
        "weeks": labels,
        "my_roster_games": dict(zip(labels, d["my_games"], strict=True)),
        "teams": {r["team"]: {"games": r["games"], "back_to_backs": r["back_to_backs"], "playoff_games": r["playoff_games"],
                              "my_players": r["my_players"]} for r in rows},
        "most_playoff_games": sorted(((r["playoff_games"], r["team"]) for r in d["teams"]), reverse=True)[:6],
        "notes": d["notes"],
    }


@mcp.tool(annotations=READ_ONLY)
def compare_players(names: list[str]) -> dict:
    """Compare up to 4 players (any NBA player): projection, recent form (last 7/14/30 days and season), minutes,
    consistency (floor/ceiling), last 10 games, games coming up, and who owns them."""
    ids = []
    for n in names[:4]:
        hits = _get("/api/players/search", q=n)["players"]
        if not hits:
            raise ValueError(f"No player matches '{n}'.")
        ids.append(hits[0]["id"])
    d = _get("/api/players/compare", ids=ids)
    return {"players": [{
        "name": p["name"], "nba_team": p["nba_team"], "positions": p["positions"], "status": p["status"], "owner": p["owner"],
        "proj_fp_per_game": p["fpts"], "fp_per_game": p["window_fp"], "minutes_last_14_days": p["recent_mpg"],
        "minutes_season": p["season_mpg"], "games_played": p["games_played"], "spread": p["sd"], "floor": p["floor"],
        "ceiling": p["ceiling"], "last_10_fp": [g["fp"] for g in p["last_games"]], "games_upcoming": p["games"],
    } for p in d["players"]], "windows": d["windows"]}


@mcp.tool(annotations=READ_ONLY)
def scout_opponent() -> dict:
    """This week's opponent (and next week's, if known): record, roster with projections and games left, injuries,
    adds used this week and recent transactions."""
    d = _get("/api/scouting")
    if not d["opponents"]:
        return {"note": "No matchup imported yet (save the Yahoo Matchup page)."}
    return {"opponents": [{
        "week": o["week"], "team": o["team"], "score": o["score"], "games_left": o["games_left"],
        "adds_this_week": o["adds_this_week"],
        "injured_or_missing": [f"{r['name']} ({r['status'] or 'missed ' + str(r['missed_streak']) + ' games'})" for r in o["injured"]],
        "roster": [{"name": r["name"], "proj_fp": r["fpts"], "games_left": r["games_left"], "status": r["status"]} for r in o["roster"]],
        "recent_transactions": [t["description"] for t in o["transactions"]],
    } for o in d["opponents"]]}


@mcp.tool(annotations=READ_ONLY)
def get_scoring_profile() -> dict:
    """Where the user's fantasy points come from (points, rebounds, assists, steals, blocks, threes, turnovers) compared
    with the league average, the user's rank in each (1 = best), and how much each stat is worth in this league."""
    d = _get("/api/scoring-profile")
    me = next((t for t in d["teams"] if t["is_me"]), None)
    return {
        "stat_weights_and_league_share": d["categories"],
        "my_fp_per_category": me and me["by_category"], "league_average": d["league_average"], "my_rank": d["my_rank"],
        "teams_by_total": [(t["name"], t["total"]) for t in d["teams"]], "note": d["note"],
    }


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
