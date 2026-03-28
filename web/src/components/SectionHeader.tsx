interface SectionHeaderProps {
  title: string;
  count?: number;
  action?: React.ReactNode;
}

export function SectionHeader({ title, count, action }: SectionHeaderProps) {
  return (
    <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-border-subtle">
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.08em] font-mono">
          {title}
        </span>
        {count !== undefined && (
          <span className="text-[10px] text-text-muted bg-elevated px-1.5 py-px rounded font-mono">
            {count}
          </span>
        )}
      </div>
      {action}
    </div>
  );
}
