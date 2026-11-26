import { useEffect, useMemo, useState } from "react";
import { api, type ScheduleGrid } from "../../api";
import { card, errText, Loading, select } from "../../ui";

// Cell shade by number of games in the week
function shade(n: number, max: number): string {
  if (n === 0) return "text-slate-300 dark:text-slate-600";
  const r = n / Math.max(max, 1);
  if (r >= 0.85) return "bg-green-200 font-semibold dark:bg-green-900";
  if (r >= 0.6) return "bg-green-100 dark:bg-green-950";
  if (r <= 0.4) return "bg-amber-100 dark:bg-amber-950";
  return "";
}

export default function SchedulePanel() {
  const [g, setG] = useState<ScheduleGrid | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<"team" | "playoffs" | "next" | "mine">("mine");

  useEffect(() => {
    api
      .schedule()
      .then(setG)
      .catch((e) => setError(errText(e)));
  }, []);

  const rows = useMemo(() => {
    if (!g) return [];
    const r = [...g.teams];
    if (sort === "playoffs") r.sort((a, b) => b.playoff_games - a.playoff_games || a.team.localeCompare(b.team));
    else if (sort === "next") r.sort((a, b) => (b.games[1] ?? 0) - (a.games[1] ?? 0) || a.team.localeCompare(b.team));
    else if (sort === "mine") r.sort((a, b) => b.my_players.length - a.my_players.length || a.team.localeCompare(b.team));
    else r.sort((a, b) => a.team.localeCompare(b.team));
    return r;
  }, [g, sort]);

  if (!g) return <Loading error={error} />;
  const maxPerCol = g.columns.map((_, i) => Math.max(...g.teams.map((t) => t.games[i])));

  return (
    <section className={card}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">Schedule grid: NBA games per week</h2>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-slate-500">Sort</span>
          <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} className={select}>
            <option value="mine">Your players' teams first</option>
            <option value="next">Most games next week</option>
            <option value="playoffs">Most playoff games</option>
            <option value="team">Team</option>
          </select>
        </label>
      </div>
      <p className="mb-3 text-sm text-slate-500">
        Games left this week, then each week to the end of the playoffs (shaded columns). Small number = back-to-backs that
        week. Green = more games than most teams, orange = fewer.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-center text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="sticky left-0 bg-white py-1 pr-2 text-left font-medium dark:bg-slate-900">Team</th>
              {g.columns.map((c) => (
                <th
                  key={c.start}
                  className={`px-1 py-1 font-medium ${c.playoff ? "bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300" : ""}`}
                  title={`${c.start} – ${c.end}`}
                >
                  {c.label}
                </th>
              ))}
              <th className="px-1 py-1 font-medium" title="Games in the playoff weeks">
                PO
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-y border-slate-200 font-semibold dark:border-slate-700">
              <td className="sticky left-0 bg-white py-1 pr-2 text-left dark:bg-slate-900" title="Sum of your active players' games">
                Your roster
              </td>
              {g.my_games.map((n, i) => (
                <td key={i} className={`px-1 py-1 tabular-nums ${g.columns[i].playoff ? "bg-violet-50 dark:bg-violet-950" : ""}`}>
                  {n}
                </td>
              ))}
              <td />
            </tr>
            {rows.map((r) => (
              <tr key={r.team} className="border-t border-slate-100 dark:border-slate-800">
                <td
                  className={`sticky left-0 bg-white py-1 pr-2 text-left dark:bg-slate-900 ${r.my_players.length ? "font-semibold text-blue-700 dark:text-blue-300" : ""}`}
                  title={r.my_players.join(", ")}
                >
                  {r.team}
                  {r.my_players.length > 0 && <span className="ml-1 font-normal text-slate-500">({r.my_players.length})</span>}
                </td>
                {r.games.map((n, i) => (
                  <td key={i} className={`px-1 py-1 tabular-nums ${shade(n, maxPerCol[i])} ${g.columns[i].playoff ? "ring-1 ring-inset ring-violet-200 dark:ring-violet-900" : ""}`}>
                    {n}
                    {r.back_to_backs[i] > 0 && <sub className="ml-0.5 text-[9px] text-slate-500">{r.back_to_backs[i]}</sub>}
                  </td>
                ))}
                <td className="px-1 py-1 font-semibold tabular-nums">{r.playoff_games}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {g.notes.map((n) => (
        <p key={n} className="mt-2 text-xs text-slate-500">
          {n}
        </p>
      ))}
    </section>
  );
}
