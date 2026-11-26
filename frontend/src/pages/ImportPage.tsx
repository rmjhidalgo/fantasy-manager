import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ImportHistoryRow, type ImportResult, type NbaStatus, type WatchFolder } from "../api";
import SaveGuide from "../components/SaveGuide";
import { formatWhen } from "../time";

const ACCEPT = ".mhtml,.mht,.html,.htm";

const STATUS_STYLE: Record<ImportResult["status"], string> = {
  imported: "text-green-700 dark:text-green-400",
  partial: "text-amber-700 dark:text-amber-400",
  duplicate: "text-slate-500",
  unsupported: "text-slate-500",
  error: "text-red-600 dark:text-red-400",
};

const STATUS_LABEL: Record<ImportResult["status"], string> = {
  imported: "✓ Imported",
  partial: "⚠ Imported (some parts skipped)",
  duplicate: "Already imported",
  unsupported: "Skipped",
  error: "✗ Couldn't read",
};

export default function ImportPage({ onImported }: { onImported: () => void }) {
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [results, setResults] = useState<ImportResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<ImportHistoryRow[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const [guideVersion, setGuideVersion] = useState(0);
  const loadHistory = useCallback(() => {
    api.imports().then((r) => setHistory(r.imports)).catch(() => {});
    setGuideVersion((v) => v + 1); // statuses in the save guide update too
  }, []);
  useEffect(loadHistory, [loadHistory]);

  const upload = async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.importFiles(files);
      setResults(r.results);
      onImported();
      loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <SaveGuide version={guideVersion} />

      <section
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          upload(Array.from(e.dataTransfer.files));
        }}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition ${
          dragging
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
            : "border-slate-300 bg-white hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            upload(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
        <p className="text-lg font-medium">{busy ? "Importing…" : "Drop saved Yahoo pages here"}</p>
        <p className="mt-1 text-sm text-slate-500">or click to choose files (.mhtml or .html). You can drop many at once.</p>
      </section>

      {error && <p className="text-red-600 dark:text-red-400">Import failed: {error}</p>}

      {results.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-3 font-semibold">Just imported</h2>
          <ResultList results={results} />
        </section>
      )}

      <WatchFolderCard onImported={onImported} />

      <NbaDataCard onChanged={onImported} />

      <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Import history</h2>
          <ReprocessButton onDone={onImported} />
        </div>
        {history.length === 0 ? (
          <p className="text-sm text-slate-500">Nothing imported yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-1 pr-3 font-medium">Page</th>
                  <th className="py-1 pr-3 font-medium">Saved</th>
                  <th className="py-1 pr-3 font-medium">Imported</th>
                  <th className="py-1 pr-3 font-medium">Result</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h, i) => (
                  <tr key={i} className="border-t border-slate-100 align-top dark:border-slate-800">
                    <td className="py-1.5 pr-3">
                      <div>{h.page_label ?? h.filename}</div>
                      {h.page_label && <div className="max-w-xs truncate text-xs text-slate-500">{h.filename}</div>}
                    </td>
                    <td className="py-1.5 pr-3 whitespace-nowrap">{formatWhen(h.saved_at)}</td>
                    <td className="py-1.5 pr-3 whitespace-nowrap">
                      {formatWhen(h.imported_at)}
                      {h.source === "folder" && <span className="ml-1 text-xs text-slate-500">(folder)</span>}
                    </td>
                    <td className={`py-1.5 pr-3 ${STATUS_STYLE[h.status]}`}>
                      {STATUS_LABEL[h.status]}
                      {h.message && <div className="text-xs text-slate-500">{h.message}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function ResultList({ results }: { results: ImportResult[] }) {
  return (
    <ul className="space-y-2">
      {results.map((r, i) => (
        <li key={i} className="text-sm">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className={`font-medium ${STATUS_STYLE[r.status]}`}>{STATUS_LABEL[r.status]}</span>
            <span>{r.page_label ?? r.filename}</span>
            {r.saved_at && <span className="text-slate-500">· saved {formatWhen(r.saved_at)}</span>}
          </div>
          {r.summary && <div className="text-slate-600 dark:text-slate-400">{r.summary}</div>}
          {r.warnings.map((w, j) => (
            <div key={j} className="text-amber-700 dark:text-amber-400">
              {w}
            </div>
          ))}
        </li>
      ))}
    </ul>
  );
}

function WatchFolderCard({ onImported }: { onImported: () => void }) {
  const [wf, setWf] = useState<WatchFolder | null>(null);
  const [path, setPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const latest = useRef<string | null>(null);
  const filled = useRef(false);

  useEffect(() => {
    const load = () =>
      api
        .watchFolder()
        .then((w) => {
          setWf(w);
          if (!filled.current) {
            setPath(w.configured ?? "");
            filled.current = true;
          }
          // Refresh the rest of the app when the folder brought in something new.
          const key = w.recent[0] ? `${w.recent[0].filename}|${w.recent[0].saved_at}` : null;
          if (latest.current !== null && key !== latest.current) onImported();
          latest.current = key ?? "";
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 5000); // pick up pages imported in the background
    return () => clearInterval(t);
  }, [onImported]);

  const save = async (folder: string | null) => {
    setError(null);
    try {
      setWf(await api.setWatchFolder(folder));
      if (!folder) setPath("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="font-semibold">Watched folder (optional)</h2>
      <p className="mb-3 text-sm text-slate-500">
        Pages you save into this folder are imported automatically within a few seconds, while the app is running.
      </p>
      <div className="flex flex-wrap gap-2">
        <input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder="e.g. C:\Users\you\Downloads\Yahoo"
          className="min-w-0 flex-1 rounded-md border border-slate-300 bg-transparent px-3 py-1.5 text-sm dark:border-slate-700"
        />
        <button
          onClick={() => save(path)}
          disabled={!path.trim()}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {wf?.running ? "Change" : "Start watching"}
        </button>
        {wf?.running && (
          <button
            onClick={() => save(null)}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            Stop
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {wf && (
        <p className="mt-2 text-sm">
          {wf.running ? (
            <span className="text-green-700 dark:text-green-400">● Watching {wf.folder}</span>
          ) : wf.configured ? (
            <span className="text-amber-700 dark:text-amber-400">Not running: folder {wf.configured} wasn't found.</span>
          ) : (
            <span className="text-slate-500">Not set up.</span>
          )}
        </p>
      )}
      {wf && wf.recent.length > 0 && (
        <div className="mt-3">
          <h3 className="mb-2 text-sm font-medium text-slate-500">Imported from the folder</h3>
          <ResultList results={wf.recent.slice(0, 5)} />
        </div>
      )}
    </section>
  );
}

function ReprocessButton({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <span className="flex items-center gap-2 text-sm">
      {msg && <span className="text-slate-500">{msg}</span>}
      <button
        disabled={busy}
        title="Read every saved page again, e.g. after an app update that reads more from them. Newest data still wins."
        onClick={() => {
          setBusy(true);
          api
            .reprocess()
            .then((r) => {
              setMsg(`Re-read ${r.pages} pages${r.errors ? `, ${r.errors} couldn't be read` : ""}.`);
              onDone();
            })
            .catch(() => setMsg("Couldn't re-read the pages."))
            .finally(() => setBusy(false));
        }}
        className="rounded-md border border-slate-300 px-2 py-1 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
      >
        {busy ? "Re-reading…" : "Re-read saved pages"}
      </button>
    </span>
  );
}

function NbaDataCard({ onChanged }: { onChanged: () => void }) {
  const [st, setSt] = useState<NbaStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.nbaStatus().then(setSt).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const refresh = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.nbaRefresh();
      load();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const link = async (yahooId: number, value: string) => {
    if (!value) return;
    await api.setPlayerMap(yahooId, value === "none" ? null : Number(value));
    load();
    onChanged();
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">NBA data</h2>
        <button
          onClick={refresh}
          disabled={busy}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          {busy ? "Downloading…" : "Refresh now"}
        </button>
      </div>
      <p className="mb-2 text-sm text-slate-500">
        Schedule and box scores (NBA.com) and the injury list with expected return dates (ESPN) download automatically every 3 hours while the app runs.
      </p>
      {st && (
        <p className="text-sm">
          {st.refreshed_at ? (
            <>
              Updated {formatWhen(st.refreshed_at)} · season {st.season} · {st.games} games · {st.game_logs} player box scores
            </>
          ) : (
            <span className="text-amber-700 dark:text-amber-400">Not downloaded yet.</span>
          )}
        </p>
      )}
      {st?.injuries && (
        <p className="text-sm text-slate-500">
          Injury list (ESPN, with expected return dates):{" "}
          {st.injuries.refreshed_at ? `${st.injuries.count} injured players, updated ${formatWhen(st.injuries.refreshed_at)}` : "not downloaded yet"}
        </p>
      )}
      {(error || st?.last_error) && (
        <p className="mt-1 text-sm text-red-600 dark:text-red-400">Last download failed: {error ?? st?.last_error}</p>
      )}
      {st && st.unmatched.length > 0 && (
        <div className="mt-3">
          <h3 className="mb-1 text-sm font-medium">Players not matched to NBA stats ({st.unmatched.length})</h3>
          <p className="mb-2 text-xs text-slate-500">Pick the right NBA player so projections can use his box scores.</p>
          <ul className="space-y-1 text-sm">
            {st.unmatched.map((u) => (
              <li key={u.yahoo_id} className="flex flex-wrap items-center gap-2">
                <span className="min-w-40">
                  {u.name} <span className="text-slate-500">({u.nba_team ?? "?"})</span>
                  {u.rostered && <span className="ml-1 text-xs text-amber-700 dark:text-amber-400">rostered</span>}
                </span>
                <select
                  defaultValue=""
                  onChange={(e) => link(u.yahoo_id, e.target.value)}
                  className="rounded-md border border-slate-300 bg-transparent px-2 py-1 text-sm dark:border-slate-700"
                >
                  <option value="">Choose…</option>
                  {u.candidates.map((c) => (
                    <option key={c.nba_id} value={c.nba_id}>
                      {c.name} ({c.team ?? "no team"})
                    </option>
                  ))}
                  <option value="none">No NBA match</option>
                </select>
              </li>
            ))}
          </ul>
        </div>
      )}
      {st && st.refreshed_at && st.unmatched.length === 0 && (
        <p className="mt-1 text-sm text-green-700 dark:text-green-400">✓ Every imported Yahoo player is matched to NBA stats.</p>
      )}
    </section>
  );
}
