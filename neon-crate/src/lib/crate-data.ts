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

const SAMPLES = [
  "https://wavesurfer.xyz/wavesurfer-code/examples/audio/demo.wav",
  "https://wavesurfer.xyz/wavesurfer-code/examples/audio/mona.mp3",
  "https://wavesurfer.xyz/wavesurfer-code/examples/audio/librivox.mp3",
  "https://upload.wikimedia.org/wikipedia/commons/c/c8/Example.ogg",
];
const s = (n: number) => SAMPLES[n % SAMPLES.length]!;

const raw: Record<string, { name: string; created: string; tracks: Omit<Track, "id" | "url">[] }> = {
  "deep-house": {
    name: "Deep House Night Ride",
    created: "2026-03-14",
    tracks: [
      { title: "Midnight Boulevard", artist: "Kaito Rivers", album: "Neon Drive EP", duration: 372, rating: 5, bpm: 122, key: "8A", quality: "FLAC 24-bit/48kHz" },
      { title: "Velvet Static", artist: "Luma Grey", album: "After Hours", duration: 418, rating: 4, bpm: 121, key: "9A", quality: "FLAC 16-bit/44.1kHz" },
      { title: "Coastline Memory", artist: "Oren Vale", album: "Shorelines", duration: 395, rating: 4, bpm: 120, key: "7A", quality: "MP3 320kbps" },
      { title: "Warm Concrete", artist: "Delphine Moss", album: "City Heat", duration: 441, rating: 3, bpm: 123, key: "8B", quality: "WAV 24-bit/96kHz" },
      { title: "Taillights", artist: "Kaito Rivers", album: "Neon Drive EP", duration: 360, rating: 5, bpm: 122, key: "10A", quality: "FLAC 24-bit/48kHz" },
      { title: "Soft Focus", artist: "Nightjar", album: "Lowlight", duration: 402, rating: 2, bpm: 119, key: "6A", quality: "AAC 256kbps" },
    ],
  },
  techno: {
    name: "Techno Warehouse Peak",
    created: "2026-05-02",
    tracks: [
      { title: "Iron Lung", artist: "Sektor 9", album: "Concrete Ritual", duration: 389, rating: 5, bpm: 132, key: "1A", quality: "WAV 24-bit/48kHz" },
      { title: "Pressure System", artist: "Halle Kova", album: "Pressure", duration: 412, rating: 4, bpm: 134, key: "2A", quality: "FLAC 24-bit/48kHz" },
      { title: "Strobe Theory", artist: "Unit Null", album: "Strobe", duration: 356, rating: 4, bpm: 135, key: "12A", quality: "MP3 320kbps" },
      { title: "Hangar 4", artist: "Sektor 9", album: "Concrete Ritual", duration: 447, rating: 3, bpm: 133, key: "1B", quality: "FLAC 16-bit/44.1kHz" },
      { title: "Black Mirror Floor", artist: "Ves Tarr", album: "Reflections", duration: 398, rating: 5, bpm: 136, key: "3A", quality: "AIFF 24-bit/48kHz" },
    ],
  },
  dnb: {
    name: "Drum & Bass Rollers",
    created: "2026-06-21",
    tracks: [
      { title: "Liquid Circuit", artist: "Bluestep", album: "Currents", duration: 324, rating: 5, bpm: 174, key: "5A", quality: "FLAC 24-bit/44.1kHz" },
      { title: "Roller Coaster Bass", artist: "Mako Line", album: "Roll Out", duration: 301, rating: 4, bpm: 172, key: "4A", quality: "MP3 320kbps" },
      { title: "Amen Signal", artist: "Kinetic Form", album: "Breakscience", duration: 288, rating: 3, bpm: 175, key: "6B", quality: "WAV 16-bit/44.1kHz" },
      { title: "Night Bus", artist: "Bluestep", album: "Currents", duration: 336, rating: 4, bpm: 174, key: "5B", quality: "FLAC 24-bit/44.1kHz" },
      { title: "Subway Echo", artist: "Ravel Dusk", album: "Underpass", duration: 315, rating: 2, bpm: 170, key: "7A", quality: "AAC 256kbps" },
    ],
  },
  melodic: {
    name: "Melodic Sunset Lounge",
    created: "2026-08-09",
    tracks: [
      { title: "Golden Hour Drift", artist: "Selene Arc", album: "Horizon", duration: 452, rating: 5, bpm: 118, key: "11B", quality: "FLAC 24-bit/96kHz" },
      { title: "Amber Waves", artist: "Tomas Edel", album: "Dunes", duration: 431, rating: 4, bpm: 120, key: "12B", quality: "FLAC 24-bit/48kHz" },
      { title: "Last Light", artist: "Selene Arc", album: "Horizon", duration: 405, rating: 5, bpm: 122, key: "10B", quality: "WAV 24-bit/48kHz" },
      { title: "Paper Lanterns", artist: "Mira Ostin", album: "Festival", duration: 389, rating: 3, bpm: 121, key: "11A", quality: "MP3 320kbps" },
    ],
  },
};

let n = 0;
export const MOCK_PLAYLISTS: Playlist[] = Object.entries(raw).map(([id, p]) => {
  const tracks = p.tracks.map((t, i) => ({ ...t, id: `${id}-${i + 1}`, url: s(n++) }));
  return { id, name: p.name, created: p.created, trackCount: tracks.length, duration: tracks.reduce((a, t) => a + t.duration, 0), tracks };
});

export function fmtTime(sec: number) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), ss = Math.floor(sec % 60);
  const p = (x: number) => String(x).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(ss)}` : `${m}:${p(ss)}`;
}

export const FASTAPI_SNIPPET = `# From the neon-crate folder
# From neon-crate: uv run --with fastapi --with uvicorn --with mutagen uvicorn server:app --port 8000
#
# The complete backend is in server.py. It serves:
#   GET /api/playlists
#   GET /api/playlists/{playlist_id}
#   GET /api/stream?playlist_id=...&track_id=...
#
# PLAYLIST_DIR can point to any folder containing .m3u or .m3u8 files.
# Streaming is limited to audio files referenced by a playlist in that folder.
`;
