// Two kinds of time in this app:
// - Times (tip-offs, "saved at", "updated at"): moments, shown in YOUR time zone (this PC's Windows setting),
//   always with its abbreviation, e.g. "12:00 PM JST".
// - Game days: US Eastern dates, because Yahoo and the NBA count a fantasy day that way. Marked "(US)".
// Times from the backend are UTC ISO strings ending in "Z".

const US_TZ = "America/New_York";

// Intl gives "GMT+9" for many zones outside the US; these read better.
const ZONE_ABBR: Record<string, string> = {
  "Asia/Tokyo": "JST",
  "Asia/Seoul": "KST",
  "Asia/Manila": "PHT",
  "Asia/Singapore": "SGT",
  "Asia/Hong_Kong": "HKT",
  "Asia/Taipei": "TST",
  "Asia/Shanghai": "CST",
  "Asia/Kolkata": "IST",
  "Australia/Sydney": "AET",
  "Europe/London": "UK",
  "Europe/Paris": "CET",
  "Europe/Berlin": "CET",
};

function zoneName(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

/** Your time zone's short name, e.g. "JST" (or "EST", "GMT+9" for zones without a common one). */
export function myZone(): string {
  const z = zoneName();
  if (ZONE_ABBR[z]) return ZONE_ABBR[z];
  try {
    const part = new Intl.DateTimeFormat("en-US", { timeZoneName: "short" }).formatToParts(new Date()).find((p) => p.type === "timeZoneName");
    return part?.value ?? "";
  } catch {
    return "";
  }
}

/** True when this PC is set to US Eastern time (then "your day" and "NBA day" are the same). */
export function isUsEastern(): boolean {
  return zoneName() === US_TZ;
}

/** "12:00 PM JST": a moment in your time zone. */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${t} ${myZone()}`.trim();
}

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "never";
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const yesterday = new Date(now.getTime() - 86_400_000).toDateString() === d.toDateString();
  const time = formatTime(iso);
  if (sameDay) return `today ${time}`;
  if (yesterday) return `yesterday ${time}`;
  return `${d.toLocaleDateString([], { month: "short", day: "numeric" })} ${time}`;
}

export function hoursOld(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return (Date.now() - new Date(iso).getTime()) / 3_600_000;
}

/** Today's NBA game day (US Eastern), as YYYY-MM-DD. */
export function usToday(now: Date = new Date()): string {
  // en-CA formats as YYYY-MM-DD
  return new Intl.DateTimeFormat("en-CA", { timeZone: US_TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

/** "Thu 11/26 13:05 JST": your current local day and time. */
export function myNow(now: Date = new Date()): string {
  const day = now.toLocaleDateString([], { weekday: "short", month: "numeric", day: "numeric" });
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${day} ${time} ${myZone()}`.trim();
}
