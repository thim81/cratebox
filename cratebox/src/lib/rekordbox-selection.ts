import type { Track } from './crate-data';

export function tracksInSavedOrder(
  tracks: Track[],
  entries: { entry_id: string; track_id: string }[],
): Track[] | null {
  if (entries.length !== tracks.length) return null;
  const byEntry = new Map(tracks.map(track => [track.id, track]));
  const ordered: Track[] = [];
  for (const entry of entries) {
    const track = byEntry.get(entry.entry_id);
    if (!track || track.rekordbox_id !== entry.track_id) return null;
    ordered.push(track);
    byEntry.delete(entry.entry_id);
  }
  return ordered;
}

/** Preserve entry identity; a removed or replaced entry falls back to its former position. */
export function selectionAfterEdit(previous: { id: string }[], next: { id: string }[], selectedId: string | null): string | undefined {
  if (next.some(entry => entry.id === selectedId)) return selectedId ?? undefined;
  const index = Math.max(0, previous.findIndex(entry => entry.id === selectedId));
  return next[Math.min(index, next.length - 1)]?.id;
}
