import { useEffect, useState } from "react";
import { api, type ComparedPlayer, type SearchHit } from "../../api";
import { card, errText, InjuryNote, Notice, StatusTag } from "../../ui";

const WINDOW_LABELS: Record<string, string> = {
  rest_of_week: "Rest of week",
  next_7: "Next 7 days",
  next_14: "Next 14 days",
  playoffs: "Playoffs",
};

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const w = 120;
  const h = 32;
  const max = Math.max(...values, 1);
  const pts = values.map((v, i) => `${((i * w) / (values.length - 1)).toFixed(1)},${(h - (v / max) * (h - 2) - 1).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-8 w-full" role="img" aria-label="Last games">
      <polyline points={pts} fill="none" className="stroke-blue-600" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export default function ComparePanel() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [chosen, setChosen] = useState<SearchHit[]>([]);
  const [data, setData] = useState<ComparedPlayer[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const t = setTimeout(() => {
      api
        .searchPlayers(q.trim())
        .then((r) => setHits(r.players))
        .catch(() => setHits([]));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    if (chosen.length === 0) {
      setData(null);
      return;
    }
    api
      .comparePlayers(chosen.map((c) => c.id))
      .then((r) => {
        setData(r.players);
        setError(null);
      })
      .catch((e) => setError(errText(e)));
  }, [chosen]);

  const add = (h: SearchHit) => {
    if (chosen.length < 4 && !chosen.some((c) => c.id === h.id)) setChosen([...chosen, h]);
    setQ("");
    setHits([]);
  };

  const rows: [string, (p: ComparedPlayer) => React.ReactNode][] = [
    ["Owner", (p) => p.owner],
    ["Projection (FP/G)", (p) => <b>{p.fpts.toFixed(1)}</b>],
    ["Last 7 days", (p) => p.window_fp.L7?.toFixed(1) ?? "–"],
    ["Last 14 days", (p) => p.window_fp.L14?.toFixed(1) ?? "–"],
    ["Last 30 days", (p) => p.window_fp.L30?.toFixed(1) ?? "–"],
    ["Season", (p) => p.window_fp.S?.toFixed(1) ?? "–"],
    ["Minutes (14 days / season)", (p) => `${p.recent_mpg ?? "–"} / ${p.season_mpg ?? "–"}`],
    ["Games played", (p) => p.games_played],
    ["Floor – ceiling", (p) => (p.floor != null ? `${p.floor} – ${p.ceiling}` : "–")],
    ["Spread (± FP)", (p) => p.sd ?? "–"],
    ["Chance to play (today)", (p) => `${Math.round(p.play_prob * 100)}%`],
    ["Injury", (p) => (p.injury ? <InjuryNote text={p.injury} /> : "–")],
    ...Object.keys(WINDOW_LABELS).map(
      (k) => [`Games: ${WINDOW_LABELS[k]}`, (p: ComparedPlayer) => p.games[k] ?? "–"] as [string, (p: ComparedPlayer) => React.ReactNode],
    ),
    ["Last 10 games", (p) => <Sparkline values={p.last_games.map((g) => g.fp)} />],
  ];

  return (
    <section className={card}>
      <h2 className="mb-2 font-semibold">Compare players</h2>
      <div className="relative mb-3 max-w-md">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={chosen.length >= 4 ? "Up to 4 players" : "Type a player's name…"}
          disabled={chosen.length >= 4}
          className="w-full rounded-md border border-slate-300 bg-transparent px-3 py-1.5 text-sm dark:border-slate-700"
        />
        {hits.length > 0 && (
          <ul className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-slate-200 bg-white text-sm shadow dark:border-slate-700 dark:bg-slate-900">
            {hits.map((h) => (
              <li key={h.id}>
                <button onClick={() => add(h)} className="flex w-full justify-between gap-2 px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-800">
                  <span>
                    {h.name} <span className="text-xs text-slate-500">{h.nba_team}</span>
                  </span>
                  <span className="text-xs text-slate-500">{h.owner}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {chosen.length === 0 && <Notice>Pick up to 4 players: anyone in the NBA, rostered or not.</Notice>}
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {data && data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr>
                <th />
                {data.map((p) => (
                  <th key={p.id} className="px-2 py-1 text-left align-top font-medium">
                    {p.name}
                    <StatusTag status={p.status} />
                    <div className="text-xs font-normal text-slate-500">
                      {p.nba_team} · {p.positions.join(",")}
                      {p.positions_estimated && "*"}
                    </div>
                    <button onClick={() => setChosen(chosen.filter((c) => c.id !== p.id))} className="text-xs font-normal text-slate-500 hover:underline">
                      Remove
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(([label, f]) => (
                <tr key={label} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1 pr-2 text-slate-500">{label}</td>
                  {data.map((p) => (
                    <td key={p.id} className="px-2 py-1 tabular-nums">
                      {f(p)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-slate-500">
            Floor/ceiling = the 25th/75th percentile of his games this season. Games counted from today's NBA game day (US date).
          </p>
        </div>
      )}
    </section>
  );
}
