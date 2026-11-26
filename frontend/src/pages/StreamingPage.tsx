import { useCallback, useEffect, useState } from "react";
import { api, type Streaming } from "../api";
import { card, dayLabel, errText, Loading, Notice, select, shortDay, StatusTag, YahooLink } from "../ui";

export default function StreamingPage() {
  const [data, setData] = useState<Streaming | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setBusy(true);
    api
      .streaming()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(errText(e)))
      .finally(() => setBusy(false));
  }, []);

  useEffect(load, [load]);

  if (!data) return <Loading error={error} />;
  const a = data.adds;

  const setUsed = (v: string) => {
    if (a.week == null) return;
    setBusy(true);
    api
      .setAddsUsed(a.week, v === "" ? null : Number(v))
      .then(load)
      .catch((e) => {
        setError(errText(e));
        setBusy(false);
      });
  };

  return (
    <div className="space-y-4">
      <section className={card}>
        <h2 className="mb-2 font-semibold">Adds this week</h2>
        {a.limit == null ? (
          <p className="text-sm text-slate-500">Import the league Settings page to know the weekly add limit.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span>
              <b>{a.used}</b> of {a.limit} used → <b>{a.left}</b> left
            </span>
            <label className="flex items-center gap-2">
              <span className="text-slate-500">Adds used so far:</span>
              <select value={a.manual ?? ""} onChange={(e) => setUsed(e.target.value)} className={select} disabled={busy || a.week == null}>
                <option value="">Count from transactions ({a.counted})</option>
                {Array.from({ length: a.limit + 1 }, (_, i) => (
                  <option key={i} value={i}>
                    {i} (I checked on Yahoo)
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
        {a.source === "transactions" && (
          <p className="mt-2 text-xs text-slate-500">
            Counted from the transactions on your last saved League page
            {a.counted_from.length > 0 && `: ${a.counted_from.map((c) => c.description.split(" - ")[0] + ` (${c.when})`).join(", ")}`}. Only
            recent transactions appear there, so pick the real number if it's higher.
          </p>
        )}
      </section>

      <section className={card}>
        <h2 className="mb-1 font-semibold">
          Streaming plan · {data.window_label}{" "}
          {data.days.length > 0 && (
            <span className="text-sm font-normal text-slate-500">
              ({dayLabel(data.days[0])} – {dayLabel(data.days[data.days.length - 1])})
            </span>
          )}
        </h2>
        {busy && <p className="text-sm text-slate-500">Working it out…</p>}
        {error && <Loading error={error} />}
        {data.moves.length === 0 ? (
          <Notice tone="ok">
            <b>Hold.</b>{" "}
            {data.adds_left === 0
              ? "No adds left this week."
              : `No add/drop gains at least ${data.min_gain} points over the rest of the week without giving up a better player.`}
          </Notice>
        ) : (
          <>
            <Notice tone="info">
              Using {data.moves.length} of your {data.adds_left} remaining adds:{" "}
              <b>
                +{data.gain.toFixed(1)} expected points
              </b>{" "}
              this week ({data.baseline.toFixed(0)} → {data.with_moves.toFixed(0)} from your lineups over these days).
            </Notice>
            <ol className="mt-3 space-y-3">
              {data.moves.map((m, i) => (
                <li key={i} className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                        Step {i + 1} · {dayLabel(m.date)}
                      </div>
                      <div className="mt-0.5">
                        <span className="font-semibold text-green-700 dark:text-green-400">Add</span> {m.add.name}
                        <StatusTag status={m.add.status} />{" "}
                        <span className="text-xs text-slate-500">
                          {m.add.nba_team} · {m.add.positions.join(",")}
                          {m.add.positions_estimated && "*"} · {m.add.fpts.toFixed(1)} FP/G
                          {m.add.kind === "W" && " · on waivers"}
                          {m.add.kind === "?" && " · not on a saved page: check he's a free agent"}
                        </span>
                      </div>
                      {m.drop && (
                        <div>
                          <span className="font-semibold text-red-700 dark:text-red-400">Drop</span> {m.drop.name}{" "}
                          <span className="text-xs text-slate-500">
                            {m.drop.fpts.toFixed(1)} FP/G{m.drop_is_streamer && " · streamer from an earlier step"}
                          </span>
                        </div>
                      )}
                      <div className="mt-1 text-xs text-slate-500">
                        Plays {m.games} game{m.games !== 1 && "s"} for you: {m.game_dates.map(shortDay).join(", ")}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold tabular-nums">+{m.gain.toFixed(1)}</div>
                      <YahooLink
                        href={m.yahoo_url}
                        onOpen={() =>
                          api
                            .logMove({
                              source: "streaming",
                              add_name: m.add.name,
                              add_yahoo_id: m.add.yahoo_id,
                              add_nba_id: m.add.id < 0 ? -m.add.id : null,
                              drop_yahoo_id: m.drop && m.drop.id > 0 ? m.drop.id : null,
                              drop_name: m.drop?.name ?? null,
                              gain: m.gain,
                            })
                            .catch(() => {})
                        }
                      >
                        {m.add.yahoo_id ? "Add on Yahoo ↗" : "Find on Yahoo ↗"}
                      </YahooLink>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </>
        )}
        <p className="mt-3 text-xs text-slate-500">
          How it plans: it tries every day, pickup and drop, keeps the move that adds the most points to your daily lineups, and
          repeats with your remaining adds. Your own players are only dropped for someone projected within {data.keep_tolerance} FP/G
          of them, so streaming never costs you a better player. Make each move on its day; re-save your pages afterwards so the plan
          updates.
        </p>
      </section>
    </div>
  );
}
