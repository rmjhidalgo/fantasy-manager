import type { Overview } from "../api";
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

export default function OverviewPage({ data, onGoImport }: { data: Overview | null; onGoImport: () => void }) {
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
  const m = data.matchup;
  const p = data.players!;

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

      {m && (
        <section className={card}>
          <h2 className="mb-1 font-semibold">
            Week {m.week} matchup{" "}
            <span className="text-sm font-normal text-slate-500">
              {m.start_date} – {m.end_date}
            </span>
          </h2>
          <div className="flex items-center justify-center gap-6 py-3 text-center">
            <div>
              <div className="text-sm text-slate-500">{data.league.my_team_name}</div>
              <div className="text-3xl font-semibold tabular-nums">{m.my_score?.toFixed(2) ?? "–"}</div>
            </div>
            <div className="text-slate-400">vs</div>
            <div>
              <div className="text-sm text-slate-500">{m.opp_name}</div>
              <div className="text-3xl font-semibold tabular-nums">{m.opp_score?.toFixed(2) ?? "–"}</div>
            </div>
          </div>
          <p className="text-center text-xs text-slate-500">Score as of {formatWhen(m.as_of)}</p>
        </section>
      )}

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
                  <th className="py-1 pr-2 text-right font-medium">FP/G</th>
                  <th className="py-1 text-right font-medium">MPG</th>
                </tr>
              </thead>
              <tbody>
                {data.my_roster!.map((r) => (
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
                      </div>
                    </td>
                    <td className="py-1 pr-2 text-right tabular-nums">{r.fpts?.toFixed(1) ?? "–"}</td>
                    <td className="py-1 text-right tabular-nums">{r.mpg?.toFixed(1) ?? "–"}</td>
                  </tr>
                ))}
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
