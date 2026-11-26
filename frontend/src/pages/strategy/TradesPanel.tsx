import { useEffect, useState } from "react";
import { api, type Horizon, type TeamRoster, type TradeAnalysis, type TradeIdeas } from "../../api";
import { btn, card, dayLabel, errText, Loading, Notice, select, StatusTag, YahooLink } from "../../ui";

const HORIZONS: [Horizon, string][] = [
  ["A", "This week"],
  ["B", "Next week"],
  ["C", "Next 5 weeks"],
  ["D", "Playoffs"],
];

function signed(x: number) {
  return `${x > 0 ? "+" : ""}${x.toFixed(1)}`;
}

function PlayerPicker({
  team,
  chosen,
  onToggle,
}: {
  team: TeamRoster | undefined;
  chosen: Set<number>;
  onToggle: (id: number) => void;
}) {
  if (!team) return null;
  return (
    <ul className="max-h-72 space-y-0.5 overflow-y-auto text-sm">
      {team.players.map((p) => (
        <li key={p.id}>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={chosen.has(p.id)} onChange={() => onToggle(p.id)} />
            <span>
              {p.name}
              <StatusTag status={p.status} />
            </span>
            <span className="ml-auto text-xs text-slate-500">
              {p.positions.join(",")} · {p.fpts.toFixed(1)}
            </span>
          </label>
        </li>
      ))}
    </ul>
  );
}

export default function TradesPanel() {
  const [teams, setTeams] = useState<TeamRoster[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<Horizon>("C");
  const [other, setOther] = useState<number | null>(null);
  const [give, setGive] = useState<Set<number>>(new Set());
  const [get, setGet] = useState<Set<number>>(new Set());
  const [result, setResult] = useState<TradeAnalysis | null>(null);
  const [ideas, setIdeas] = useState<TradeIdeas | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .teams()
      .then((r) => {
        setTeams(r.teams);
        setOther(r.teams.find((t) => !t.is_me)?.id ?? null);
      })
      .catch((e) => setError(errText(e)));
  }, []);

  if (!teams) return <Loading error={error} />;
  const me = teams.find((t) => t.is_me);
  const them = teams.find((t) => t.id === other);
  const toggle = (set: Set<number>, setter: (s: Set<number>) => void) => (id: number) => {
    const n = new Set(set);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    setter(n);
    setResult(null);
  };

  const analyze = (otherTeam: number, g: number[], r: number[]) => {
    setBusy(true);
    setError(null);
    api
      .analyzeTrade(otherTeam, g, r, horizon)
      .then(setResult)
      .catch((e) => setError(errText(e)))
      .finally(() => setBusy(false));
  };
  const find = () => {
    setBusy(true);
    setError(null);
    api
      .findTrades(horizon)
      .then(setIdeas)
      .catch((e) => setError(errText(e)))
      .finally(() => setBusy(false));
  };

  return (
    <div className="space-y-4">
      <section className={card}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">Trade analyzer</h2>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-slate-500">Horizon</span>
            <select
              value={horizon}
              onChange={(e) => {
                setHorizon(e.target.value as Horizon);
                setResult(null);
                setIdeas(null);
              }}
              className={select}
            >
              {HORIZONS.map(([k, l]) => (
                <option key={k} value={k}>
                  {k} · {l}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <div className="mb-1 text-sm font-medium">You give ({me?.name})</div>
            <PlayerPicker team={me} chosen={give} onToggle={toggle(give, setGive)} />
          </div>
          <div>
            <div className="mb-1 flex items-center gap-2 text-sm font-medium">
              You get from
              <select
                value={other ?? ""}
                onChange={(e) => {
                  setOther(Number(e.target.value));
                  setGet(new Set());
                  setResult(null);
                }}
                className={select}
              >
                {teams
                  .filter((t) => !t.is_me)
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
              </select>
            </div>
            <PlayerPicker team={them} chosen={get} onToggle={toggle(get, setGet)} />
          </div>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <button className={btn} disabled={busy || !give.size || !get.size || other == null} onClick={() => analyze(other!, [...give], [...get])}>
            Analyze trade
          </button>
          {busy && <span className="text-sm text-slate-500">Working it out…</span>}
          {error && <span className="text-sm text-red-600 dark:text-red-400">{error}</span>}
        </div>

        {result && <TradeResult r={result} />}
      </section>

      <section className={card}>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">Trade finder</h2>
          <button className={btn} disabled={busy} onClick={find}>
            Find trades that help both teams
          </button>
        </div>
        <p className="mb-3 text-sm text-slate-500">
          1-for-1 trades with every team where <b>both</b> lineups gain over the horizon, so the other manager has a reason to say
          yes. Players of similar value are paired; your untouchables are never offered.
        </p>
        {ideas &&
          (ideas.trades.length === 0 ? (
            <Notice tone="info">No 1-for-1 trade helps both sides for this horizon.</Notice>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="text-left text-slate-500">
                  <tr>
                    <th className="py-1 pr-2 font-medium">With</th>
                    <th className="py-1 pr-2 font-medium">You give</th>
                    <th className="py-1 pr-2 font-medium">You get</th>
                    <th className="py-1 pr-2 text-right font-medium">You</th>
                    <th className="py-1 pr-2 text-right font-medium">Them</th>
                    <th className="py-1 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {ideas.trades.map((t, i) => (
                    <tr key={i} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="py-1.5 pr-2">{t.team.name}</td>
                      <td className="py-1.5 pr-2">
                        {t.give.name} <span className="text-xs text-slate-500">{t.give.fpts.toFixed(1)}</span>
                        <StatusTag status={t.give.status} />
                      </td>
                      <td className="py-1.5 pr-2">
                        {t.get.name} <span className="text-xs text-slate-500">{t.get.fpts.toFixed(1)}</span>
                        <StatusTag status={t.get.status} />
                      </td>
                      <td className="py-1.5 pr-2 text-right font-semibold tabular-nums text-green-700 dark:text-green-400">{signed(t.my_gain)}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{signed(t.their_gain)}</td>
                      <td className="py-1.5 text-right">
                        <button
                          className="text-xs text-blue-700 hover:underline dark:text-blue-300"
                          onClick={() => {
                            setOther(t.team.id);
                            setGive(new Set([t.give.id]));
                            setGet(new Set([t.get.id]));
                            analyze(t.team.id, [t.give.id], [t.get.id]);
                          }}
                        >
                          Details
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        {ideas?.notes.map((n) => (
          <p key={n} className="mt-2 text-xs text-slate-500">
            {n}
          </p>
        ))}
      </section>
    </div>
  );
}

function TradeResult({ r }: { r: TradeAnalysis }) {
  const tone = r.my_team.gain > 0 && r.their_team.gain > 0 ? "ok" : r.my_team.gain > 0 ? "info" : "warn";
  return (
    <div className="mt-4 space-y-3">
      <Notice tone={tone}>
        <b>{r.verdict}</b> over {r.label}
        {r.days.length > 0 && ` (${dayLabel(r.days[0])} – ${dayLabel(r.days[1])})`}. Takes effect {dayLabel(r.effective)} after the
        league's review period.
        {r.deadline && ` Trade deadline: ${dayLabel(r.deadline)}.`}
      </Notice>
      <div className="grid gap-3 md:grid-cols-2">
        {[r.my_team, r.their_team].map((s, i) => (
          <div key={s.id} className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
            <div className="text-sm text-slate-500">{s.name}</div>
            <div className={`text-2xl font-semibold tabular-nums ${s.gain >= 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>
              {signed(s.gain)} pts
            </div>
            <div className="text-xs text-slate-500">
              Lineup points {s.before.toFixed(0)} → {s.after.toFixed(0)}
            </div>
            {s.drops.length > 0 && (
              <div className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                Must drop to fit: {s.drops.map((d) => d.name).join(", ")}
              </div>
            )}
            {i === 1 && (
              <div className="mt-1">
                <YahooLink href={r.yahoo_url}>Their team on Yahoo ↗</YahooLink>
              </div>
            )}
          </div>
        ))}
      </div>
      <table className="w-full text-sm">
        <thead className="text-left text-slate-500">
          <tr>
            <th className="py-1 pr-2 font-medium"></th>
            <th className="py-1 pr-2 font-medium">Player</th>
            <th className="py-1 pr-2 text-right font-medium">FP/G</th>
            <th className="py-1 pr-2 text-right font-medium">Games</th>
            <th className="py-1 text-right font-medium" title="Expected points over the horizon, before lineup limits">
              Value
            </th>
          </tr>
        </thead>
        <tbody>
          {(
            [
              ["Give", r.give],
              ["Get", r.get],
            ] as const
          ).flatMap(([side, ps]) =>
            ps.map((p) => (
              <tr key={side + p.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className={`py-1 pr-2 text-xs font-medium ${side === "Get" ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>{side}</td>
                <td className="py-1 pr-2">
                  {p.name}
                  <StatusTag status={p.status} /> <span className="text-xs text-slate-500">{p.nba_team}</span>
                </td>
                <td className="py-1 pr-2 text-right tabular-nums">{p.fpts.toFixed(1)}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{p.games}</td>
                <td className="py-1 text-right tabular-nums">{p.value.toFixed(0)}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
      {r.notes.map((n) => (
        <p key={n} className="text-xs text-slate-500">
          {n}
        </p>
      ))}
      <p className="text-xs text-slate-500">
        Points change = what actually ends up in each team's daily lineups, so position fit and schedules count, not just FP/G.
        Propose trades on Yahoo.
      </p>
    </div>
  );
}
