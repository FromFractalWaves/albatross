import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  color?: string;
  variant?: "default" | "solid" | "outline";
  className?: string;
}

export function Badge({ children, color, variant = "default", className }: BadgeProps) {
  const baseClasses =
    "inline-flex items-center gap-1 whitespace-nowrap rounded px-2 py-0.5 font-mono text-[11px] font-medium tracking-[0.02em]";

  if (variant === "solid") {
    return (
      <span
        className={cn(baseClasses, "text-text-inverse", className)}
        style={{ background: color }}
      >
        {children}
      </span>
    );
  }

  if (variant === "outline") {
    return (
      <span
        className={cn(baseClasses, "bg-transparent border border-border", className)}
        style={{ color: color || undefined }}
      >
        {children}
      </span>
    );
  }

  // default variant: tinted background
  return (
    <span
      className={cn(baseClasses, className)}
      style={{
        background: color ? `${color}18` : "#3b82f618",
        color: color || "#3b82f6",
        border: `1px solid ${color ? `${color}30` : "#3b82f630"}`,
      }}
    >
      {children}
    </span>
  );
}
