import { useEffect, useState } from "react";
import { api, type WatchFolder } from "../api";
import { btn, card, errText } from "../ui";
import SaveGuide from "./SaveGuide";

/** First run: no league imported yet. Set up the pages folder, then follow the save guide. */
export default function Welcome({ onRefresh }: { onRefresh: () => void }) {
  const [wf, setWf] = useState<WatchFolder | null>(null);
  const [path, setPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    api
      .watchFolder()
      .then((w) => {
        setWf(w);
        setPath(w.configured ?? w.suggested ?? "");
      })
      .catch(() => {});
  }, []);

  // While waiting for the first pages, look for new imports every few seconds
  useEffect(() => {
    const t = setInterval(() => {
      setTick((x) => x + 1);
      onRefresh();
    }, 5000);
    return () => clearInterval(t);
  }, [onRefresh]);

  const useFolder = () => {
    setError(null);
    api
      .setWatchFolder(path, true)
      .then(setWf)
      .catch((e) => setError(errText(e)));
  };

  return (
    <div className="space-y-4">
      <section className={card}>
        <h2 className="mb-1 text-xl font-semibold">👋 Welcome to Fantasy Manager</h2>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          This app helps you win your Yahoo Fantasy Basketball league: best lineups, pickups, trades and playoff odds. It works from
          Yahoo pages that <b>you</b> save from your browser, so it never needs your Yahoo password. Everything stays on this PC.
        </p>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Getting started takes about 10 minutes, once:</p>
      </section>

      <section className={card}>
        <h2 className="mb-1 font-semibold">1 · Pick a folder for your saved pages</h2>
        <p className="mb-3 text-sm text-slate-500">
          Whenever you save a Yahoo page into this folder, the app reads it by itself within a few seconds.
        </p>
        {wf?.running ? (
          <p className="text-sm text-green-700 dark:text-green-400">
            ✓ Using <b>{wf.folder}</b>. Save your Yahoo pages there.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            <input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              className="min-w-0 flex-1 rounded-md border border-slate-300 bg-transparent px-3 py-1.5 text-sm dark:border-slate-700"
            />
            <button className={btn} disabled={!path.trim()} onClick={useFolder}>
              Use this folder
            </button>
          </div>
        )}
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </section>

      <div className={wf?.running ? "" : "pointer-events-none opacity-50"}>
        <h2 className="mb-2 mt-6 font-semibold">2 · Save your league's pages from Yahoo</h2>
        <SaveGuide version={tick} />
      </div>

      <section className={card}>
        <h2 className="mb-1 font-semibold">3 · That's it</h2>
        <p className="text-sm text-slate-500">
          As soon as your first page arrives, this screen turns into your team's overview. Then keep the "Regular updates" going
          (about a minute a day) on the <b>Import &amp; data</b> tab. Optional extras on the <b>Settings</b> tab: a morning summary
          notification, and asking Claude Desktop about your team.
        </p>
      </section>
    </div>
  );
}
