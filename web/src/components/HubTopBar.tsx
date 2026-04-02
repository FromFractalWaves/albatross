"use client";

import { ThemeToggle } from "./ThemeToggle";

export function HubTopBar() {
  return (
    <div className="sticky top-0 z-50 px-5 py-3 border-b border-border bg-surface flex items-center justify-between">
      <span className="text-sm font-bold text-text-primary tracking-tight">Albatross</span>
      <ThemeToggle />
    </div>
  );
}
