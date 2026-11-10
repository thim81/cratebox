/** Preserve entry identity; a removed or replaced entry falls back to its former position. */
export function selectionAfterEdit(previous: { id: string }[], next: { id: string }[], selectedId: string | null): string | undefined {
  if (next.some(entry => entry.id === selectedId)) return selectedId ?? undefined;
  const index = Math.max(0, previous.findIndex(entry => entry.id === selectedId));
  return next[Math.min(index, next.length - 1)]?.id;
}
