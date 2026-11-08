import type { Track } from "@/lib/crate-data";

export function updateTrackRating(
  tracks: Track[],
  trackId: string,
  rating: number,
  rekordboxId?: string,
): Track[] {
  return tracks.map((track) =>
    track.id === trackId || (rekordboxId && track.rekordbox_id === rekordboxId)
      ? { ...track, rating }
      : track,
  );
}
