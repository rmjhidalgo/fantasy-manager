// Desktop notifications for new alerts and the daily summary (shown while the app is open in a browser tab).
import { api, type AlertItem } from "./api";

const SUMMARY_KEY = "fm_summary_notified_on";

function todayLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Once a day, at or after the chosen local time: a desktop notification with the summary's first items. */
export async function maybeNotifySummary(onClick: () => void): Promise<void> {
  try {
    if (localStorage.getItem(SUMMARY_KEY) === todayLocal()) return;
  } catch {
    return; // no storage: we can't remember, so don't risk notifying every minute
  }
  let settings;
  try {
    settings = await api.summarySettings();
  } catch {
    return;
  }
  if (!settings.enabled) return;
  const [hh, mm] = settings.time.split(":").map(Number);
  const now = new Date();
  if (now.getHours() * 60 + now.getMinutes() < hh * 60 + mm) return;
  try {
    localStorage.setItem(SUMMARY_KEY, todayLocal());
  } catch {
    return;
  }
  if (notificationPermission() !== "granted") return;
  try {
    const s = await api.summary();
    const body = s.items
      .slice(0, 3)
      .map((i) => i.title)
      .join("\n");
    const n = new Notification("☀ Fantasy Manager: today's summary", { body, tag: "fm-summary" });
    n.onclick = () => {
      window.focus();
      onClick();
    };
  } catch {
    /* summary unavailable */
  }
}

const SEEN_KEY = "fm_notified_alerts";

function loadSeen(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) ?? "[]") as string[]);
  } catch {
    return new Set();
  }
}

function saveSeen(seen: Set<string>): void {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-300)));
  } catch {
    /* storage unavailable: we may notify twice, which is harmless */
  }
}

export function notificationsSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export function notificationPermission(): NotificationPermission | "unsupported" {
  return notificationsSupported() ? Notification.permission : "unsupported";
}

export async function enableNotifications(): Promise<NotificationPermission | "unsupported"> {
  if (!notificationsSupported()) return "unsupported";
  return Notification.requestPermission();
}

/** Show a desktop notification for each alert not notified before. */
export function notifyNew(alerts: AlertItem[], onClick: (a: AlertItem) => void): void {
  const seen = loadSeen();
  const fresh = alerts.filter((a) => a.notify && !seen.has(a.key));
  if (fresh.length === 0) return;
  if (notificationPermission() === "granted") {
    for (const a of fresh) {
      try {
        const n = new Notification(`🏀 ${a.title}`, { body: a.detail, tag: a.key });
        n.onclick = () => {
          window.focus();
          onClick(a);
        };
      } catch {
        /* some browsers only allow notifications from a service worker */
      }
    }
  }
  for (const a of fresh) seen.add(a.key);
  saveSeen(seen);
}
