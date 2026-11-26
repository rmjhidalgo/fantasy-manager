// Types and calls for the backend API.

export type ImportResult = {
  filename: string;
  status: "imported" | "partial" | "duplicate" | "unsupported" | "error";
  page_type?: string | null;
  page_label?: string | null;
  league_name?: string | null;
  saved_at?: string | null;
  summary?: string | null;
  warnings: string[];
};

export type ImportHistoryRow = {
  filename: string;
  source: "upload" | "folder";
  status: ImportResult["status"];
  page_label: string | null;
  saved_at: string | null;
  imported_at: string;
  message: string | null;
};

export type WatchFolder = {
  configured: string | null;
  folder: string | null;
  running: boolean;
  recent: ImportResult[];
};

export type RosterRow = {
  player_id: number;
  slot: string;
  name: string;
  nba_team: string | null;
  positions: string | null;
  status: string | null;
  gp: number | null;
  fpts: number | null;
  mpg: number | null;
};

export type StandingRow = {
  team_id: number;
  name: string;
  rank: number;
  wins: number | null;
  losses: number | null;
  ties: number | null;
  points_for: number | null;
  waiver_priority: number | null;
  moves: number | null;
  is_me: boolean;
};

export type Overview = {
  league: { id: number; name: string | null; my_team_id: number | null; my_team_name: string | null } | null;
  settings?: {
    scoring: Record<string, number>;
    roster_positions: string[];
    max_adds_per_week: number | null;
    playoff_weeks: number[];
    trade_end_date: string | null;
  } | null;
  freshness?: Record<"settings" | "standings" | "my_roster" | "matchup" | "players" | "stats", string | null>;
  standings?: StandingRow[];
  my_roster?: RosterRow[];
  matchup?: {
    week: number;
    start_date: string | null;
    end_date: string | null;
    my_score: number | null;
    opp_score: number | null;
    opp_name: string | null;
    as_of: string | null;
  } | null;
  players?: {
    rostered_known: number;
    roster_spots_total: number | null;
    free_agents_known: number;
    waivers_known: number;
    stats_window: string | null;
  };
};

export type League = { id: number; name: string | null; my_team_id: number | null; my_team_name: string | null; active: boolean };

export type SideOutlook = {
  team_id: number;
  name: string | null;
  current: number;
  remaining_expected: number;
  final_expected: number;
  final_p10: number;
  final_p90: number;
  games_left: number;
  days: { date: string; expected: number; starters: number; pending: number }[];
};

export type Outlook = {
  today: string;
  matchup: {
    week: number;
    start_date: string;
    end_date: string;
    as_of: string | null;
    win_prob: number;
    me: SideOutlook;
    opp: SideOutlook;
    notes: string[];
  } | null;
  roster: {
    player_id: number;
    slot: string;
    name: string;
    fpts: number | null;
    sd: number | null;
    play_prob: number | null;
    source: "nba" | "yahoo" | "none";
    recent_mpg: number | null;
    season_mpg: number | null;
    games_left: number | null;
  }[];
};

export type LineupDay = {
  date: string;
  slots: string[];
  best_expected: number;
  current_expected: number;
  players: {
    player_id: number;
    name: string;
    positions: string[];
    status: string | null;
    current_slot: string;
    best_slot: string | null;
    change: "start" | "bench" | "no game" | null;
    locked: boolean;
    expected: number;
    game: { opponent: string; start_utc: string | null; final: boolean; started: boolean } | null;
  }[];
};

export type NbaStatus = {
  refreshed_at: string | null;
  season: string | null;
  games: number;
  game_logs: number;
  last_error: string | null;
  unmatched: {
    yahoo_id: number;
    name: string;
    nba_team: string | null;
    rostered: boolean;
    candidates: { nba_id: number; name: string; team: string | null }[];
  }[];
};

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const body = await r.json();
      detail = body.detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}

export const api = {
  overview: () => fetch("/api/overview").then((r) => json<Overview>(r)),
  leagues: () => fetch("/api/leagues").then((r) => json<{ leagues: League[] }>(r)),
  setActiveLeague: (league_id: number) =>
    fetch("/api/active-league", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ league_id }),
    }).then((r) => json<{ leagues: League[] }>(r)),
  imports: () => fetch("/api/imports?limit=30").then((r) => json<{ imports: ImportHistoryRow[] }>(r)),
  importFiles: (files: File[]) => {
    const fd = new FormData();
    for (const f of files) {
      fd.append("files", f, f.name);
      fd.append("last_modified", String(f.lastModified || 0));
    }
    return fetch("/api/import", { method: "POST", body: fd }).then((r) => json<{ results: ImportResult[] }>(r));
  },
  outlook: () => fetch("/api/outlook").then((r) => json<Outlook>(r)),
  lineup: (day?: string) => fetch(`/api/lineup${day ? `?day=${day}` : ""}`).then((r) => json<LineupDay>(r)),
  nbaStatus: () => fetch("/api/nba/status").then((r) => json<NbaStatus>(r)),
  nbaRefresh: () => fetch("/api/nba/refresh", { method: "POST" }).then((r) => json<Record<string, unknown>>(r)),
  setPlayerMap: (yahoo_id: number, nba_id: number | null) =>
    fetch("/api/player-map", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yahoo_id, nba_id }),
    }).then((r) => json<{ ok: boolean }>(r)),
  watchFolder: () => fetch("/api/watch-folder").then((r) => json<WatchFolder>(r)),
  setWatchFolder: (folder: string | null) =>
    fetch("/api/watch-folder", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder }),
    }).then((r) => json<WatchFolder>(r)),
};
