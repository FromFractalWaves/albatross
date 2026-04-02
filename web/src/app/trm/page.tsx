import Link from "next/link";
import { HubTopBar } from "@/components/HubTopBar";

export default function TRMHub() {
  return (
    <div className="min-h-screen bg-base">
      <HubTopBar />

      <div className="flex flex-col items-center justify-center gap-6 p-8 pt-24">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 max-w-2xl w-full">
          <Link
            href="/trm/scenarios"
            className="group bg-surface rounded-lg border border-border hover:bg-hover hover:border-accent-blue/30 transition-all p-8 flex flex-col gap-3"
          >
            <span className="text-lg font-bold text-text-primary font-mono tracking-tight">
              Scenarios
            </span>
            <span className="text-[13px] text-text-muted leading-relaxed">
              Run scenarios, visualize thread decisions, view scoring
            </span>
            <span className="text-[11px] font-mono uppercase tracking-[0.06em] text-accent-blue mt-2">
              Browse Scenarios →
            </span>
          </Link>
        </div>
      </div>
    </div>
  );
}
