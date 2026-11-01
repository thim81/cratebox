import type {
  CollectionMatch,
  CollectionStatus,
  ImageResult,
  Playlist,
  RekordboxPlaylist,
  Track,
} from "@/lib/crate-data";

async function requestJson<T>(apiUrl: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, init);
  const data = (await response.json().catch(() => ({}))) as { detail?: string };
  if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
  return data as T;
}

export function searchImages(
  apiUrl: string,
  query: string,
  options: { artist?: string; album?: string; track?: string; coverArt?: boolean } = {},
): Promise<ImageResult[]> {
  return requestJson(apiUrl, "/api/images/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      artist: options.artist ?? "",
      album: options.album ?? "",
      track: options.track ?? "",
      cover_art: options.coverArt ?? true,
    }),
  });
}

export function saveArtwork(
  apiUrl: string,
  playlistId: string,
  imageUrl: string,
  trackId?: string,
) {
  return requestJson<{ image_url: string }>(apiUrl, "/api/artwork", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ playlist_id: playlistId, image_url: imageUrl, track_id: trackId }),
  });
}

export async function embedArtwork(
  apiUrl: string,
  playlistId: string,
  trackId: string,
  imageUrl: string,
): Promise<{ backup_id: string; artwork_url: string }> {
  const result = await requestJson<{ backup_id: string; artwork_url: string }>(
    apiUrl,
    "/api/artwork/embed",
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playlist_id: playlistId, track_id: trackId, image_url: imageUrl }),
    },
  );
  return { ...result, artwork_url: new URL(result.artwork_url, `${apiUrl}/`).toString() };
}

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
      artwork_url: track.artwork_url
        ? new URL(track.artwork_url, `${apiUrl}/`).toString()
        : undefined,
      fallback_artwork_url: track.fallback_artwork_url
        ? new URL(track.fallback_artwork_url, `${apiUrl}/`).toString()
        : undefined,
    })),
  };
}

export function getRekordboxPlaylists(apiUrl: string): Promise<RekordboxPlaylist[]> {
  return requestJson(apiUrl, "/api/rekordbox/playlists");
}

export function getRekordboxPlaylistTracks(
  apiUrl: string,
  playlistId: string,
): Promise<Track[]> {
  return requestJson(
    apiUrl,
    `/api/rekordbox/playlists/${encodeURIComponent(playlistId)}/tracks`,
  );
}

export function copyRekordboxPlaylist(
  apiUrl: string,
  playlistId: string,
  name: string,
  updateExisting = false,
): Promise<{ name: string; track_count: number; updated_existing: boolean }> {
  return requestJson(
    apiUrl,
    `/api/rekordbox/playlists/${encodeURIComponent(playlistId)}/copy`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, update_existing: updateExisting }),
    },
  );
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
