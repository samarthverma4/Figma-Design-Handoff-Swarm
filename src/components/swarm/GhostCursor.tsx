import { useEffect, useRef, useState } from "react";
import type { CursorTarget } from "@/lib/swarm/types";

interface Props { target: CursorTarget; pulseKey: number; }

export function GhostCursor({ target, pulseKey }: Props) {
  const [pos, setPos] = useState({ x: target.x, y: target.y });
  const raf = useRef<number | undefined>(undefined);

  // Smooth easing toward target
  useEffect(() => {
    let cancelled = false;
    const step = () => {
      setPos((p) => {
        const dx = target.x - p.x;
        const dy = target.y - p.y;
        if (Math.abs(dx) < 0.05 && Math.abs(dy) < 0.05) return p;
        return { x: p.x + dx * 0.09, y: p.y + dy * 0.09 };
      });
      if (!cancelled) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => { cancelled = true; if (raf.current) cancelAnimationFrame(raf.current); };
  }, [target.x, target.y]);

  return (
    <div
      className="pointer-events-none absolute z-30"
      style={{ left: `${pos.x}%`, top: `${pos.y}%`, transform: "translate(-4px,-4px)" }}
    >
      {/* Trail */}
      <div
        className="absolute -inset-3 rounded-full opacity-60 blur-md"
        style={{ background: "radial-gradient(circle, var(--violet) 0%, transparent 70%)" }}
      />
      {/* Click ring */}
      {pulseKey > 0 && (
        <span
          key={pulseKey}
          className="ring-pulse absolute left-1 top-1 h-5 w-5 rounded-full border-2"
          style={{ borderColor: "var(--violet)", transformOrigin: "center" }}
        />
      )}
      {/* Cursor arrow */}
      <svg width="18" height="20" viewBox="0 0 18 20" className="drop-shadow-[0_0_6px_var(--violet)]">
        <path
          d="M1.5 1 L1.5 15.5 L5.5 12 L8 17.5 L10.5 16.5 L8 11 L13 11 Z"
          fill="white"
          stroke="black"
          strokeWidth="1"
          strokeLinejoin="round"
        />
      </svg>
      {/* Caption */}
      {target.caption && (
        <div className="shadow-float absolute left-5 top-4 whitespace-nowrap rounded-lg border border-hairline bg-surface px-2.5 py-1.5 font-mono text-[11px] text-foreground">
          {target.caption}
        </div>
      )}
    </div>
  );
}
