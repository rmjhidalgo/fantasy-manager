import { useEffect, useMemo, useState } from "react";
import { api, type FreeAgent, type FreeAgents } from "../api";
import { formatWhen, hoursOld } from "../time";
import { card, dayLabel, errText, InjuryNote, Loading, Notice, select, StatusTag, YahooLink } from "../ui";

const WINDOWS = [
  ["week", "Rest of this week"],
  ["7", "Next 7 days"],
  ["14", "Next 14 days"],
];
const POSITIONS = ["", "PG", "SG", "SF", "PF", "C"];
const STATS = [
  ["L7", "Last 7 days"],
  ["L14", "Last 14 days"],
  ["L30", "Last 30 days"],
  ["S", "Season"],
] as const;

function kindLabel(p: FreeAgent): string {
  if (p.kind === "FA") return "Free agent";
  if (p.kind === "W") return p.waiver_until ? `Waivers → ${dayLabel(p.waiver_until)} (US)` : "Waivers";
  return "Not on a saved page";
}

export default function FreeAgentsPage() {
  const [window, setWindow] = useState("week");
  const [position, setPosition] = useState("");
  const [kind, setKind] = useState<"all" | "FA" | "W" | "?">("all");
  const [minGames, setMinGames] = useState(0);
  const [rising, setRising] = useState(false);
  const [healthy, setHealthy] = useState(true);
  const [stat, setStat] = useState<(typeof STATS)[number][0]>("L14");
  const [data, setData] = useState<FreeAgents | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api
      .freeAgents(window, position)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(errText(e)))
      .finally(() => setLoading(false));
  }, [window, position]);

  const rows = useMemo(() => {
    if (!data) return [];
    return data.players.filter(
      (p) =>
        (kind === "all" || p.kind === kind) &&
        p.games >= minGames &&
        (!rising || (p.recent_mpg != null && p.season_mpg != null && p.recent_mpg - p.season_mpg >= 3)) &&
        (!healthy || p.play_prob >= 0.5),
    );
  }, [data, kind, minGames, rising, healthy]);

  if (!data) return <Loading error={error} />;
  const availOld = hoursOld(data.pool.available_as_of);
  const takenOld = hoursOld(data.pool.rostered_as_of);

  return (
    <div className="space-y-4">
      <section className={card}>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-slate-500">Days counted</span>
            <select value={window} onChange={(e) => setWindow(e.target.value)} className={select}>
              {WINDOWS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500">Position</span>
            <select value={position} onChange={(e) => setPosition(e.target.value)} className={select}>
              {POSITIONS.map((p) => (
                <option key={p} value={p}>
                  {p || "Any"}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500">Availability</span>
            <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} className={select}>
              <option value="all">All</option>
              <option value="FA">Free agents</option>
              <option value="W">On waivers</option>
              <option value="?">Not on a saved page</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500">Min. games</span>
            <select value={minGames} onChange={(e) => setMinGames(Number(e.target.value))} className={select}>
              {[0, 1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n || "Any"}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500">Recent FP/G column</span>
            <select value={stat} onChange={(e) => setStat(e.target.value as typeof stat)} className={select}>
              {STATS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1.5 pb-1">
            <input type="checkbox" checked={rising} onChange={(e) => setRising(e.target.checked)} /> Rising minutes
          </label>
          <label className="flex items-center gap-1.5 pb-1">
            <input type="checkbox" checked={healthy} onChange={(e) => setHealthy(e.target.checked)} /> Hide injured
          </label>
          {loading && <span className="pb-1 text-slate-500">Updating…</span>}
        </div>
      </section>

      <Notice tone={(availOld ?? 99) > 48 || (takenOld ?? 99) > 72 ? "warn" : "info"}>
        <b>{data.pool.from_pages + data.pool.from_nba} available players</b>: {data.pool.from_pages} from your saved Available list
        {data.pool.available_as_of ? ` (${formatWhen(data.pool.available_as_of)})` : ""}, and {data.pool.from_nba} worked out from NBA data
        (everyone not among the {data.pool.rostered_count} rostered players on your Taken pages
        {data.pool.rostered_as_of ? `, saved ${formatWhen(data.pool.rostered_as_of)}` : ""}).
        {data.pool.from_transactions > 0 && ` ${data.pool.from_transactions} updated from newer transactions.`} Players marked{" "}
        <i>not on a saved page</i> may be on waivers and have estimated positions (*): check on Yahoo before counting on them.
      </Notice>

      <section className={card}>
        <h2 className="mb-1 font-semibold">
          Best pickups · {data.window_label}{" "}
          <span className="text-sm font-normal text-slate-500">
            ({dayLabel(data.days[0])} – {dayLabel(data.days[data.days.length - 1])}, US dates)
          </span>
        </h2>
        <p className="mb-3 text-sm text-slate-500">
          <b>Gain</b> = extra points your best daily lineups would score with him, after dropping the player shown.{" "}
          {data.open_spots > 0
            ? `You have ${data.open_spots} empty roster spot${data.open_spots > 1 ? "s" : ""}, so no drop is needed.`
            : `Drops are chosen among your lowest-projected players: ${data.drop_candidates.map((d) => d.name).join(", ")}.`}
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-1 pr-2 font-medium">Player</th>
                <th className="py-1 pr-2 font-medium">Status</th>
                <th className="py-1 pr-2 text-right font-medium" title="Games in these days he could play for you">
                  G
                </th>
                <th className="py-1 pr-2 text-right font-medium" title="Projected fantasy points per game">
                  Proj
                </th>
                <th className="py-1 pr-2 text-right font-medium">{stat === "S" ? "Season" : stat}</th>
                <th className="py-1 pr-2 text-right font-medium" title="Minutes per game: last 14 days (season)">
                  Min
                </th>
                <th className="py-1 pr-2 text-right font-medium">Gain</th>
                <th className="py-1 pr-2 font-medium">Drop</th>
                <th className="py-1 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 60).map((p) => (
                <tr key={p.id} className="border-t border-slate-100 align-top dark:border-slate-800">
                  <td className="py-1.5 pr-2">
                    {p.name}
                    <StatusTag status={p.status} />
                    <div className="text-xs text-slate-500">
                      {p.nba_team} · {p.positions.join(",")}
                      {p.positions_estimated && "*"}
                      {p.pct_rostered != null && ` · ${p.pct_rostered}% rostered`}
                    </div>
                    {p.missed_streak >= 3 && (
                      <div className="text-xs text-amber-700 dark:text-amber-400">Missed his team's last {p.missed_streak} games</div>
                    )}
                    <InjuryNote text={p.injury} />
                  </td>
                  <td className="py-1.5 pr-2 text-xs">
                    {kindLabel(p)}
                    {p.note && <div className="text-slate-500">{p.note}</div>}
                  </td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{p.games}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{p.fpts.toFixed(1)}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-slate-500">{p.window_fp[stat]?.toFixed(1) ?? "–"}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-xs">
                    {p.recent_mpg ?? "–"}
                    {p.recent_mpg != null && p.season_mpg != null && Math.abs(p.recent_mpg - p.season_mpg) >= 3 && (
                      <span className={p.recent_mpg > p.season_mpg ? "text-green-700 dark:text-green-400" : "text-amber-700 dark:text-amber-400"}>
                        {p.recent_mpg > p.season_mpg ? " ▲" : " ▼"}
                      </span>
                    )}
                    <div className="text-slate-500">({p.season_mpg ?? "–"})</div>
                  </td>
                  <td className="py-1.5 pr-2 text-right font-semibold tabular-nums">
                    {p.gain == null ? "–" : p.gain > 0 ? `+${p.gain.toFixed(1)}` : p.gain.toFixed(1)}
                  </td>
                  <td className="py-1.5 pr-2 text-xs">
                    {p.gain == null ? "" : p.drop_name ?? "(empty spot)"}
                    {p.vs_drop != null && p.vs_drop < 0 && (
                      <div className="text-amber-700 dark:text-amber-400" title="Per-game projection compared with the player dropped">
                        {p.vs_drop.toFixed(1)} FP/G long-term
                      </div>
                    )}
                  </td>
                  <td className="py-1.5">
                    <YahooLink
                      href={p.yahoo_url}
                      onOpen={() =>
                        api
                          .logMove({
                            source: "free agents",
                            add_name: p.name,
                            add_yahoo_id: p.yahoo_id,
                            add_nba_id: p.id < 0 ? -p.id : null,
                            drop_yahoo_id: p.drop && p.drop > 0 ? p.drop : null,
                            drop_name: p.drop_name,
                            gain: p.gain,
                          })
                          .catch(() => {})
                      }
                    >
                      {p.yahoo_id ? "Add on Yahoo ↗" : "Find on Yahoo ↗"}
                    </YahooLink>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <p className="py-4 text-center text-sm text-slate-500">No players match these filters.</p>}
        <p className="mt-3 text-xs text-slate-500">
          Gain counts only these days: an orange "FP/G long-term" note means the player you'd drop is better per game for the rest of
          the season. Gain is worked out for the 60 best players by expected points; the rest show "–".
        </p>
      </section>
    </div>
  );
}
