import { useEffect, useState } from "react";
import { api, type PlayoffOdds } from "../../api";
import { card, errText, Loading, Notice } from "../../ui";

const pct = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(x * 100)}%`);

export default function OddsPanel() {
  const [d, setD] = useState<PlayoffOdds | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .playoffOdds()
      .then(setD)
      .catch((e) => setError(errText(e)));
  }, []);
  if (!d) return <Loading error={error} />;
  if (d.teams.length === 0) return <Notice tone="warn">{d.notes.join(" ")}</Notice>;
  const me = d.teams.find((t) => t.is_me);
  const n = d.teams.length;
  const spots = d.playoff_spots ?? 8;

  return (
    <section className={card}>
      <h2 className="mb-1 font-semibold">Playoff odds</h2>
      <p className="mb-3 text-sm text-slate-500">
        The rest of the regular season ({d.weeks_left} weeks after this one) simulated {d.seasons?.toLocaleString()} times. Top{" "}
        {spots} make the playoffs (week {d.first_playoff_week}). Standings: wins, then points for.
      </p>
      {me && d.what_if && (
        <Notice tone="info">
          <b>You: {pct(me.playoff_odds)}</b>. Win this week → {pct(d.what_if.win_this_week)}, lose → {pct(d.what_if.lose_this_week)}{" "}
          (you're {pct(d.what_if.chance_to_win_this_week)} to win it).
        </Notice>
      )}
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-2 text-left font-medium">Team</th>
              <th className="py-1 pr-2 text-left font-medium">Record</th>
              <th className="py-1 pr-2 text-right font-medium">Playoffs</th>
              <th className="py-1 pr-2 text-right font-medium">Wins</th>
              <th className="py-1 pr-2 text-right font-medium">Seed</th>
              <th className="py-1 text-left font-medium">Chance of each seed (1 → {n})</th>
            </tr>
          </thead>
          <tbody>
            {d.teams.map((t) => (
              <tr key={t.team_id} className={`border-t border-slate-100 dark:border-slate-800 ${t.is_me ? "bg-blue-50 font-medium dark:bg-blue-950" : ""}`}>
                <td className="py-1 pr-2">{t.name}</td>
                <td className="py-1 pr-2 tabular-nums text-slate-500">{t.record}</td>
                <td className="py-1 pr-2 text-right font-semibold tabular-nums">{pct(t.playoff_odds)}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{t.proj_wins.toFixed(1)}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{t.avg_seed.toFixed(1)}</td>
                <td className="py-1">
                  <div className="flex gap-px">
                    {t.seed_chances.map((c, s) => (
                      <div
                        key={s}
                        title={`Seed ${s + 1}: ${pct(c)}`}
                        className={`h-4 w-4 rounded-sm ${s < spots ? "bg-blue-600" : "bg-slate-500"}`}
                        style={{ opacity: Math.max(0.06, Math.min(1, c * 2.5)) }}
                      />
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {d.notes.map((x) => (
        <p key={x} className="mt-2 text-xs text-slate-500">
          {x}
        </p>
      ))}
      <p className="mt-2 text-xs text-slate-500">
        Later weeks use each team's projected weekly score (best lineups, injured players gradually back) with normal week-to-week
        swings. Blue squares = playoff seeds; darker = more likely.
      </p>
    </section>
  );
}
