"use client";

import { useState } from "react";
import type { TRMContext, ReadyPacket } from "@/types/trm";
import { Badge } from "./Badge";

interface ContextInspectorProps {
  context: TRMContext | null;
  incomingPacket: ReadyPacket | null;
}

export function ContextInspector({ context, incomingPacket }: ContextInspectorProps) {
  const [expanded, setExpanded] = useState(false);

  const contextJson = context
    ? { ...context, incoming_packet: incomingPacket }
    : null;

  return (
    <div className="bg-surface rounded-lg border border-border overflow-hidden">
      <div
        className="flex items-center justify-between px-3.5 py-2.5 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.08em] font-mono">
            Context Inspector
          </span>
          <Badge variant="outline">TRMContext</Badge>
        </div>
        <span
          className="text-xs text-text-muted transition-transform duration-200"
          style={{ transform: expanded ? "rotate(180deg)" : "rotate(0deg)" }}
        >
          ▼
        </span>
      </div>
      {expanded && contextJson && (
        <div className="px-3.5 pb-3.5 border-t border-border-subtle">
          <pre className="text-[11px] font-mono text-text-secondary leading-[1.6] mt-3 whitespace-pre-wrap overflow-auto max-h-[300px]">
            {JSON.stringify(contextJson, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
