import type { AgentState, Handoff } from "@/lib/swarm/types";
import { Sparkline } from "./Sparkline";

const colorVar: Record<AgentState["color"], string> = {
  blue: "var(--blue)",
  violet: "var(--violet)",
  green: "var(--green)",
};

function AgentCard({ agent }: { agent: AgentState }) {
  const c = colorVar[agent.color];
  const active = agent.status === "active" || agent.status === "handoff";
  const error = agent.status === "error";
  const healed = agent.status === "healed";
  const statusLabel: Record<AgentState["status"], string> = {
    idle: "idle",
    active: "active",
    handoff: "handing off",
    error: "error",
    healed: "healed",
    done: "complete",
    skipped: "skipped",
  };

  return (
    <div
      className={`relative rounded-lg border bg-surface p-3.5 transition-all ${
        error ? "border-red/60 glow-red" : active ? "border-transparent" : "border-hairline"
      } ${healed ? "healed-flash" : ""}`}
      style={
        active && !error
          ? { boxShadow: `0 0 0 1px ${c}, 0 0 22px -6px ${c}` }
          : undefined
      }
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${active ? "pulse-dot" : ""}`}
            style={{ backgroundColor: error ? "var(--red)" : c }}
          />
          <span className="text-[13px] font-semibold text-foreground">{agent.name}</span>
        </div>
        <span
          className="font-mono text-[10px] uppercase tracking-wider"
          style={{ color: error ? "var(--red)" : active ? c : "var(--muted-foreground)" }}
        >
          {statusLabel[agent.status]}
        </span>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <code className="truncate font-mono text-[11px] text-muted-foreground">
          {agent.tool}<span className="caret">|</span>
        </code>
        <Sparkline values={agent.sparkline} color={c} />
      </div>
    </div>
  );
}

function Connector({ handoff, from, to }: { handoff: Handoff | null; from: string; to: string }) {
  const active = handoff && handoff.from === from && handoff.to === to;
  return (
    <div className="relative flex h-9 items-center justify-center">
      <div
        className={`h-full w-px ${active ? "bg-primary" : "bg-hairline"} transition-colors`}
        style={{ backgroundImage: active ? undefined : "linear-gradient(to bottom, transparent 0, transparent 3px, var(--hairline) 3px, var(--hairline) 6px)", backgroundSize: "1px 6px" }}
      />
      {active && (
        <div
          key={handoff!.key}
          className="absolute left-1/2 top-0 -translate-x-1/2"
          style={{ animation: "handoff-travel 900ms linear forwards" }}
        >
          <div className="flex flex-col items-center gap-1">
            <div className="h-2 w-2 rounded-full glow-violet" style={{ backgroundColor: "var(--violet)" }} />
          </div>
        </div>
      )}
      {active && (
        <span className="absolute -right-1 top-1/2 -translate-y-1/2 translate-x-full rounded border border-hairline bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-foreground">
          {handoff!.payload}
        </span>
      )}
    </div>
  );
}

interface Props {
  agents: Record<"detect" | "extract" | "post", AgentState>;
  handoff: Handoff | null;
}

export function AgentSwarm({ agents, handoff }: Props) {
  return (
    <div className="panel h-full p-4 flex flex-col">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Agent Swarm</h2>
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">langgraph · swarm</span>
      </div>
      <div className="flex-1 flex flex-col justify-center">
        <AgentCard agent={agents.detect} />
        <Connector handoff={handoff} from="detect" to="extract" />
        <AgentCard agent={agents.extract} />
        <Connector handoff={handoff} from="extract" to="post" />
        <AgentCard agent={agents.post} />
      </div>
    </div>
  );
}
