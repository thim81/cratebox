export interface Track {
  id: string;
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

export interface ImageResult {
  title: string;
  image_url: string;
  thumbnail_url: string;
  source_url: string;
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
