import { useEffect, useState } from "react";
import { api, type MatchupDetail, type MatchupSide } from "../api";
import { formatWhen } from "../time";
import { card, dayLabel, errText, Loading, shortDay, StatusTag, YahooLink } from "../ui";

export default function MatchupPage({ version }: { version: number }) {
  const [data, setData] = useState<MatchupDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .matchup()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(errText(e)));
  }, [version]);

  if (!data) return <Loading error={error} />;
  const m = data.matchup;
  if (!m) return <p className="text-slate-500">Import your Matchup page (and wait for NBA data) to see the matchup.</p>;
  const win = Math.round(m.win_prob * 100);

  return (
    <div className="space-y-6">
      <section className={card}>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-semibold">
            Week {m.week} <span className="text-sm font-normal text-slate-500">{dayLabel(m.start_date)} – {dayLabel(m.end_date)}</span>
          </h2>
          <YahooLink href={m.yahoo_url} />
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 py-2 text-center">
          <Score side={m.me} />
          <div className="text-slate-400">vs</div>
          <Score side={m.opp} />
        </div>
        <div className="mb-1 flex justify-between text-sm">
          <span className="font-medium">Chance to win: {win}%</span>
          <span className="text-slate-500">Score saved {formatWhen(m.as_of)}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
          <div className="h-full bg-blue-600" style={{ width: `${win}%` }} />
        </div>
        {data.history.length > 1 && <History points={data.history} />}
        {m.notes.map((n, i) => (
          <p key={i} className="mt-2 text-xs text-amber-700 dark:text-amber-400">
            {n}
          </p>
        ))}
      </section>

      <section className={card}>
        <h2 className="mb-2 font-semibold">Day by day</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500">
            <tr>
              <th className="py-1 font-medium">Day</th>
              <th className="py-1 text-right font-medium">{m.me.name ?? "You"}</th>
              <th className="py-1 text-right font-medium">{m.opp.name ?? "Opponent"}</th>
            </tr>
          </thead>
          <tbody>
            {m.me.days.map((d, i) => {
              const od = m.opp.days[i];
              return (
                <tr key={d.date} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1">{dayLabel(d.date)}</td>
                  <DayCell d={d} />
                  {od ? <DayCell d={od} /> : <td />}
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-500">
          Points: real box scores for finished games, expected points for the rest. "Benched" = players with a game but no slot
          that day (slot conflicts). Likely final: you {m.me.final_p10.toFixed(0)}–{m.me.final_p90.toFixed(0)}, opponent{" "}
          {m.opp.final_p10.toFixed(0)}–{m.opp.final_p90.toFixed(0)}.
        </p>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <PlayerGrid side={m.me} days={m.me.days.map((d) => d.date)} />
        <PlayerGrid side={m.opp} days={m.opp.days.map((d) => d.date)} />
      </div>
    </div>
  );
}

function Score({ side }: { side: MatchupSide }) {
  return (
    <div>
      <div className="text-sm text-slate-500">{side.name}</div>
      <div className="text-3xl font-semibold tabular-nums">{side.current.toFixed(2)}</div>
      <div className="text-sm text-slate-500">
        → {side.final_expected.toFixed(0)} · {side.games_left} games left
      </div>
    </div>
  );
}

function DayCell({ d }: { d: MatchupSide["days"][number] }) {
  return (
    <td className="py-1 text-right tabular-nums">
      {d.expected.toFixed(0)}{" "}
      <span className="text-xs text-slate-500">
        ({d.starters} play{d.conflicts > 0 && <span className="text-amber-700 dark:text-amber-400">, {d.conflicts} benched</span>})
      </span>
    </td>
  );
}

function PlayerGrid({ side, days }: { side: MatchupSide; days: string[] }) {
  return (
    <section className={card}>
      <h2 className="mb-2 font-semibold">{side.name}: games left</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-2 text-left font-medium">Player</th>
              {days.map((d) => (
                <th key={d} className="px-1 py-1 text-center text-xs font-medium">
                  {shortDay(d)}
                </th>
              ))}
              <th className="py-1 pl-2 text-right font-medium">Proj</th>
            </tr>
          </thead>
          <tbody>
            {side.players.map((p) => (
              <tr key={p.player_id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1 pr-2">
                  {p.name}
                  <StatusTag status={p.status} />
                  <div className="text-xs text-slate-500">
                    {p.nba_team} · {p.positions.join(",")}
                  </div>
                </td>
                {days.map((d) => {
                  const s = p.days[d];
                  return (
                    <td key={d} className="px-1 py-1 text-center">
                      {s === "pending" && <span title="Plays (projected starter)" className="inline-block h-2.5 w-2.5 rounded-full bg-blue-600" />}
                      {s === "final" && <span title="Played (finished)" className="text-xs text-slate-500">✓</span>}
                      {s === "bench" && (
                        <span title="Has a game but no free slot" className="inline-block h-2.5 w-2.5 rounded-full border-2 border-amber-500" />
                      )}
                    </td>
                  );
                })}
                <td className="py-1 pl-2 text-right tabular-nums">{p.fpts?.toFixed(1) ?? "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        <span className="inline-block h-2 w-2 rounded-full bg-blue-600" /> plays ·{" "}
        <span className="inline-block h-2 w-2 rounded-full border-2 border-amber-500" /> game but no slot · ✓ finished since the score
        was saved
      </p>
    </section>
  );
}

function History({ points }: { points: MatchupDetail["history"] }) {
  const w = 600;
  const h = 90;
  const pad = 6;
  const x = (i: number) => pad + (i * (w - 2 * pad)) / Math.max(1, points.length - 1);
  const y = (p: number) => h - pad - p * (h - 2 * pad);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.win_prob).toFixed(1)}`).join(" ");
  return (
    <div className="mt-3">
      <div className="mb-1 text-xs text-slate-500">Chance to win after each data update this week</div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-auto w-full" role="img" aria-label="Win chance history">
        <line x1={pad} x2={w - pad} y1={y(0.5)} y2={y(0.5)} className="stroke-slate-300 dark:stroke-slate-600" strokeDasharray="4 4" />
        <path d={path} fill="none" className="stroke-blue-600" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        {points.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.win_prob)} r={3} className="fill-blue-600">
            <title>
              {formatWhen(p.at)}: {Math.round(p.win_prob * 100)}% ({p.my_final.toFixed(0)}–{p.opp_final.toFixed(0)})
            </title>
          </circle>
        ))}
      </svg>
    </div>
  );
}
