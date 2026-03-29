interface Tab {
  id: string;
  label: string;
  disabled?: boolean;
}

interface TabBarProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (id: string) => void;
}

export function TabBar({ tabs, activeTab, onTabChange }: TabBarProps) {
  return (
    <div className="flex gap-0.5">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => !tab.disabled && onTabChange(tab.id)}
          disabled={tab.disabled}
          className={`px-3.5 py-1.5 text-[11px] font-semibold font-mono uppercase tracking-[0.06em] rounded-[5px] border-none transition-all duration-150 ${
            activeTab === tab.id
              ? "bg-elevated text-text-primary"
              : tab.disabled
                ? "text-text-muted opacity-50 cursor-not-allowed"
                : "text-text-muted cursor-pointer hover:text-text-secondary"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
