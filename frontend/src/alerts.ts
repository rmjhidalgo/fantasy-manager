// Desktop notifications for new alerts (shown while the app is open in a browser tab).
import type { AlertItem } from "./api";

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
