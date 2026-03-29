import type { Event } from "@/types/trm";
import { Badge } from "./Badge";

interface EventCardProps {
  event: Event;
  threadColorMap: Map<string, string>;
}

export function EventCard({ event, threadColorMap }: EventCardProps) {
  const eventColor = threadColorMap.get(event.thread_ids[0]) ?? "#3b82f6";

  return (
    <div className="bg-surface rounded-lg border border-border overflow-hidden">
      {/* Header */}
      <div className="px-3.5 py-3 flex items-start gap-2.5">
        <div
          className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0"
          style={{
            backgroundColor: eventColor,
            boxShadow: `0 0 8px ${eventColor}40`,
          }}
        />
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[11px] font-mono font-semibold" style={{ color: eventColor }}>
              {event.event_id}
            </span>
            <Badge variant="outline">{event.status}</Badge>
          </div>
          <span className="text-xs text-text-secondary leading-[1.4]">{event.label}</span>
        </div>
        <span className="text-[10px] font-mono text-text-muted bg-elevated px-1.5 py-0.5 rounded">
          opened {event.opened_at}
        </span>
      </div>

      {/* Thread Links */}
      {event.thread_ids.length > 0 && (
        <div className="px-3.5 py-2.5 border-t border-border-subtle flex flex-wrap gap-1.5">
          {event.thread_ids.map((threadId) => (
            <Badge
              key={threadId}
              variant="outline"
              color={threadColorMap.get(threadId)}
            >
              {threadId}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
