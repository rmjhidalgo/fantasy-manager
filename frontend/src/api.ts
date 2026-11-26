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
  suggested?: string;
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
    injury?: string | null;
    games_left: number | null;
  }[];
};

export type LineupDay = {
  date: string;
  slots: string[];
  best_expected: number;
  current_expected: number;
  il_moves: IlMove[];
  yahoo_url: string;
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

export type IlMove = { player_id: number; name: string; move: "to IL" | "activate"; reason: string };

export type AlertItem = {
  key: string;
  level: "danger" | "warn" | "info";
  title: string;
  detail: string;
  action: "lineup" | "streaming" | "import" | null;
  notify: boolean;
  player_id?: number;
  next_man_up?: {
    name: string;
    minutes_with: number;
    minutes_without: number;
    fpts_without: number;
    games_without: number;
    available: boolean;
    kind: string | null;
    yahoo_url: string | null;
  }[];
};

export type FreeAgent = {
  id: number;
  yahoo_id: number | null;
  name: string;
  nba_team: string | null;
  positions: string[];
  positions_estimated: boolean;
  status: string | null;
  missed_streak: number;
  injury?: string | null;
  kind: "FA" | "W" | "?";
  source: "page" | "nba";
  waiver_until: string | null;
  available_from: string;
  fpts: number;
  play_prob: number;
  window_fp: { L7?: number | null; L14?: number | null; L30?: number | null; S?: number | null };
  recent_mpg: number | null;
  season_mpg: number | null;
  pct_rostered: number | null;
  games: number;
  raw_expected: number;
  gain: number | null;
  drop: number | null;
  drop_name: string | null;
  vs_drop: number | null;
  note: string | null;
  yahoo_url: string;
};

export type FreeAgents = {
  window: string;
  window_label: string;
  days: string[];
  open_spots: number;
  drop_candidates: { id: number; name: string; fpts: number }[];
  pool: {
    from_pages: number;
    from_nba: number;
    available_as_of: string | null;
    rostered_as_of: string | null;
    rostered_count: number;
    from_transactions: number;
  };
  available_url: string;
  players: FreeAgent[];
};

export type Adds = {
  week: number | null;
  limit: number | null;
  used: number;
  left: number | null;
  manual: number | null;
  counted: number;
  counted_from: { when: string; description: string; adds: number }[];
  source: "you" | "transactions";
};

export type Streaming = {
  days: string[];
  window_label: string;
  adds_left: number;
  baseline: number;
  with_moves: number;
  gain: number;
  open_spots: number;
  min_gain: number;
  keep_tolerance: number;
  adds: Adds;
  moves: {
    date: string;
    add: {
      id: number;
      yahoo_id: number | null;
      name: string;
      nba_team: string | null;
      positions: string[];
      positions_estimated: boolean;
      kind: string;
      source: string;
      fpts: number;
      status: string | null;
    };
    drop: { id: number; name: string; fpts: number } | null;
    drop_is_streamer: boolean;
    games: number;
    game_dates: string[];
    gain: number;
    yahoo_url: string;
  }[];
};

export type MoveLogInput = {
  source: "suggested" | "free agents" | "streaming";
  add_name: string;
  add_yahoo_id?: number | null;
  add_nba_id?: number | null;
  drop_yahoo_id?: number | null;
  drop_name?: string | null;
  gain?: number | null;
  horizon?: Horizon | null;
};

export type MoveLogData = {
  performance: { total_net: number; moves_counted: number };
  moves: {
    result: { added_fp: number; added_games: number; dropped_fp: number; dropped_games: number; net: number } | null;
    id: number;
    created_at: string;
    source: string;
    horizon: string | null;
    add_name: string;
    drop_name: string | null;
    gain: number | null;
    status: "open" | "done" | "missed" | "not done" | "dismissed";
    resolved_at: string | null;
    note: string | null;
    yahoo_url: string;
  }[];
  transactions: { when: string; description: string; moves: { name: string; action: "add" | "drop" }[] }[];
};

export type AssistantStatus = {
  enabled: boolean;
  last_used: string | null;
  config_path: string | null;
  installed: boolean;
  outdated?: boolean;
  server_entry: Record<string, unknown>;
  claude_code_command: string;
  result?: { path: string; backup?: string; removed?: boolean };
};

export type TeamRoster = {
  id: number;
  name: string | null;
  is_me: boolean;
  players: { id: number; name: string; nba_team: string | null; positions: string[]; status: string | null; fpts: number }[];
};

export type TradePlayer = {
  id: number;
  name: string;
  nba_team: string | null;
  positions: string[];
  status: string | null;
  fpts: number;
  games: number;
  value: number;
  injury?: string | null;
  return_date?: string | null;
};

export type TradeSide = { id: number; name: string | null; gain: number; before: number; after: number; drops: TradePlayer[] };

export type TradeAnalysis = {
  horizon: Horizon;
  label: string;
  days: string[];
  effective: string;
  deadline: string | null;
  my_team: TradeSide;
  their_team: TradeSide;
  give: TradePlayer[];
  get: TradePlayer[];
  verdict: string;
  notes: string[];
  yahoo_url: string;
};

export type TradeIdeas = {
  horizon: Horizon;
  label: string;
  effective: string;
  deadline: string | null;
  notes: string[];
  trades: { team: { id: number; name: string | null }; give: TradePlayer; get: TradePlayer; my_gain: number; their_gain: number; yahoo_url: string }[];
};

export type ScheduleGrid = {
  columns: { label: string; start: string; end: string; playoff: boolean; current: boolean }[];
  teams: { team: string; games: number[]; back_to_backs: number[]; playoff_games: number; my_players: string[] }[];
  my_games: number[];
  notes: string[];
};

export type SearchHit = { id: number; name: string; nba_team: string | null; positions: string[]; owner: string };

export type ComparedPlayer = {
  id: number;
  name: string;
  nba_team: string | null;
  positions: string[];
  positions_estimated: boolean;
  status: string | null;
  owner: string;
  fpts: number;
  play_prob: number;
  window_fp: { L7?: number | null; L14?: number | null; L30?: number | null; S?: number | null };
  recent_mpg: number | null;
  season_mpg: number | null;
  games_played: number;
  sd: number | null;
  floor: number | null;
  ceiling: number | null;
  missed_streak: number;
  injury?: string | null;
  last_games: { date: string; fp: number; min: number | null }[];
  games: Record<string, number>;
  pct_rostered: number | null;
};

export type Scouting = {
  week: number | null;
  opponents: {
    week: number;
    team: { id: number; name: string | null; rank: number | null; record: string | null; points_for: number | null };
    score: { me: number | null; them: number | null; as_of: string | null } | null;
    roster: { name: string; nba_team: string | null; positions: string[]; status: string | null; fpts: number; games_left: number; on_il: boolean; missed_streak: number; injury?: string | null }[];
    injured: Scouting["opponents"][number]["roster"];
    games_left: number;
    adds_this_week: number | null;
    transactions: { when: string; description: string; moves: { name: string; action: "add" | "drop" }[] }[];
  }[];
};

export type ScoringProfile = {
  categories: { key: string; weight: number; league_share: number }[];
  teams: { team_id: number; name: string | null; is_me: boolean; total: number; by_category: Record<string, number>; share: Record<string, number> }[];
  league_average: Record<string, number>;
  my_rank: Record<string, number>;
  note?: string;
};

export type ChecklistItem = {
  key: "settings" | "schedule" | "my_team" | "matchup" | "league_home" | "transactions" | "available" | "taken";
  saved_at: string | null;
  status: "ok" | "old" | "missing" | "partial";
  teams_done?: number;
  teams_total?: number;
  missing_teams?: string[];
  players?: number;
};

export type Checklist = { league: { id: number; name: string | null } | null; setup: ChecklistItem[]; regular: ChecklistItem[] };

export type PlayoffOdds = {
  week?: number;
  weeks_left?: number;
  playoff_spots?: number;
  first_playoff_week?: number;
  seasons?: number;
  teams: {
    team_id: number;
    name: string | null;
    is_me: boolean;
    record: string;
    playoff_odds: number;
    avg_seed: number;
    proj_wins: number;
    seed_chances: number[];
  }[];
  what_if?: { win_this_week: number | null; lose_this_week: number | null; chance_to_win_this_week: number } | null;
  notes: string[];
};

export type SummarySettings = { enabled: boolean; time: string; horizon: Horizon };

export type DailySummary = {
  generated_at: string;
  settings: SummarySettings;
  items: { kind: string; title: string; detail: string; action: string | null; level: "info" | "warn" | "danger" }[];
};

export type Tuning = {
  days: number;
  games_tested: number;
  results: { name: string; weights: number[]; mae: number | null; games: number }[];
  current: number[];
  best: { name: string; weights: number[]; mae: number } | null;
  recommend: boolean;
  windows: string[];
};

export type Horizon = "A" | "B" | "C" | "D";

export type Suggestions = {
  horizon: Horizon;
  horizon_name: string;
  label: string;
  days: string[];
  weeks: { week: number | null; start: string; end: string }[];
  budget: number;
  adds: Adds;
  notes: string[];
  warnings?: string[];
  untouchable?: number[];
  drop_candidates?: { id: number; name: string; fpts: number }[];
  il_moves: { player_id: number; name: string; status: string }[];
  baseline: number;
  with_moves: number;
  win_before: number | null;
  win_after: number | null;
  min_gain: number;
  team_url: string;
  moves: {
    add: {
      id: number;
      yahoo_id: number | null;
      name: string;
      nba_team: string | null;
      positions: string[];
      positions_estimated: boolean;
      status: string | null;
      fpts: number;
      kind: "FA" | "W" | "?";
      source: string;
    };
    drop: { id: number; name: string; fpts: number; status: string | null } | null;
    type: "add" | "add/drop" | "waiver claim";
    first_day: string;
    games: number;
    games_dropped: number;
    gain: number;
    win_change: number | null;
    reasons: string[];
    yahoo_url: string;
  }[];
};

export type MatchupSide = {
  team_id: number;
  name: string | null;
  current: number;
  final_expected: number;
  final_p10: number;
  final_p90: number;
  games_left: number;
  days: { date: string; expected: number; actual: number; starters: number; pending: number; conflicts: number; from_page: boolean }[];
  players: {
    player_id: number;
    name: string;
    nba_team: string | null;
    positions: string[];
    status: string | null;
    fpts: number | null;
    days: Record<string, "pending" | "final" | "bench">;
    starts: number;
    benched: number;
  }[];
};

export type MatchupDetail = {
  matchup: {
    week: number;
    start_date: string;
    end_date: string;
    as_of: string | null;
    win_prob: number;
    me: MatchupSide;
    opp: MatchupSide;
    notes: string[];
    yahoo_url: string;
  } | null;
  history: { at: string; win_prob: number; my_final: number; opp_final: number }[];
};

export type NbaStatus = {
  injuries?: { count: number; refreshed_at: string | null };
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
  checklist: () => fetch("/api/import/checklist").then((r) => json<Checklist>(r)),
  playoffOdds: () => fetch("/api/playoff-odds").then((r) => json<PlayoffOdds>(r)),
  summary: () => fetch("/api/summary").then((r) => json<DailySummary>(r)),
  summarySettings: () => fetch("/api/summary/settings").then((r) => json<SummarySettings>(r)),
  setSummarySettings: (s: SummarySettings) =>
    fetch("/api/summary/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(s),
    }).then((r) => json<SummarySettings>(r)),
  tuning: () => fetch("/api/tuning").then((r) => json<Tuning>(r)),
  setTuning: (weights: number[] | null) =>
    fetch("/api/tuning", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weights }),
    }).then((r) => json<{ weights: number[] }>(r)),
  reprocess: () => fetch("/api/imports/reprocess", { method: "POST" }).then((r) => json<{ pages: number; errors: number }>(r)),
  teams: () => fetch("/api/teams").then((r) => json<{ teams: TeamRoster[] }>(r)),
  analyzeTrade: (other_team: number, give: number[], get: number[], horizon: Horizon) =>
    fetch("/api/trade/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ other_team, give, get, horizon }),
    }).then((r) => json<TradeAnalysis>(r)),
  findTrades: (horizon: Horizon) => fetch(`/api/trade/find?horizon=${horizon}`).then((r) => json<TradeIdeas>(r)),
  schedule: () => fetch("/api/schedule").then((r) => json<ScheduleGrid>(r)),
  searchPlayers: (q: string) => fetch(`/api/players/search?q=${encodeURIComponent(q)}`).then((r) => json<{ players: SearchHit[] }>(r)),
  comparePlayers: (ids: number[]) =>
    fetch(`/api/players/compare?${ids.map((i) => `ids=${i}`).join("&")}`).then((r) =>
      json<{ players: ComparedPlayer[]; windows: Record<string, [string, string]> }>(r),
    ),
  scouting: () => fetch("/api/scouting").then((r) => json<Scouting>(r)),
  scoringProfile: () => fetch("/api/scoring-profile").then((r) => json<ScoringProfile>(r)),
  logMove: (m: MoveLogInput) =>
    fetch("/api/move-log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(m),
      keepalive: true, // the click also opens Yahoo in a new tab
    }).then((r) => json<{ id: number }>(r)),
  moveLog: () => fetch("/api/move-log").then((r) => json<MoveLogData>(r)),
  setMoveStatus: (id: number, status: "open" | "dismissed") =>
    fetch(`/api/move-log/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }).then((r) => json<{ ok: boolean }>(r)),
  assistant: () => fetch("/api/assistant").then((r) => json<AssistantStatus>(r)),
  setAssistant: (enabled: boolean) =>
    fetch("/api/assistant", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }).then((r) => json<AssistantStatus>(r)),
  installAssistant: () => fetch("/api/assistant/install", { method: "POST" }).then((r) => json<AssistantStatus>(r)),
  uninstallAssistant: () => fetch("/api/assistant/uninstall", { method: "POST" }).then((r) => json<AssistantStatus>(r)),
  suggestions: (horizon: Horizon) => fetch(`/api/suggestions?horizon=${horizon}`).then((r) => json<Suggestions>(r)),
  untouchables: () => fetch("/api/untouchables").then((r) => json<{ player_ids: number[] }>(r)),
  setUntouchables: (player_ids: number[]) =>
    fetch("/api/untouchables", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_ids }),
    }).then((r) => json<{ player_ids: number[] }>(r)),
  matchup: () => fetch("/api/matchup").then((r) => json<MatchupDetail>(r)),
  alerts: () => fetch("/api/alerts").then((r) => json<{ league_id: number; alerts: AlertItem[] }>(r)),
  freeAgents: (window: string, position: string) =>
    fetch(`/api/free-agents?window=${window}${position ? `&position=${position}` : ""}`).then((r) => json<FreeAgents>(r)),
  streaming: (adds_left?: number) =>
    fetch(`/api/streaming${adds_left != null ? `?adds_left=${adds_left}` : ""}`).then((r) => json<Streaming>(r)),
  setAddsUsed: (week: number, used: number | null) =>
    fetch("/api/adds", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ week, used }),
    }).then((r) => json<Adds>(r)),
  nbaStatus: () => fetch("/api/nba/status").then((r) => json<NbaStatus>(r)),
  nbaRefresh: () => fetch("/api/nba/refresh", { method: "POST" }).then((r) => json<Record<string, unknown>>(r)),
  setPlayerMap: (yahoo_id: number, nba_id: number | null) =>
    fetch("/api/player-map", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yahoo_id, nba_id }),
    }).then((r) => json<{ ok: boolean }>(r)),
  watchFolder: () => fetch("/api/watch-folder").then((r) => json<WatchFolder>(r)),
  setWatchFolder: (folder: string | null, create = false) =>
    fetch("/api/watch-folder", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder, create }),
    }).then((r) => json<WatchFolder>(r)),
  version: () => fetch("/api/version").then((r) => json<VersionInfo>(r)),
};

export type VersionInfo = { current: string; latest: string | null; update_available: boolean; download_url: string };
