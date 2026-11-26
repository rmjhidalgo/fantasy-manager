import { useEffect, useState } from "react";
import { api, type LineupDay, type Outlook } from "../api";
import { card, dayLabel, errText, Loading, Notice, select, StatusTag, YahooLink } from "../ui";
import { formatTime } from "../time";

function addDays(iso: string, n: number): string {
  const d = new Date(iso + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export default function LineupPage({ outlook }: { outlook: Outlook | null }) {
  const [day, setDay] = useState<string | null>(null);
  const [data, setData] = useState<LineupDay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const today = outlook?.today ?? null;
  const chosen = day ?? today;

  useEffect(() => {
    if (!chosen) return;
    api
      .lineup(chosen)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(errText(e)));
  }, [chosen, outlook]);

  if (!today) return <Loading error={outlook ? null : "Import your league pages first."} />;
  const options = Array.from({ length: 8 }, (_, i) => addDays(today, i));
  const changes = data?.players.filter((p) => p.change === "start" || p.change === "bench") ?? [];
  const gain = data ? data.best_expected - data.current_expected : 0;
  const withGame = data?.players.filter((p) => p.game && !p.current_slot.startsWith("IL") && p.expected > 0).length ?? 0;
  const filled = data?.players.filter((p) => p.best_slot).length ?? 0;

  return (
    <div className="space-y-6">
      <section className={card}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Best lineup</h2>
          <div className="flex items-center gap-3">
            <select value={chosen ?? ""} onChange={(e) => setDay(e.target.value)} className={select}>
              {options.map((d) => (
                <option key={d} value={d}>
                  {dayLabel(d)} (US){d === today ? " · today's NBA day" : ""}
                </option>
              ))}
            </select>
            {data && <YahooLink href={data.yahoo_url} />}
          </div>
        </div>
        {error && <Loading error={error} />}
        {data && (
          <div className="space-y-3">
            {changes.length > 0 && gain > 0.5 ? (
              <Notice tone="warn">
                <b>Suggested changes (+{gain.toFixed(1)} expected pts):</b>{" "}
                {changes.map((c) => `${c.change === "start" ? "Start" : "Bench"} ${c.name}`).join(", ")}
                <div className="text-xs opacity-75">Compared with the lineup on your last imported My Team page.</div>
              </Notice>
            ) : (
              <Notice tone="ok">✓ Your imported lineup is already the best for this day.</Notice>
            )}
            {data.il_moves.length > 0 && (
              <Notice tone="warn">
                {data.il_moves.map((m) => (
                  <div key={m.player_id}>
                    <b>{m.move === "to IL" ? `Move ${m.name} to IL` : `Activate ${m.name} from IL`}</b> — {m.reason}
                  </div>
                ))}
              </Notice>
            )}
            <p className="text-sm text-slate-500">
              {withGame} of your healthy players have a game; {filled} of {data.slots.length} slots filled
              {filled < data.slots.length && " — see Streaming to fill the gap"}. Expected {data.best_expected.toFixed(0)} pts.
            </p>
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-1 pr-2 font-medium">Slot</th>
                  <th className="py-1 pr-2 font-medium">Player</th>
                  <th className="py-1 pr-2 font-medium">Now</th>
                  <th className="py-1 pr-2 font-medium">Game</th>
                  <th className="py-1 text-right font-medium">Exp.</th>
                </tr>
              </thead>
              <tbody>
                {data.players.map((p) => (
                  <tr key={p.player_id} className={`border-t border-slate-100 dark:border-slate-800 ${p.best_slot ? "" : "text-slate-400"}`}>
                    <td className="py-1 pr-2 font-medium">{p.best_slot ?? "—"}</td>
                    <td className="py-1 pr-2">
                      {p.name}
                      <StatusTag status={p.status} />
                      {p.change === "start" && <span className="ml-1 text-xs font-medium text-green-700 dark:text-green-400">start</span>}
                      {p.change === "bench" && <span className="ml-1 text-xs font-medium text-amber-700 dark:text-amber-400">bench</span>}
                      <div className="text-xs text-slate-500">{p.positions.join(", ")}</div>
                    </td>
                    <td className="py-1 pr-2 text-xs text-slate-500">{p.current_slot}</td>
                    <td className="py-1 pr-2 text-xs">
                      {p.game ? p.game.opponent : "no game"}
                      {p.game && !p.game.started && p.game.start_utc && (
                        <span className="text-slate-500">
                          {" "}
                          {formatTime(p.game.start_utc)}
                        </span>
                      )}
                      {p.locked && <span className="text-slate-500"> · 🔒 started</span>}
                    </td>
                    <td className="py-1 text-right tabular-nums">{p.expected ? p.expected.toFixed(1) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-slate-500">
              Days are US game days (Yahoo's); tip-off times are in your time zone. Expected = projected points × chance of playing. Make the changes on Yahoo: the
              button opens your team page for this day.
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
