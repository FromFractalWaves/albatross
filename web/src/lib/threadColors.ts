const THREAD_HEX = [
  "#3b82f6", // blue
  "#f59e0b", // amber
  "#22c55e", // green
  "#a855f7", // purple
  "#06b6d4", // cyan
  "#ef4444", // red
] as const;

export function getThreadColor(index: number): string {
  return THREAD_HEX[index % THREAD_HEX.length];
}

export function buildThreadColorMap(threadIds: string[]): Map<string, string> {
  const map = new Map<string, string>();
  threadIds.forEach((id, i) => map.set(id, getThreadColor(i)));
  return map;
}
