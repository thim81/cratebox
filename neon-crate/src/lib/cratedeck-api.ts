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
  options: {
    artist?: string;
    album?: string;
    track?: string;
    coverArt?: boolean;
    musicbrainz?: boolean;
    googleImages?: boolean;
    duckduckgo?: boolean;
    spotify?: boolean;
    soundcloud?: boolean;
  } = {},
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
      musicbrainz: options.musicbrainz ?? false,
      google_images: options.googleImages ?? true,
      duckduckgo: options.duckduckgo ?? false,
      spotify: options.spotify ?? false,
      soundcloud: options.soundcloud ?? false,
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

export function createPlaylist(apiUrl: string, name: string): Promise<Playlist> {
  return requestJson(apiUrl, "/api/playlists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
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

export async function revealTrackInFinder(apiUrl: string, track: Track): Promise<void> {
  await requestJson<{ revealed: boolean }>(apiUrl, "/api/reveal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      playlist_id: track.playlist_id,
      track_id: track.playlist_id ? track.id : (track.rekordbox_id ?? track.id),
    }),
  });
}

export function getRekordboxPlaylistTracks(apiUrl: string, playlistId: string): Promise<Track[]> {
  return requestJson(apiUrl, `/api/rekordbox/playlists/${encodeURIComponent(playlistId)}/tracks`);
}

export function copyRekordboxPlaylist(
  apiUrl: string,
  playlistId: string,
  name: string,
  updateExisting = false,
): Promise<{ name: string; track_count: number; updated_existing: boolean }> {
  return requestJson(apiUrl, `/api/rekordbox/playlists/${encodeURIComponent(playlistId)}/copy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, update_existing: updateExisting }),
  });
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

export async function reorderPlaylistTrack(
  apiUrl: string,
  playlistId: string,
  sourceTrackId: string,
  targetTrackId: string,
  before: boolean,
): Promise<void> {
  const response = await fetch(
    `${apiUrl}/api/playlists/${encodeURIComponent(playlistId)}/tracks/reorder`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_track_id: sourceTrackId,
        target_track_id: targetTrackId,
        before,
      }),
    },
  );
  const data = (await response.json()) as { detail?: string };
  if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
}

export const PLAYLIST_SEPARATORS = [
  { type: "generic", label: "Generic", trackId: "228753448" },
  { type: "90s", label: "90s", trackId: "118082420" },
  { type: "R&B", label: "R&B", trackId: "38579759" },
  { type: "Ambi", label: "Ambi", trackId: "242295304" },
  { type: "Salsa", label: "Salsa", trackId: "244354734" },
  { type: "Party", label: "Party", trackId: "247266859" },
  { type: "Dance", label: "Dance", trackId: "32984962" },
] as const;

export type SeparatorType = (typeof PLAYLIST_SEPARATORS)[number]["type"];

export async function insertPlaylistSeparator(
  apiUrl: string,
  playlistId: string,
  type: SeparatorType,
  beforeTrackId: string,
): Promise<void> {
  await requestJson(apiUrl, `/api/playlists/${encodeURIComponent(playlistId)}/separators`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, before_track_id: beforeTrackId, confirm_update: true }),
  });
}

export async function replacePlaylistSeparator(
  apiUrl: string,
  playlistId: string,
  separatorRowId: string,
  type: SeparatorType,
): Promise<void> {
  await requestJson(apiUrl, `/api/playlists/${encodeURIComponent(playlistId)}/separators/replace`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      separator_row_id: separatorRowId,
      type,
      confirm_update: true,
    }),
  });
}

export async function appendRekordboxTrack(
  apiUrl: string,
  playlistId: string,
  trackId: string,
): Promise<void> {
  await requestJson(apiUrl, `/api/playlists/${encodeURIComponent(playlistId)}/tracks/append`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ track_id: trackId, confirm_update: true }),
  });
}

export async function insertRekordboxTrackAfter(
  apiUrl: string,
  playlistId: string,
  afterTrackId: string,
  trackId: string,
): Promise<{ track_id: string }> {
  return requestJson(
    apiUrl,
    `/api/playlists/${encodeURIComponent(playlistId)}/tracks/insert-after`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        track_id: trackId,
        after_track_id: afterTrackId,
        confirm_update: true,
      }),
    },
  );
}

export function collectionStreamUrl(apiUrl: string, trackId: string): string {
  return `${apiUrl}/api/collection/stream/${encodeURIComponent(trackId)}`;
}

export function collectionArtworkUrl(apiUrl: string, trackId: string): string {
  return `${apiUrl}/api/collection/tracks/${encodeURIComponent(trackId)}/artwork`;
}
