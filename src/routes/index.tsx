import { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useRunEngine } from "@/lib/swarm/use-run-engine";
import { TopBar } from "@/components/swarm/TopBar";
import { AgentSwarm } from "@/components/swarm/AgentSwarm";
import { BrowserView } from "@/components/swarm/BrowserView";
import { ProgressRail } from "@/components/swarm/ProgressRail";
import { ExtractionPanel } from "@/components/swarm/ExtractionPanel";
import { DeliveryPanel } from "@/components/swarm/DeliveryPanel";
import { Console } from "@/components/swarm/Console";

export const Route = createFileRoute("/")({
  component: Dashboard,
});

function Dashboard() {
  const { state, start, replay, setMode, setSpeed } = useRunEngine();
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof window === "undefined") return "dark";
    const saved = window.localStorage.getItem("fds-theme");
    return saved === "light" || saved === "dark" ? saved : "dark";
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    try { window.localStorage.setItem("fds-theme", theme); } catch {}
  }, [theme]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      <TopBar
        runStatus={state.runStatus}
        runNumber={state.runNumber}
        mode={state.mode}
        onToggleMode={setMode}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      />

      {/* Body: 3-column grid — 24px gutter, 16px panel padding pattern */}
      <main className="grid min-h-0 flex-1 gap-6 p-6" style={{ gridTemplateColumns: "25% 1fr 25%" }}>
        <div className="min-h-0">
          <AgentSwarm agents={state.agents} handoff={state.handoff} />
        </div>

        <div className="flex min-h-0 flex-col gap-6">
          <div className="min-h-0 flex-1">
            <BrowserView
              frames={state.frames}
              cursor={state.cursor}
              clickPulseKey={state.clickPulseKey}
              toast={state.toast}
            />
          </div>
          <ProgressRail checkpoints={state.checkpoints} />
        </div>

        <div className="grid min-h-0 grid-rows-[1fr_auto] gap-6">
          <ExtractionPanel specs={state.specs} asset={state.asset} />
          <DeliveryPanel delivery={state.delivery} />
        </div>
      </main>

      <div className="grid gap-6 px-6 pb-6" style={{ gridTemplateColumns: "25% 1fr 25%" }}>
        <div className="flex items-center gap-2">
          <button
            onClick={start}
            disabled={state.running}
            className="flex items-center gap-2 rounded-md border border-selection bg-selection px-3.5 py-2 text-[12px] font-medium text-white transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span className="h-2 w-2 rounded-full bg-white" />
            {state.runStatus === "IDLE" || state.runStatus === "COMPLETE" ? "Start Run" : "Running…"}
          </button>
          <button
            onClick={replay}
            className="rounded-md border border-hairline bg-surface px-3 py-2 text-[12px] text-foreground hover:border-hairline-strong"
            title="Restart the demo"
          >
            Replay
          </button>
          <div className="ml-auto flex overflow-hidden rounded-md border border-hairline bg-surface">
            {[1, 2].map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s as 1 | 2)}
                className={`px-2.5 py-1.5 font-mono text-[11px] transition-colors ${
                  state.speed === s ? "bg-selection/15 text-selection" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>
        <div className="col-span-2 h-[26vh] min-h-[220px]">
          <Console logs={state.logs} learned={state.learned} />
        </div>
      </div>
    </div>
  );
}
