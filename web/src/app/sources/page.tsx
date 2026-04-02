import Link from "next/link";
import { HubTopBar } from "@/components/HubTopBar";

export default function SourcesHub() {
  return (
    <div className="min-h-screen bg-base">
      <HubTopBar />

      <div className="flex flex-col items-center justify-center gap-6 p-8 pt-12">
        <div className="max-w-2xl w-full flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Link
              href="/"
              className="text-[11px] font-mono uppercase tracking-[0.06em] text-text-muted hover:text-text-secondary transition-colors"
            >
              ← Back to Home
            </Link>
            <h1 className="text-lg font-bold text-text-primary font-mono tracking-tight">
              Live Data Sources
            </h1>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 max-w-2xl w-full">
          <Link
            href="/live/mock"
            className="group bg-surface rounded-lg border border-border hover:bg-hover hover:border-accent-green/30 transition-all p-8 flex flex-col gap-3"
          >
            <span className="text-lg font-bold text-text-primary font-mono tracking-tight">
              Mock Pipeline
            </span>
            <span className="text-[13px] text-text-muted leading-relaxed">
              Replays a scenario with full radio metadata through the full pipeline — capture, preprocessing, TRM routing — and streams results into the live dashboard.
            </span>
            <div className="flex items-center gap-1.5 mt-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent-green" />
              <span className="text-[10px] font-mono uppercase tracking-[0.06em] text-text-muted">
                available
              </span>
            </div>
            <span className="text-[11px] font-mono uppercase tracking-[0.06em] text-accent-green mt-1">
              Open Pipeline →
            </span>
          </Link>
        </div>
      </div>
    </div>
  );
}
