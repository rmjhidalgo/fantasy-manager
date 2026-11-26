import { useCallback, useEffect, useState } from "react";
import { api, type Horizon, type LineupDay, type Outlook, type Suggestions } from "../api";
import { card, dayLabel, errText, Loading, Notice, StatusTag, YahooLink } from "../ui";

const HORIZONS: { key: Horizon; name: string; aim: string }[] = [
  { key: "A", name: "A · This week", aim: "Chance to win this matchup" },
  { key: "B", name: "B · Next week", aim: "Points next week" },
  { key: "C", name: "C · Next 5 weeks", aim: "Longer-term points" },
  { key: "D", name: "D · Playoffs", aim: "Points in playoff weeks" },
];

const pct = (x: number) => `${Math.round(x * 1000) / 10}%`;

export default function SuggestPage({ outlook }: { outlook: Outlook | null }) {
  const [horizon, setHorizon] = useState<Horizon>("A");
  const [data, setData] = useState<Suggestions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lineup, setLineup] = useState<LineupDay | null>(null);

  const load = useCallback(() => {
    setBusy(true);
    api
      .suggestions(horizon)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(errText(e)))
      .finally(() => setBusy(false));
  }, [horizon]);

  useEffect(load, [load]);
  useEffect(() => {
    if (horizon === "A") api.lineup().then(setLineup).catch(() => setLineup(null));
  }, [horizon]);

  const lineupChanges = lineup?.players.filter((p) => p.change === "start" || p.change === "bench") ?? [];
  const lineupGain = lineup ? lineup.best_expected - lineup.current_expected : 0;

  return (
    <div className="space-y-4">
      <section className={card}>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {HORIZONS.map((h) => (
            <button
              key={h.key}
              onClick={() => setHorizon(h.key)}
              className={`rounded-md border px-3 py-2 text-left text-sm ${
                horizon === h.key
                  ? "border-blue-600 bg-blue-50 dark:bg-blue-950"
                  : "border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
              }`}
            >
              <div className="font-medium">{h.name}</div>
              <div className="text-xs text-slate-500">{h.aim}</div>
            </button>
          ))}
        </div>
      </section>

      {!data ? (
        <Loading error={error} />
      ) : (
        <>
          {(data.warnings ?? []).map((w) => (
            <Notice key={w} tone="warn">
              ⚠ {w}
            </Notice>
          ))}

          <section className={card}>
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-semibold">
                {data.horizon_name}: {data.label}{" "}
                {data.days.length > 0 && (
                  <span className="text-sm font-normal text-slate-500">
                    ({dayLabel(data.days[0])} – {dayLabel(data.days[data.days.length - 1])})
                  </span>
                )}
              </h2>
              {busy && <span className="text-sm text-slate-500">Working it out…</span>}
            </div>
            <p className="mb-3 text-sm text-slate-500">
              Budget: <b>{data.budget}</b> add{data.budget !== 1 && "s"}
              {data.horizon === "B"
                ? " (adds reset on Monday)"
                : data.adds.limit != null && ` (${data.adds.used} of ${data.adds.limit} used this week — set it on the Streaming tab)`}
              . Your lineups: {data.baseline.toFixed(0)} pts as things stand
              {data.moves.length > 0 && (
                <>
                  {" "}
                  → <b>{data.with_moves.toFixed(0)}</b> with these moves (+{(data.with_moves - data.baseline).toFixed(1)})
                </>
              )}
              .
              {data.win_before != null && (
                <>
                  {" "}
                  Chance to win: {pct(data.win_before)}
                  {data.win_after != null && (
                    <>
                      {" "}
                      → <b>{pct(data.win_after)}</b>
                    </>
                  )}
                  .
                </>
              )}
            </p>

            {data.horizon === "A" && lineupChanges.length > 0 && lineupGain > 0.5 && (
              <div className="mb-3">
                <Notice tone="warn">
                  <b>Lineup today (+{lineupGain.toFixed(1)} pts):</b>{" "}
                  {lineupChanges.map((c) => `${c.change === "start" ? "start" : "bench"} ${c.name}`).join(", ")}.{" "}
                  {lineup && <YahooLink href={lineup.yahoo_url}>Set lineup on Yahoo ↗</YahooLink>}
                </Notice>
              </div>
            )}

            {data.il_moves.length > 0 && (
              <div className="mb-3">
                <Notice tone="warn">
                  {data.il_moves.map((m) => (
                    <div key={m.player_id}>
                      <b>First: move {m.name} ({m.status}) to IL</b> — opens a roster spot, so a pickup needs no drop.{" "}
                      <YahooLink href={data.team_url}>Team page ↗</YahooLink>
                    </div>
                  ))}
                </Notice>
              </div>
            )}

            {data.moves.length === 0 ? (
              <Notice tone="ok">
                <b>Hold.</b>{" "}
                {data.budget === 0
                  ? "No adds left to use."
                  : data.days.length === 0
                    ? "No days to plan for yet."
                    : `No move gains at least ${data.min_gain} points over this horizon${data.horizon === "A" || data.horizon === "B" ? " without giving up a better player" : ""}.`}
              </Notice>
            ) : (
              <ol className="space-y-3">
                {data.moves.map((m, i) => (
                  <li key={i} className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                          {i + 1}. {m.type} · {data.horizon === "A" ? `counts from ${dayLabel(m.first_day)}` : `${m.games} games in window`}
                        </div>
                        <div className="mt-0.5">
                          <span className="font-semibold text-green-700 dark:text-green-400">Add</span> {m.add.name}
                          <StatusTag status={m.add.status} />{" "}
                          <span className="text-xs text-slate-500">
                            {m.add.nba_team} · {m.add.positions.join(",")}
                            {m.add.positions_estimated && "*"} · {m.add.fpts.toFixed(1)} FP/G
                          </span>
                        </div>
                        {m.drop && (
                          <div>
                            <span className="font-semibold text-red-700 dark:text-red-400">Drop</span> {m.drop.name}
                            <StatusTag status={m.drop.status} />{" "}
                            <span className="text-xs text-slate-500">{m.drop.fpts.toFixed(1)} FP/G</span>
                          </div>
                        )}
                        <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-sm text-slate-600 dark:text-slate-300">
                          {m.reasons.map((r) => (
                            <li key={r}>{r}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-semibold tabular-nums">+{m.gain.toFixed(1)}</div>
                        <div className="text-xs text-slate-500">pts</div>
                        {m.win_change != null && Math.abs(m.win_change) >= 0.001 && (
                          <div className="text-xs text-slate-500">
                            {m.win_change > 0 ? "+" : ""}
                            {(m.win_change * 100).toFixed(1)}% win
                          </div>
                        )}
                        <div className="mt-1">
                          <YahooLink href={m.yahoo_url}>{m.add.yahoo_id ? "Add on Yahoo ↗" : "Find on Yahoo ↗"}</YahooLink>
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}

            {data.notes.map((n) => (
              <p key={n} className="mt-2 text-xs text-slate-500">
                {n}
              </p>
            ))}
            <p className="mt-2 text-xs text-slate-500">
              Gains are worked out with the lineup optimizer over every day of the horizon: only points that would end up in your
              lineup count. Moves are listed in the order chosen; each gain assumes the moves above it. You make every move on
              Yahoo.
            </p>
          </section>

          <Untouchables outlook={outlook} onChange={load} dropCandidates={data.drop_candidates ?? []} />
        </>
      )}
    </div>
  );
}

function Untouchables({
  outlook,
  onChange,
  dropCandidates,
}: {
  outlook: Outlook | null;
  onChange: () => void;
  dropCandidates: { id: number; name: string }[];
}) {
  const [ids, setIds] = useState<Set<number> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .untouchables()
      .then((r) => setIds(new Set(r.player_ids)))
      .catch((e) => setError(errText(e)));
  }, []);

  if (!outlook || !ids) return error ? <Loading error={error} /> : null;
  const toggle = (pid: number) => {
    const next = new Set(ids);
    if (next.has(pid)) next.delete(pid);
    else next.add(pid);
    setIds(next);
    api
      .setUntouchables([...next])
      .then(onChange)
      .catch((e) => setError(errText(e)));
  };
  const roster = [...outlook.roster].sort((a, b) => (b.fpts ?? 0) - (a.fpts ?? 0));

  return (
    <section className={card}>
      <h2 className="mb-1 font-semibold">Untouchables</h2>
      <p className="mb-2 text-sm text-slate-500">
        Ticked players are never suggested as drops. Now considered for dropping:{" "}
        {dropCandidates.length ? dropCandidates.map((d) => d.name).join(", ") : "nobody"}.
      </p>
      <div className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {roster.map((r) => (
          <label key={r.player_id} className="flex items-center gap-2">
            <input type="checkbox" checked={ids.has(r.player_id)} onChange={() => toggle(r.player_id)} />
            <span>{r.name}</span>
            <span className="text-xs text-slate-500">{r.fpts?.toFixed(1) ?? "–"} FP/G</span>
          </label>
        ))}
      </div>
      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
    </section>
  );
}
