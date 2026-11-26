import { useEffect, useState, type ReactNode } from "react";
import { api, type Checklist, type ChecklistItem } from "../api";
import { formatWhen } from "../time";
import { card } from "../ui";

type Step = { key: ChecklistItem["key"]; title: string; what: string; how: ReactNode };

const SETUP: Step[] = [
  {
    key: "settings",
    title: "League settings",
    what: "Your league's scoring, roster spots, add limit and playoff weeks.",
    how: (
      <>
        Open your league on Yahoo → <b>League</b> menu → <b>Settings</b> → save the page.
      </>
    ),
  },
  {
    key: "schedule",
    title: "Season schedule (every team)",
    what: "Who plays whom each week: makes playoff odds and next week's matchup exact.",
    how: (
      <ol className="ml-4 list-decimal space-y-0.5">
        <li>
          Open your league's main page. In the standings box, click the <b>Schedule</b> tab.
        </li>
        <li>
          Click the <b>first team's name</b> in the list of teams, then save the page.
        </li>
        <li>Click the next team's name and save again. Repeat until every team is saved (one page per team).</li>
      </ol>
    ),
  },
];

const REGULAR: { when: string; why: string; steps: Step[] }[] = [
  {
    when: "Every day, before the games (1–2 minutes)",
    why: "Keeps your lineup, matchup and alerts right.",
    steps: [
      {
        key: "my_team",
        title: "My Team",
        what: "Your roster, lineup slots and injury tags.",
        how: (
          <>
            Click <b>My Team</b> on Yahoo → save.
          </>
        ),
      },
      {
        key: "matchup",
        title: "Matchup",
        what: "This week's score and both rosters.",
        how: (
          <>
            Click <b>Matchup</b> → save.
          </>
        ),
      },
      {
        key: "league_home",
        title: "League main page",
        what: "Standings, every team's score this week, and recent adds and drops.",
        how: (
          <>
            Click your <b>league's name</b> → save.
          </>
        ),
      },
      {
        key: "transactions",
        title: "Transactions",
        what: "Every add and drop with its date, so your adds used this week are counted exactly.",
        how: (
          <>
            Open your league's <b>League</b> menu → <b>Transactions</b> → save. (The first page is enough; save the next page too if
            your league made more than 25 moves this week.)
          </>
        ),
      },
    ],
  },
  {
    when: "2–3 times a week, before looking for pickups",
    why: "Shows who's available and on waivers.",
    steps: [
      {
        key: "available",
        title: "Available players (2–3 pages)",
        what: "Free agents and waiver players, with Yahoo's positions and injury tags.",
        how: (
          <>
            Click <b>Players</b>. Set the status to <b>Available</b>, sort by <b>Fan Pts</b>, and pick stats for the <b>last 14
            days</b>. Save the page, then click <b>Next 25</b> at the bottom and save again (2–3 pages are enough).
          </>
        ),
      },
    ],
  },
  {
    when: "Once a week (e.g. Monday)",
    why: "Tells the app who owns every player, so it can work out everyone else as available.",
    steps: [
      {
        key: "taken",
        title: "Taken players (all pages)",
        what: "Every rostered player and his owner.",
        how: (
          <>
            Click <b>Players</b>, set the status to <b>Taken</b>. Save, click <b>Next 25</b>, save again… until the last page.
          </>
        ),
      },
    ],
  },
];

function StatusChip({ item }: { item: ChecklistItem | undefined }) {
  if (!item || item.status === "missing")
    return <span className="whitespace-nowrap rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-950 dark:text-red-300">✗ Not saved yet</span>;
  if (item.status === "partial")
    return (
      <span className="whitespace-nowrap rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
        ⚠ {item.teams_done} of {item.teams_total} teams
      </span>
    );
  if (item.status === "old")
    return (
      <span className="whitespace-nowrap rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
        ⚠ Saved {formatWhen(item.saved_at)} — save again
      </span>
    );
  return (
    <span className="whitespace-nowrap rounded bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-800 dark:bg-green-950 dark:text-green-300">
      ✓ {item.key === "schedule" && item.teams_total ? `All ${item.teams_total} teams` : `Saved ${formatWhen(item.saved_at)}`}
    </span>
  );
}

function StepRow({ step, item, n }: { step: Step; item: ChecklistItem | undefined; n?: number }) {
  return (
    <li className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="font-medium">
          {n != null && <span className="mr-1 text-slate-500">{n}.</span>}
          {step.title}
        </div>
        <StatusChip item={item} />
      </div>
      <div className="text-sm text-slate-500">{step.what}</div>
      <div className="mt-1 text-sm">{step.how}</div>
      {item?.missing_teams && item.missing_teams.length > 0 && item.status === "partial" && (
        <div className="mt-1 text-sm text-amber-700 dark:text-amber-400">Still missing: {item.missing_teams.join(", ")}</div>
      )}
    </li>
  );
}

export default function SaveGuide({ version }: { version: number }) {
  const [c, setC] = useState<Checklist | null>(null);
  const [folder, setFolder] = useState<string | null>(null);

  useEffect(() => {
    api.checklist().then(setC).catch(() => {});
    api
      .watchFolder()
      .then((w) => setFolder(w.running ? w.folder : null))
      .catch(() => {});
  }, [version]);

  const find = (key: string) => [...(c?.setup ?? []), ...(c?.regular ?? [])].find((i) => i.key === key);
  const setupDone = (c?.setup ?? []).every((i) => i.status === "ok");

  return (
    <div className="space-y-4">
      <section className={card}>
        <h2 className="mb-2 font-semibold">How to save a page from Yahoo</h2>
        <ol className="ml-5 list-decimal space-y-1 text-sm">
          <li>Open the page on the Yahoo Fantasy website, signed in as usual.</li>
          <li>
            Press <kbd className="rounded border px-1">Ctrl</kbd> + <kbd className="rounded border px-1">S</kbd>.
          </li>
          <li>
            Under <b>Save as type</b>, choose <b>Webpage, Single File</b>.
          </li>
          <li>
            {folder ? (
              <>
                Save it into <b>{folder}</b>. The app picks it up by itself within a few seconds.
              </>
            ) : (
              <>Save it anywhere, then drag the file onto the box below (or set up a watched folder further down, so it's automatic).</>
            )}
          </li>
        </ol>
        <p className="mt-2 text-xs text-slate-500">
          File names don't matter, and saving a page twice is harmless: the app always keeps the newest information.
        </p>
      </section>

      <section className={card}>
        <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Step 1 · One-time setup</h2>
          {setupDone ? (
            <span className="text-sm text-green-700 dark:text-green-400">✓ Done — nothing to do here until next season</span>
          ) : (
            <span className="text-sm text-amber-700 dark:text-amber-400">About 5 minutes, once a season</span>
          )}
        </div>
        <p className="mb-3 text-sm text-slate-500">Save these once at the start of the season (again only if your league changes its rules).</p>
        <ul className="space-y-2">
          {SETUP.map((s, i) => (
            <StepRow key={s.key} step={s} item={find(s.key)} n={i + 1} />
          ))}
        </ul>
      </section>

      <section className={card}>
        <h2 className="mb-1 font-semibold">Step 2 · Regular updates</h2>
        <p className="mb-3 text-sm text-slate-500">
          The app is only as current as your last saved pages. Players' stats and the NBA schedule update by themselves.
        </p>
        <div className="space-y-4">
          {REGULAR.map((g) => (
            <div key={g.when}>
              <h3 className="text-sm font-semibold">{g.when}</h3>
              <p className="mb-2 text-xs text-slate-500">{g.why}</p>
              <ul className="space-y-2">
                {g.steps.map((s) => (
                  <StepRow key={s.key} step={s} item={find(s.key)} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
