import { useEffect, useState } from "react";
import { api, type LineupDay, type Outlook, type Overview } from "../api";
import { formatWhen, hoursOld } from "../time";

const FRESHNESS_LABELS: [keyof NonNullable<Overview["freshness"]>, string, number][] = [
  // key, label, hours after which it's shown as stale
  ["my_roster", "My roster", 24],
  ["matchup", "Matchup", 24],
  ["players", "Free agents / owners", 48],
  ["stats", "Player stats", 72],
  ["standings", "Standings", 24 * 7],
  ["settings", "Settings", 24 * 60],
];

const card = "rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900";

function dayLabel(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString([], { weekday: "short", month: "numeric", day: "numeric" });
}

export default function OverviewPage({
  data,
  outlook,
  onGoImport,
}: {
  data: Overview | null;
  outlook: Outlook | null;
  onGoImport: () => void;
}) {
  if (!data) return <p className="text-slate-500">Loading…</p>;
  if (!data.league) {
    return (
      <div className={`${card} text-center`}>
        <p className="mb-3">No league data yet.</p>
        <button onClick={onGoImport} className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700">
          Import your saved Yahoo pages
        </button>
      </div>
    );
  }
  const f = data.freshness!;
  const p = data.players!;
  const proj = new Map((outlook?.roster ?? []).map((r) => [r.player_id, r]));

  return (
    <div className="space-y-6">
      <section className={card}>
        <h2 className="mb-3 font-semibold">Data as of</h2>
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
          {FRESHNESS_LABELS.map(([key, label, staleAfter]) => {
            const h = hoursOld(f[key]);
            const tone =
              h === null ? "text-red-600 dark:text-red-400" : h > staleAfter ? "text-amber-700 dark:text-amber-400" : "";
            return (
              <div key={key}>
                <div className="text-slate-500">{label}</div>
                <div className={tone}>
                  {f[key] ? formatWhen(f[key]) : "not imported"}
                  {h !== null && h > staleAfter && " · old"}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <MatchupCard data={data} outlook={outlook} />

      <LineupCard outlook={outlook} />

      <div className="grid gap-6 lg:grid-cols-2">
        <section className={card}>
          <h2 className="mb-3 font-semibold">My roster</h2>
          {data.my_roster!.length === 0 ? (
            <p className="text-sm text-slate-500">Import your My Team page to see your roster.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-1 pr-2 font-medium">Slot</th>
                  <th className="py-1 pr-2 font-medium">Player</th>
                  <th className="py-1 pr-2 text-right font-medium" title="Projected fantasy points per game played">
                    Proj
                  </th>
                  <th className="py-1 pr-2 text-right font-medium" title="Season fantasy points per game (Yahoo)">
                    Season
                  </th>
                  <th className="py-1 text-right font-medium" title="Games left this matchup week (not started yet)">
                    Left
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.my_roster!.map((r) => {
                  const pr = proj.get(r.player_id);
                  return (
                    <tr key={r.player_id} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="py-1 pr-2 text-slate-500">{r.slot}</td>
                      <td className="py-1 pr-2">
                        {r.name}{" "}
                        {r.status && (
                          <span className="rounded bg-red-100 px-1 text-xs font-medium text-red-700 dark:bg-red-950 dark:text-red-300">
                            {r.status}
                          </span>
                        )}
                        <div className="text-xs text-slate-500">
                          {r.nba_team} · {r.positions}
                          {pr?.recent_mpg != null && pr.season_mpg != null && Math.abs(pr.recent_mpg - pr.season_mpg) >= 3 && (
                            <span className={pr.recent_mpg > pr.season_mpg ? "text-green-700 dark:text-green-400" : "text-amber-700 dark:text-amber-400"}>
                              {" "}
                              · {pr.recent_mpg > pr.season_mpg ? "▲" : "▼"} {pr.recent_mpg} min lately
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-1 pr-2 text-right font-medium tabular-nums">{pr?.fpts?.toFixed(1) ?? "–"}</td>
                      <td className="py-1 pr-2 text-right tabular-nums text-slate-500">{r.fpts?.toFixed(1) ?? "–"}</td>
                      <td className="py-1 text-right tabular-nums">{pr?.games_left ?? "–"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>

        <section className={card}>
          <h2 className="mb-3 font-semibold">Standings</h2>
          {data.standings!.length === 0 ? (
            <p className="text-sm text-slate-500">Import the League home page to see standings.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-1 pr-2 font-medium">#</th>
                  <th className="py-1 pr-2 font-medium">Team</th>
                  <th className="py-1 pr-2 font-medium">W-L-T</th>
                  <th className="py-1 text-right font-medium">Points</th>
                </tr>
              </thead>
              <tbody>
                {data.standings!.map((s) => (
                  <tr
                    key={s.team_id}
                    className={`border-t border-slate-100 dark:border-slate-800 ${s.is_me ? "bg-blue-50 font-medium dark:bg-blue-950" : ""} ${s.rank === 8 ? "border-b-2 border-b-slate-300 dark:border-b-slate-600" : ""}`}
                  >
                    <td className="py-1 pr-2">{s.rank}</td>
                    <td className="py-1 pr-2">{s.name}</td>
                    <td className="py-1 pr-2 tabular-nums">
                      {s.wins}-{s.losses}-{s.ties}
                    </td>
                    <td className="py-1 text-right tabular-nums">{s.points_for?.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-2 text-xs text-slate-500">Line under 8th place = playoff cut.</p>
        </section>
      </div>

      <section className={card}>
        <h2 className="mb-2 font-semibold">Players known</h2>
        <ul className="space-y-1 text-sm">
          <li>
            Rostered: <b>{p.rostered_known}</b>
            {p.roster_spots_total ? ` (of up to ${p.roster_spots_total} roster spots)` : ""}
          </li>
          <li>
            Free agents: <b>{p.free_agents_known}</b>, on waivers: <b>{p.waivers_known}</b>
          </li>
          {p.stats_window && <li className="text-slate-500">Stats: {p.stats_window.startsWith("S_AS") ? "season averages" : p.stats_window}</li>}
        </ul>
      </section>
    </div>
  );
}

function MatchupCard({ data, outlook }: { data: Overview; outlook: Outlook | null }) {
  const m = data.matchup;
  const o = outlook?.matchup;
  if (!m) return null;
  const win = o ? Math.round(o.win_prob * 100) : null;
  return (
    <section className={card}>
      <h2 className="mb-1 font-semibold">
        Week {m.week} matchup{" "}
        <span className="text-sm font-normal text-slate-500">
          {m.start_date} – {m.end_date}
        </span>
      </h2>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 py-3 text-center">
        <div>
          <div className="text-sm text-slate-500">{data.league!.my_team_name}</div>
          <div className="text-3xl font-semibold tabular-nums">{m.my_score?.toFixed(2) ?? "–"}</div>
          {o && <div className="text-sm text-slate-500">→ projected {o.me.final_expected.toFixed(0)}</div>}
        </div>
        <div className="text-slate-400">vs</div>
        <div>
          <div className="text-sm text-slate-500">{m.opp_name}</div>
          <div className="text-3xl font-semibold tabular-nums">{m.opp_score?.toFixed(2) ?? "–"}</div>
          {o && <div className="text-sm text-slate-500">→ projected {o.opp.final_expected.toFixed(0)}</div>}
        </div>
      </div>

      {o && win !== null && (
        <>
          <div className="mb-1 flex justify-between text-sm">
            <span className="font-medium">Chance to win: {win}%</span>
            <span className="text-slate-500">
              Games left: {o.me.games_left} vs {o.opp.games_left}
            </span>
          </div>
          <div className="mb-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <div className="h-full bg-blue-600" style={{ width: `${win}%` }} />
          </div>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-1 font-medium">Day</th>
                <th className="py-1 text-right font-medium">You</th>
                <th className="py-1 text-right font-medium">Opponent</th>
              </tr>
            </thead>
            <tbody>
              {o.me.days.map((d, i) => {
                const od = o.opp.days[i];
                return (
                  <tr key={d.date} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1">{dayLabel(d.date)}</td>
                    <td className="py-1 text-right tabular-nums">
                      {d.expected.toFixed(0)} <span className="text-xs text-slate-500">({d.starters} play)</span>
                    </td>
                    <td className="py-1 text-right tabular-nums">
                      {od?.expected.toFixed(0)} <span className="text-xs text-slate-500">({od?.starters} play)</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-slate-500">
            Likely final range for you: {o.me.final_p10.toFixed(0)}–{o.me.final_p90.toFixed(0)}. Assumes both teams start their
            best available players each day.
          </p>
          {o.notes.map((n, i) => (
            <p key={i} className="mt-1 text-xs text-amber-700 dark:text-amber-400">
              {n}
            </p>
          ))}
        </>
      )}
      {!o && <p className="text-center text-xs text-slate-500">Score as of {formatWhen(m.as_of)}. Projections appear once NBA data is downloaded.</p>}
    </section>
  );
}

function LineupCard({ outlook }: { outlook: Outlook | null }) {
  const days = outlook?.matchup?.me.days.map((d) => d.date) ?? [];
  const [day, setDay] = useState<string | null>(null);
  const [data, setData] = useState<LineupDay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chosen = day ?? outlook?.today ?? null;

  useEffect(() => {
    if (!chosen) return;
    api
      .lineup(chosen)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [chosen, outlook]);

  if (!outlook) return null;
  const options = Array.from(new Set([outlook.today, ...days])).sort();
  const changes = data?.players.filter((p) => p.change === "start" || p.change === "bench") ?? [];
  const gain = data ? data.best_expected - data.current_expected : 0;

  return (
    <section className={card}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Best lineup</h2>
        <select
          value={chosen ?? ""}
          onChange={(e) => setDay(e.target.value)}
          className="rounded-md border border-slate-300 bg-transparent px-2 py-1 text-sm dark:border-slate-700"
        >
          {options.map((d) => (
            <option key={d} value={d}>
              {dayLabel(d)}
              {d === outlook.today ? " (today, US time)" : ""}
            </option>
          ))}
        </select>
      </div>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {data && (
        <>
          {changes.length > 0 && gain > 0.5 ? (
            <div className="mb-3 rounded-md bg-amber-50 p-3 text-sm dark:bg-amber-950">
              <b>Suggested changes (+{gain.toFixed(1)} expected pts):</b>{" "}
              {changes.map((c) => `${c.change === "start" ? "Start" : "Bench"} ${c.name}`).join(", ")}
              <div className="text-xs text-slate-500">Compared with the lineup on your last imported My Team page.</div>
            </div>
          ) : (
            <p className="mb-3 text-sm text-green-700 dark:text-green-400">✓ Your imported lineup is already the best for this day.</p>
          )}
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-1 pr-2 font-medium">Slot</th>
                <th className="py-1 pr-2 font-medium">Player</th>
                <th className="py-1 pr-2 font-medium">Game</th>
                <th className="py-1 text-right font-medium">Exp.</th>
              </tr>
            </thead>
            <tbody>
              {data.players.map((p) => (
                <tr key={p.player_id} className={`border-t border-slate-100 dark:border-slate-800 ${p.best_slot ? "" : "text-slate-400"}`}>
                  <td className="py-1 pr-2">{p.best_slot ?? "—"}</td>
                  <td className="py-1 pr-2">
                    {p.name}
                    {p.status && <span className="ml-1 text-xs text-red-600 dark:text-red-400">{p.status}</span>}
                    {p.change === "start" && <span className="ml-1 text-xs text-green-700 dark:text-green-400">start</span>}
                    {p.change === "bench" && <span className="ml-1 text-xs text-amber-700 dark:text-amber-400">bench</span>}
                  </td>
                  <td className="py-1 pr-2 text-xs">
                    {p.game ? p.game.opponent : "no game"}
                    {p.game && !p.game.started && p.game.start_utc && (
                      <span className="text-slate-500">
                        {" "}
                        {new Date(p.game.start_utc).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    )}
                    {p.locked && <span className="text-slate-500"> · 🔒 started</span>}
                  </td>
                  <td className="py-1 text-right tabular-nums">{p.expected ? p.expected.toFixed(1) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
