import { useState } from "react";
import ComparePanel from "./strategy/ComparePanel";
import ProfilePanel from "./strategy/ProfilePanel";
import SchedulePanel from "./strategy/SchedulePanel";
import ScoutingPanel from "./strategy/ScoutingPanel";
import TradesPanel from "./strategy/TradesPanel";

const SUBTABS = [
  ["trades", "Trades"],
  ["schedule", "Schedule grid"],
  ["compare", "Compare players"],
  ["scouting", "Opponent scouting"],
  ["profile", "Scoring profile"],
] as const;

type Sub = (typeof SUBTABS)[number][0];

export default function StrategyPage() {
  const [sub, setSub] = useState<Sub>("trades");
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-800">
        {SUBTABS.map(([k, l]) => (
          <button
            key={k}
            onClick={() => setSub(k)}
            className={`-mb-px border-b-2 px-3 py-1.5 text-sm ${
              sub === k
                ? "border-blue-600 font-medium text-blue-700 dark:text-blue-300"
                : "border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
            }`}
          >
            {l}
          </button>
        ))}
      </div>
      {sub === "trades" && <TradesPanel />}
      {sub === "schedule" && <SchedulePanel />}
      {sub === "compare" && <ComparePanel />}
      {sub === "scouting" && <ScoutingPanel />}
      {sub === "profile" && <ProfilePanel />}
    </div>
  );
}
