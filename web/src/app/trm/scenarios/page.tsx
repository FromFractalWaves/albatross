"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE } from "@/lib/api";
import { HubTopBar } from "@/components/HubTopBar";
import { SectionHeader } from "@/components/SectionHeader";
import type { TierGroup } from "@/types/scenarios";

function formatTier(tier: string): string {
  return tier
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function formatScenarioName(name: string): string {
  return name
    .replace(/^scenario_\d+_/, "")
    .replace(/_/g, " ")
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export default function ScenariosPage() {
  const [tiers, setTiers] = useState<TierGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/scenarios`)
      .then((res) => res.json())
      .then((data) => {
        setTiers(data);
        setLoading(false);
      })
      .catch(() => {
        setError("Failed to load scenarios. Is the API running?");
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen bg-base">
      <HubTopBar />

      <div className="max-w-3xl mx-auto px-5 py-4 flex flex-col gap-4">
        <Link
          href="/trm"
          className="text-[11px] font-mono uppercase tracking-[0.06em] text-text-muted hover:text-text-secondary transition-colors"
        >
          ← Back to TRM
        </Link>

        <h1 className="text-lg font-bold text-text-primary font-mono tracking-tight">
          Scenarios
        </h1>

        {loading && (
          <div className="text-text-muted text-sm">Loading scenarios...</div>
        )}

        {error && (
          <div className="text-accent-red text-sm">{error}</div>
        )}

        {!loading && !error && tiers.length === 0 && (
          <div className="text-text-muted text-sm">No scenarios found.</div>
        )}

        {!loading && !error && tiers.length > 0 && (
          <div className="flex flex-col gap-3.5">
            {tiers.map((tierGroup) => (
              <div
                key={tierGroup.tier}
                className="bg-surface rounded-lg border border-border overflow-hidden"
              >
                <SectionHeader
                  title={formatTier(tierGroup.tier)}
                  count={tierGroup.scenarios.length}
                />
                <div>
                  {tierGroup.scenarios.map((scenario, i) => (
                    <Link
                      key={scenario.name}
                      href={`/trm/scenarios/${tierGroup.tier}/${scenario.name}`}
                      className={`px-3.5 py-3 flex items-center justify-between hover:bg-hover transition-colors cursor-pointer ${
                        i < tierGroup.scenarios.length - 1 ? "border-b border-border-subtle" : ""
                      }`}
                    >
                      <div className="flex flex-col gap-0.5">
                        <span className="text-[13px] text-text-primary font-mono">
                          {formatScenarioName(scenario.name)}
                        </span>
                        <span className="text-[11px] text-text-muted font-mono">
                          {scenario.name}
                        </span>
                      </div>
                      <span className="text-text-muted text-xs">›</span>
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
