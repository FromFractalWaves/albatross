export function HubTopBar() {
  return (
    <div className="sticky top-0 z-50 px-5 py-3 border-b border-border bg-surface flex items-center gap-3">
      <span className="text-sm font-bold text-text-primary tracking-tight">TRM</span>
      <div className="w-px h-4 bg-border" />
      <span className="text-xs text-text-muted">Thread Routing Module</span>
    </div>
  );
}
