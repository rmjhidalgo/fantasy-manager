import { useEffect, useState } from "react";
import { api, type ScoringProfile } from "../../api";
import { card, errText, Loading } from "../../ui";

const NAMES: Record<string, string> = {
  PTS: "Points",
  REB: "Rebounds",
  AST: "Assists",
  ST: "Steals",
  BLK: "Blocks",
  "3PTM": "Threes",
  TO: "Turnovers",
};

function ordinal(n: number) {
  return n + (n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th");
}

export default function ProfilePanel() {
  const [d, setD] = useState<ScoringProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .scoringProfile()
      .then(setD)
      .catch((e) => setError(errText(e)));
  }, []);
  if (!d) return <Loading error={error} />;
  const me = d.teams.find((t) => t.is_me);
  if (!me) return <Loading error="Your team isn't known yet." />;
  const n = d.teams.length;
  const maxAbs = Math.max(...d.categories.map((c) => Math.max(Math.abs(me.by_category[c.key]), Math.abs(d.league_average[c.key]))), 1);

  return (
    <div className="space-y-4">
      <section className={card}>
        <h2 className="mb-1 font-semibold">Where your points come from</h2>
        <p className="mb-3 text-sm text-slate-500">
          FP per game by stat for your team (blue) and the league average (grey). Rank among {n} teams, 1st = best.
        </p>
        <div className="space-y-2">
          {d.categories.map((c) => {
            const mine = me.by_category[c.key];
            const avg = d.league_average[c.key];
            const rank = d.my_rank[c.key];
            const diff = mine - avg;
            return (
              <div key={c.key} className="grid grid-cols-[7rem_1fr_6.5rem] items-center gap-3 text-sm">
                <div>
                  {NAMES[c.key] ?? c.key} <span className="text-xs text-slate-500">×{c.weight}</span>
                </div>
                <div className="space-y-0.5">
                  <div className="h-2.5 rounded bg-blue-600" style={{ width: `${(Math.abs(mine) / maxAbs) * 100}%` }} />
                  <div className="h-2.5 rounded bg-slate-300 dark:bg-slate-600" style={{ width: `${(Math.abs(avg) / maxAbs) * 100}%` }} />
                </div>
                <div className="text-right tabular-nums">
                  {mine.toFixed(1)}{" "}
                  <span className={`text-xs ${diff >= 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>
                    ({diff >= 0 ? "+" : ""}
                    {diff.toFixed(1)})
                  </span>
                  <div className={`text-xs ${rank <= 3 ? "text-green-700 dark:text-green-400" : rank > n - 3 ? "text-red-700 dark:text-red-400" : "text-slate-500"}`}>
                    {ordinal(rank)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-xs text-slate-500">{d.note}</p>
      </section>

      <section className={card}>
        <h2 className="mb-1 font-semibold">What each stat is worth in this league</h2>
        <p className="mb-3 text-sm text-slate-500">Share of all fantasy points in the league, from each stat (starters of every team).</p>
        <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          {d.categories.map((c) => (
            <div key={c.key} className="rounded-md border border-slate-200 p-2 dark:border-slate-700">
              <div className="text-slate-500">{NAMES[c.key] ?? c.key}</div>
              <div className="text-lg font-semibold tabular-nums">{(c.league_share * 100).toFixed(1)}%</div>
              <div className="text-xs text-slate-500">{c.weight > 0 ? "+" : ""}
                {c.weight} per {c.key === "TO" ? "turnover" : "unit"}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Steals and blocks are worth 3 each here: a player who adds one more steal + block per game gains 6 FP/G, as much as 6
          extra points.
        </p>
      </section>

      <section className={card}>
        <h2 className="mb-2 font-semibold">Teams by starters' FP per game</h2>
        <table className="w-full text-sm">
          <tbody>
            {d.teams.map((t, i) => (
              <tr key={t.team_id} className={`border-t border-slate-100 dark:border-slate-800 ${t.is_me ? "bg-blue-50 font-medium dark:bg-blue-950" : ""}`}>
                <td className="py-1 pr-2 text-slate-500">{i + 1}</td>
                <td className="py-1 pr-2">{t.name}</td>
                <td className="py-1 text-right tabular-nums">{t.total.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
