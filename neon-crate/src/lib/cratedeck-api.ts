import type { CollectionMatch, CollectionStatus, Playlist, Track } from "@/lib/crate-data";

export async function getPlaylists(apiUrl: string): Promise<Playlist[]> {
  const response = await fetch(`${apiUrl}/api/playlists`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as Playlist[];
}

export async function getPlaylist(
  apiUrl: string,
  playlistId: string,
  checkStatus = false,
): Promise<Playlist> {
  const response = await fetch(`${apiUrl}/api/playlists/${encodeURIComponent(playlistId)}`);
  if (checkStatus && !response.ok) throw new Error(`HTTP ${response.status}`);
  const playlist = (await response.json()) as Playlist;
  return {
    ...playlist,
    tracks: (playlist.tracks ?? []).map((track) => ({
      ...track,
      url: new URL(track.url, `${apiUrl}/`).toString(),
    })),
  };
}

export async function getCollectionStatus(apiUrl: string): Promise<CollectionStatus> {
  const response = await fetch(`${apiUrl}/api/collection/status`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as CollectionStatus;
}

export async function lookupCollection(apiUrl: string, track: Track): Promise<CollectionMatch[]> {
  const response = await fetch(`${apiUrl}/api/collection/lookup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      track_id: track.rekordbox_id,
      artist: track.artist,
      title: track.title,
    }),
  });
  const data = (await response.json()) as {
    matches?: CollectionMatch[];
    detail?: string;
  };
  if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
  return data.matches ?? [];
}

export async function deletePlaylistTracks(
  apiUrl: string,
  playlistId: string,
  trackIds: string[],
): Promise<void> {
  const response = await fetch(`${apiUrl}/api/playlists/${encodeURIComponent(playlistId)}/tracks`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ track_ids: trackIds }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}

export async function swapPlaylistTrack(
  apiUrl: string,
  playlistId: string,
  sourceTrackId: string,
  replacementTrackId: string,
): Promise<{ track_id?: string }> {
  const response = await fetch(
    `${apiUrl}/api/playlists/${encodeURIComponent(playlistId)}/tracks/swap`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_track_id: sourceTrackId,
        replacement_track_id: replacementTrackId,
      }),
    },
  );
  const data = (await response.json()) as { track_id?: string; detail?: string };
  if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
  return data;
}

export function collectionStreamUrl(apiUrl: string, trackId: string): string {
  return `${apiUrl}/api/collection/stream/${encodeURIComponent(trackId)}`;
}
