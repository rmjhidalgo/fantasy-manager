import { useEffect, useState } from "react";
import { isUsEastern, myNow, usToday } from "../time";
import { dayLabel } from "../ui";

/** Top bar: which NBA game day it is (US Eastern, the day Yahoo counts) next to your own date and time. */
export default function TimeBar() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  const nbaDay = usToday(now);
  return (
    <div
      className="text-xs text-slate-500"
      title="Yahoo and the NBA count each fantasy day in US Eastern time, so game days in this app are US dates. Times (tip-offs, when pages were saved) are shown in your own time zone."
    >
      <span className="font-medium text-slate-700 dark:text-slate-200">NBA day: {dayLabel(nbaDay)} (US)</span>
      {!isUsEastern() && <span> · Your time: {myNow(now)}</span>}
    </div>
  );
}
