import { useState } from "react";
import type { AlertItem } from "../api";
import { enableNotifications, notificationPermission } from "../alerts";
import { card, YahooLink } from "../ui";

const TONE = {
  danger: "border-l-red-500 bg-red-50 dark:bg-red-950/40",
  warn: "border-l-amber-500 bg-amber-50 dark:bg-amber-950/40",
  info: "border-l-slate-400 bg-slate-50 dark:bg-slate-800/60",
};

const ACTION_LABEL = { lineup: "Lineup →", streaming: "Streaming →", import: "Import →" };

export default function AlertsCard({
  alerts,
  onAction,
}: {
  alerts: AlertItem[] | null;
  onAction: (action: NonNullable<AlertItem["action"]>) => void;
}) {
  const [perm, setPerm] = useState(notificationPermission());
  if (!alerts) return null;

  return (
    <section className={card}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Alerts</h2>
        {perm === "default" && (
          <button
            onClick={() => enableNotifications().then(setPerm)}
            className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            🔔 Enable desktop notifications
          </button>
        )}
        {perm === "granted" && <span className="text-xs text-slate-500">🔔 Desktop notifications on (while this tab is open)</span>}
        {perm === "denied" && <span className="text-xs text-slate-500">Notifications are blocked in this browser's site settings</span>}
      </div>
      {alerts.length === 0 ? (
        <p className="text-sm text-green-700 dark:text-green-400">✓ Nothing needs your attention.</p>
      ) : (
        <ul className="space-y-2">
          {alerts.map((a) => (
            <li key={a.key} className={`rounded-md border-l-4 px-3 py-2 text-sm ${TONE[a.level]}`}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-medium">{a.title}</div>
                  {a.detail && <div className="text-slate-600 dark:text-slate-300">{a.detail}</div>}
                </div>
                {a.action && (
                  <button onClick={() => onAction(a.action!)} className="shrink-0 text-xs text-blue-700 hover:underline dark:text-blue-300">
                    {ACTION_LABEL[a.action]}
                  </button>
                )}
              </div>
              {a.next_man_up && a.next_man_up.length > 0 && (
                <div className="mt-1.5 text-xs">
                  <div className="text-slate-500">Next man up (minutes in the games he missed):</div>
                  <ul className="mt-0.5 space-y-0.5">
                    {a.next_man_up.map((h) => (
                      <li key={h.name}>
                        <b>{h.name}</b> {h.minutes_with} → {h.minutes_without} min, {h.fpts_without} FP/G over {h.games_without} game
                        {h.games_without !== 1 && "s"}
                        {h.available ? (
                          <>
                            {" "}
                            · <span className="text-green-700 dark:text-green-400">available{h.kind === "W" ? " (waivers)" : ""}</span>{" "}
                            {h.yahoo_url && <YahooLink href={h.yahoo_url}>Yahoo ↗</YahooLink>}
                          </>
                        ) : (
                          <span className="text-slate-500"> · rostered</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
