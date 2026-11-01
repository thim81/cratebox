export interface Track {
  id: string;
  title: string;
  artist: string;
  album: string;
  duration: number; // seconds
  rating: number;
  bpm: number;
  key: string;
  quality: string;
  url: string;
}
export interface Playlist {
  id: string;
  name: string;
  created: string;
  trackCount: number;
  duration: number;
  tracks?: Track[];
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
  similarity: number;
}

export function fmtTime(sec: number) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const h = Math.floor(sec / 3600),
    m = Math.floor((sec % 3600) / 60),
    ss = Math.floor(sec % 60);
  const p = (x: number) => String(x).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(ss)}` : `${m}:${p(ss)}`;
}
