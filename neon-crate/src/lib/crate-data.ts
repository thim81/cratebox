export interface Track {
  id: string;
  playlist_id?: string;
  rekordbox_id?: string | null;
  title: string;
  artist: string;
  album: string;
  duration: number; // seconds
  rating: number;
  bpm: number;
  key: string;
  quality: string;
  url: string;
  artwork_url?: string;
  fallback_artwork_url?: string;
  has_artwork?: boolean;
}
export interface Playlist {
  id: string;
  name: string;
  created: string;
  trackCount: number;
  duration: number;
  artwork_url?: string;
  tracks?: Track[];
}

export interface RekordboxPlaylist {
  id: string;
  name: string;
  parent_id: string | null;
  is_folder: boolean;
  is_smart_playlist: boolean;
  track_count: number;
  created_date: string | null;
  sequence: number;
}

export interface ImageResult {
  title: string;
  image_url: string;
  thumbnail_url: string;
  source_url: string;
  source: "Cover Art Archive" | "Google Images" | "DuckDuckGo";
}

export type CollectionState = "idle" | "starting" | "connected" | "error";

export interface CollectionStatus {
  state: CollectionState;
  message: string | null;
}

export interface CollectionMatch {
  id: string;
  title: string;
  artist: string;
  album: string;
  duration: number;
  bpm: number;
  key: string;
  rating: number;
  play_count: number;
  cue_count: number;
  playlist_count: number;
  playlists: { id: string; name: string }[];
  similarity: number;
  quality?: string;
  playable?: boolean;
}

export function fmtTime(sec: number) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const h = Math.floor(sec / 3600),
    m = Math.floor((sec % 3600) / 60),
    ss = Math.floor(sec % 60);
  const p = (x: number) => String(x).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(ss)}` : `${m}:${p(ss)}`;
}
