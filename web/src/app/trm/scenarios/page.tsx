"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE } from "@/lib/api";
import { HubTopBar } from "@/components/HubTopBar";
import { TabBar } from "@/components/TabBar";
import { SectionHeader } from "@/components/SectionHeader";
import type { TierGroup } from "@/types/scenarios";

type HubTab = "scenarios" | "live" | "history";

const tabs = [
  { id: "scenarios", label: "SCENARIOS" },
  { id: "live", label: "LIVE", disabled: true },
  { id: "history", label: "HISTORY", disabled: true },
];

function formatTier(tier: string): string {
  return tier.replace(/_/g, " ").toUpperCase();
}

export default function ScenariosPage() {
  const [activeTab, setActiveTab] = useState<HubTab>("scenarios");
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
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to load scenarios");
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen bg-base">
      <HubTopBar />

      <div className="flex flex-col gap-3.5 p-4 px-5">
        <TabBar
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={(id) => setActiveTab(id as HubTab)}
        />

        {loading && (
          <div className="text-text-muted text-sm px-1">Loading scenarios...</div>
        )}

        {error && (
          <div className="text-accent-red text-sm px-1">Error: {error}</div>
        )}

        {!loading && !error && activeTab === "scenarios" && (
          <div className="flex flex-col gap-3.5 max-w-3xl">
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
                      <span className="text-[13px] text-text-primary font-mono">
                        {scenario.name}
                      </span>
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
