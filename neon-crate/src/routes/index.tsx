import { createFileRoute } from "@tanstack/react-router";
import { Fragment, useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  ChevronDown,
  ChevronUp,
  Circle,
  CircleAlert,
  CircleCheck,
  Disc3,
  ListMusic,
  LoaderCircle,
  Search,
  Settings,
  Sun,
  Moon,
  Star,
  Volume2,
  VolumeX,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Deck, type DeckHandle } from "@/components/Deck";
import { CollectionLookupResults } from "@/components/CollectionLookupResults";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import {
  fmtTime,
  type CollectionMatch,
  type CollectionStatus,
  type Playlist,
  type Track,
} from "@/lib/crate-data";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "CrateDeck — DJ Crate Player for m3u8 Playlists" },
      {
        name: "description",
        content:
          "Rekordbox-style DJ crate browser and waveform player for your local m3u8 playlists.",
      },
      { property: "og:title", content: "CrateDeck — DJ Crate Player" },
      {
        property: "og:description",
        content: "Browse crates, sort by BPM and key, and play tracks with a live waveform.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

type SortKey = "number" | "title" | "artist" | "duration" | "rating" | "bpm" | "key";
const SEEK_SECONDS = 5;
const camelot = (k: string) => parseInt(k) * 2 + (k.endsWith("B") ? 1 : 0);

function Index() {
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [lightMode, setLightMode] = useState(false);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [activeId, setActiveId] = useState("");
  const [tracks, setTracks] = useState<Track[]>([]);
  const [collectionStatus, setCollectionStatus] = useState<CollectionStatus>({
    state: "idle",
    message: null,
  });
  const [expandedLookupTrackId, setExpandedLookupTrackId] = useState<string | null>(null);
  const [lookupTrack, setLookupTrack] = useState<Track | null>(null);
  const [lookupMatches, setLookupMatches] = useState<CollectionMatch[]>([]);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const lookupRequestId = useRef(0);
  const [apiError, setApiError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [crateQ, setCrateQ] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ k: SortKey | null; dir: 1 | -1 }>({ k: null, dir: 1 });
  const [sel, setSel] = useState(0);
  const [rangeAnchor, setRangeAnchor] = useState<number | null>(null);
  const [loaded, setLoaded] = useState<{ track: Track; playlist: string } | null>(null);
  const [autoPlay, setAutoPlay] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(0.8);
  const [muted, setMuted] = useState(false);
  const deck = useRef<DeckHandle>(null);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  useEffect(() => {
    if (localStorage.getItem("crate-deck-theme") === "light") {
      setLightMode(true);
      document.documentElement.classList.add("light");
    }
  }, []);

  const toggleTheme = () => {
    const nextLightMode = !lightMode;
    setLightMode(nextLightMode);
    document.documentElement.classList.toggle("light", nextLightMode);
    localStorage.setItem("crate-deck-theme", nextLightMode ? "light" : "dark");
  };

  const refreshPlaylists = useCallback(async () => {
    setRefreshing(true);
    try {
      const response = await fetch(`${apiUrl}/api/playlists`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data: Playlist[] = await response.json();
      setPlaylists(data);
      setApiError(null);
      setActiveId((current) =>
        data.some((p) => p.id === current) ? current : (data[0]?.id ?? ""),
      );
    } catch (e) {
      setPlaylists([]);
      setTracks([]);
      setApiError(`Can't reach ${apiUrl} (${e instanceof Error ? e.message : "request failed"})`);
    } finally {
      setRefreshing(false);
    }
  }, [apiUrl]);

  const refreshCollectionStatus = useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/api/collection/status`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setCollectionStatus((await response.json()) as CollectionStatus);
    } catch {
      setCollectionStatus({ state: "error", message: "Local API unavailable" });
    }
  }, [apiUrl]);

  const lookupTrackInCollection = useCallback(
    async (track: Track) => {
      const requestId = ++lookupRequestId.current;
      if (expandedLookupTrackId === track.id) {
        setExpandedLookupTrackId(null);
        return;
      }
      setExpandedLookupTrackId(track.id);
      setLookupTrack(track);
      setLookupMatches([]);
      setLookupError(null);
      setLookupLoading(true);
      try {
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
        if (lookupRequestId.current === requestId) {
          const matches = data.matches ?? [];
          setLookupMatches(matches);
          const exact = track.rekordbox_id
            ? matches.find((match) => match.id === track.rekordbox_id)
            : undefined;
          if (exact) {
            const applyMetadata = (current: Track): Track => ({
              ...current,
              title: exact.title || current.title,
              artist: exact.artist || current.artist,
              album: exact.album || current.album,
              rating: exact.rating ?? current.rating,
              bpm: exact.bpm || current.bpm,
              key: exact.key || current.key,
              duration: exact.duration || current.duration,
            });
            setTracks((current) => current.map((item) =>
              item.id === track.id ? applyMetadata(item) : item,
            ));
            setLoaded((current) => current?.track.id === track.id
              ? { ...current, track: applyMetadata(current.track) }
              : current);
          }
        }
      } catch (error) {
        if (lookupRequestId.current === requestId) {
          setLookupError(
            error instanceof Error ? error.message : "Collection lookup failed.",
          );
        }
      } finally {
        if (lookupRequestId.current === requestId) setLookupLoading(false);
        void refreshCollectionStatus();
      }
    },
    [apiUrl, expandedLookupTrackId, refreshCollectionStatus],
  );

  const playCollectionMatch = useCallback((match: CollectionMatch) => {
    const id = `collection-${match.id}`;
    if (loaded?.track.id === id) {
      if (!playing) deck.current?.toggle();
      return;
    }
    const track: Track = {
      id,
      rekordbox_id: match.id,
      title: match.title,
      artist: match.artist,
      album: match.album,
      duration: match.duration,
      rating: match.rating,
      bpm: match.bpm,
      key: match.key,
      quality: "Rekordbox collection",
      url: `${apiUrl}/api/collection/stream/${encodeURIComponent(match.id)}`,
    };
    setAutoPlay(true);
    setLoaded({ track, playlist: "Rekordbox collection" });
  }, [apiUrl, loaded, playing]);

  useEffect(() => {
    void refreshPlaylists();
  }, [refreshPlaylists]);

  useEffect(() => {
    void refreshCollectionStatus();
    const interval = window.setInterval(() => void refreshCollectionStatus(), 3000);
    return () => window.clearInterval(interval);
  }, [refreshCollectionStatus]);

  useEffect(() => {
    setSel(0);
    setRangeAnchor(null);
    if (!activeId) {
      setTracks([]);
      return;
    }
    fetch(`${apiUrl}/api/playlists/${encodeURIComponent(activeId)}`)
      .then((r) => r.json())
      .then((d: Playlist) =>
        setTracks(
          (d.tracks ?? []).map((track) => ({
            ...track,
            url: new URL(track.url, `${apiUrl}/`).toString(),
          })),
        ),
      )
      .catch(() => setTracks([]));
  }, [activeId, apiUrl]);

  const activePl = playlists.find((p) => p.id === activeId);
  const crates = playlists.filter((p) => p.name.toLowerCase().includes(crateQ.toLowerCase()));

  const trackNumbers = useMemo(
    () => new Map(tracks.map((track, index) => [track.id, index + 1])),
    [tracks],
  );

  const view = useMemo(() => {
    const s = q.toLowerCase();
    let list = tracks.filter(
      (t) =>
        !s ||
        [t.title, t.artist, t.album, t.key, String(t.bpm), t.quality].some((v) =>
          v.toLowerCase().includes(s),
        ),
    );
    if (sort.k) {
      const k = sort.k;
      list = [...list].sort((a, b) => {
        const va = k === "key" ? camelot(a.key) : k === "number" ? trackNumbers.get(a.id) ?? 0 : a[k],
          vb = k === "key" ? camelot(b.key) : k === "number" ? trackNumbers.get(b.id) ?? 0 : b[k];
        return (
          (typeof va === "string"
            ? va.localeCompare(vb as string)
            : (va as number) - (vb as number)) * sort.dir
        );
      });
    }
    return list;
  }, [tracks, q, sort, trackNumbers]);

  const selectedRange = useMemo(() => {
    if (rangeAnchor === null || !view.length) return [];
    return view.slice(Math.min(rangeAnchor, sel), Math.max(rangeAnchor, sel) + 1);
  }, [view, rangeAnchor, sel]);
  const selectedIds = useMemo(
    () => new Set(selectedRange.map((track) => track.id)),
    [selectedRange],
  );
  const collectionStatusLabel =
    collectionStatus.state === "idle"
      ? "MCP not started"
      : collectionStatus.state === "starting"
        ? "MCP connecting"
        : collectionStatus.state === "connected"
          ? "MCP connected"
          : "MCP error";

  const load = useCallback(
    (t: Track | undefined, play = true) => {
      if (!t) return;
      setAutoPlay(play);
      setLoaded({ track: t, playlist: activePl?.name ?? "" });
    },
    [activePl?.name],
  );

  const step = (d: number) => {
    if (!loaded) return;
    const i = view.findIndex((t) => t.id === loaded.track.id);
    if (i < 0) {
      const targetIndex = d > 0 ? 0 : view.length - 1;
      if (view[targetIndex]) {
        load(view[targetIndex]);
        setSel(targetIndex);
      }
      return;
    }
    const n = view[i + d];
    if (n) {
      load(n);
      setSel(i + d);
    }
  };

  const removeTracks = useCallback(
    async (toRemove: Track[]) => {
      if (!toRemove.length) return;
      const prompt =
        toRemove.length === 1
          ? `Remove “${toRemove[0]!.title}” from “${activePl?.name ?? "this playlist"}”? The audio file will stay on disk.`
          : `Remove ${toRemove.length} selected tracks from “${activePl?.name ?? "this playlist"}”? The audio files will stay on disk.`;
      if (!window.confirm(prompt)) return;
      try {
        const response = await fetch(
          `${apiUrl}/api/playlists/${encodeURIComponent(activeId)}/tracks`,
          {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ track_ids: toRemove.map((track) => track.id) }),
          },
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const removedIds = new Set(toRemove.map((track) => track.id));
        const positions = toRemove
          .map((track) => view.findIndex((item) => item.id === track.id))
          .filter((index) => index >= 0);
        const firstIndex = positions.length ? Math.min(...positions) : 0;
        const remainingView = view.filter((track) => !removedIds.has(track.id));
        const nextIndex = Math.max(0, Math.min(firstIndex, remainingView.length - 1));
        const playlistResponse = await fetch(
          `${apiUrl}/api/playlists/${encodeURIComponent(activeId)}`,
        );
        if (!playlistResponse.ok) throw new Error(`HTTP ${playlistResponse.status}`);
        const updatedPlaylist = (await playlistResponse.json()) as Playlist;
        const updatedTracks = (updatedPlaylist.tracks ?? []).map((track) => ({
          ...track,
          url: new URL(track.url, `${apiUrl}/`).toString(),
        }));
        setTracks(updatedTracks);
        setRangeAnchor(null);
        setSel(nextIndex);
        if (loaded) {
          if (removedIds.has(loaded.track.id)) {
            setLoaded(null);
          } else {
            const refreshedLoaded = updatedTracks.find(
              (track) => loaded.track.rekordbox_id
                ? track.rekordbox_id === loaded.track.rekordbox_id
                : track.id === loaded.track.id,
            );
            if (refreshedLoaded) {
              setLoaded({ ...loaded, track: refreshedLoaded });
            }
          }
        }
        setApiError(null);
        await refreshPlaylists();
      } catch (error) {
        setApiError(
          `Couldn't remove track (${error instanceof Error ? error.message : "request failed"})`,
        );
      }
    },
    [activeId, activePl?.name, apiUrl, view, loaded, refreshPlaylists],
  );

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || settingsOpen) return;
      if (e.metaKey && e.key === "Backspace") {
        e.preventDefault();
        void removeTracks(selectedRange.length ? selectedRange : view[sel] ? [view[sel]] : []);
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (view.length) {
          const next = Math.max(
            0,
            Math.min(view.length - 1, sel + (e.key === "ArrowDown" ? 1 : -1)),
          );
          setSel(next);
          if (e.shiftKey) {
            if (rangeAnchor === null) setRangeAnchor(sel);
          } else {
            setRangeAnchor(null);
            if (e.metaKey) load(view[next]);
          }
        }
      } else if (e.key === "ArrowLeft" && loaded) {
        e.preventDefault();
        deck.current?.seek(-SEEK_SECONDS);
      } else if (e.key === "ArrowRight" && loaded) {
        e.preventDefault();
        deck.current?.seek(SEEK_SECONDS);
      } else if (e.key === "Enter") {
        e.preventDefault();
        setRangeAnchor(null);
        load(view[sel]);
      } else if (e.key === " ") {
        e.preventDefault();
        if (loaded) deck.current?.toggle();
        else load(view[sel]);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [view, sel, loaded, load, settingsOpen, rangeAnchor, selectedRange, removeTracks]);

  useEffect(() => {
    rowRefs.current[sel]?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  const toggleSort = (k: SortKey) => {
    setRangeAnchor(null);
    setSort((s) =>
      s.k === k ? (s.dir === 1 ? { k, dir: -1 } : { k: null, dir: 1 }) : { k, dir: 1 },
    );
  };
  const Th = ({
    k,
    children,
    className = "",
  }: {
    k?: SortKey;
    children: React.ReactNode;
    className?: string;
  }) => (
    <th
      onClick={k ? () => toggleSort(k) : undefined}
      className={`sticky top-0 z-10 bg-card px-2 py-1.5 text-left font-semibold uppercase tracking-wider ${k ? "cursor-pointer select-none hover:text-primary" : ""} ${sort.k === k && k ? "text-primary" : ""} ${className}`}
    >
      <span className="inline-flex items-center gap-0.5">
        {children}
        {sort.k === k &&
          k &&
          (sort.dir === 1 ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
      </span>
    </th>
  );

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <header className="flex items-center gap-3 border-b border-border bg-sidebar px-4 py-2">
        <Disc3 className="text-primary" size={22} />
        <span className="font-mono text-sm font-bold tracking-widest">
          CRATE<span className="text-accent">DECK</span>
        </span>
        <div className="ml-auto flex items-center gap-3 text-xs">
          <div
            role="status"
            aria-label={collectionStatusLabel}
            title={collectionStatus.message
              ? `${collectionStatusLabel}: ${collectionStatus.message}`
              : collectionStatusLabel}
            className={`flex items-center gap-1.5 ${collectionStatus.state === "connected" ? "text-accent" : collectionStatus.state === "error" ? "text-destructive" : "text-muted-foreground"}`}
          >
            {collectionStatus.state === "starting" ? (
              <LoaderCircle size={14} className="animate-spin" />
            ) : collectionStatus.state === "connected" ? (
              <CircleCheck size={14} />
            ) : collectionStatus.state === "error" ? (
              <CircleAlert size={14} />
            ) : (
              <Circle size={14} />
            )}
          </div>
          <Button
            size="icon"
            variant="ghost"
            onClick={toggleTheme}
            aria-label={`Switch to ${lightMode ? "dark" : "light"} mode`}
            title={`Switch to ${lightMode ? "dark" : "light"} mode`}
          >
            {lightMode ? <Moon size={16} /> : <Sun size={16} />}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => setMuted((value) => !value)}
            aria-label={muted ? "Unmute" : "Mute"}
            title={muted ? "Unmute" : "Mute"}
          >
            {muted || volume === 0 ? <VolumeX size={16} /> : <Volume2 size={16} />}
          </Button>
          <Slider
            className="w-24"
            min={0}
            max={1}
            step={0.01}
            value={[muted ? 0 : volume]}
            onValueChange={([value]) => {
              setVolume(value ?? 0);
              setMuted(false);
            }}
            aria-label="Volume"
          />
          <Button
            size="icon"
            variant="ghost"
            onClick={() => setSettingsOpen(true)}
            aria-label="Settings"
          >
            <Settings size={16} />
          </Button>
        </div>
      </header>

      <Deck
        ref={deck}
        track={loaded?.track ?? null}
        playlistName={loaded?.playlist ?? ""}
        autoPlay={autoPlay}
        volume={volume}
        muted={muted}
        onPrev={() => step(-1)}
        onNext={() => step(1)}
        onPlayingChange={setPlaying}
      />

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
          <div className="p-2">
            <div className="relative">
              <Search
                size={14}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                value={crateQ}
                onChange={(e) => setCrateQ(e.target.value)}
                placeholder="Filter crates…"
                className="h-8 pl-7 text-xs"
              />
            </div>
          </div>
          <div className="flex items-center justify-between px-3 pb-1">
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Crates
            </span>
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              onClick={() => void refreshPlaylists()}
              disabled={refreshing}
              aria-label="Refresh playlists"
              title="Refresh playlists"
            >
              <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {apiError && (
              <div className="m-2 rounded border border-destructive/50 p-2 text-xs text-destructive">
                {apiError}
              </div>
            )}
            {crates.map((p) => (
              <button
                key={p.id}
                onClick={() => setActiveId(p.id)}
                className={`block w-full border-l-2 px-3 py-2 text-left transition-colors ${p.id === activeId ? "border-primary bg-sidebar-accent" : "border-transparent hover:bg-sidebar-accent/60"}`}
              >
                <div className="flex items-center gap-2 text-sm font-medium">
                  <ListMusic
                    size={14}
                    className={p.id === activeId ? "text-primary" : "text-muted-foreground"}
                  />
                  <span className="truncate">{p.name}</span>
                </div>
                <div className="mt-0.5 flex gap-3 pl-6 font-mono text-[10px] text-muted-foreground">
                  <span>{p.trackCount} trk</span>
                  <span>{fmtTime(p.duration)}</span>
                  <span>{p.created}</span>
                </div>
              </button>
            ))}
          </div>
          <div className="border-t border-sidebar-border p-2 font-mono text-[10px] leading-relaxed text-muted-foreground">
            ↑↓ browse · ⌘↑↓ load · ⇧↑↓ select · ⌘⌫ remove · ←→ seek 5s
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-3 border-b border-border px-3 py-2">
            <h1 className="truncate text-sm font-semibold">{activePl?.name ?? "—"}</h1>
            <span className="font-mono text-xs text-muted-foreground">{view.length} tracks</span>
            <div className="relative ml-auto w-72">
              <Search
                size={14}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setSel(0);
                  setRangeAnchor(null);
                }}
                placeholder="Search title, artist, key, BPM…"
                className="h-8 pl-7 text-xs"
              />
            </div>
          </div>
          <div className="flex-1 overflow-auto">
            <table className="w-full border-collapse text-xs">
              <thead className="text-[10px] text-muted-foreground">
                <tr>
                  <Th className="w-10">{""}</Th>
                  <Th k="number" className="w-8">#</Th>
                  <Th className="w-6">{""}</Th>
                  <Th k="title">Title</Th>
                  <Th k="artist">Artist</Th>
                  <Th>Album</Th>
                  <Th k="duration">Time</Th>
                  <Th k="rating">Rating</Th>
                  <Th k="bpm">BPM</Th>
                  <Th k="key">Key</Th>
                  <Th>Quality</Th>
                  <Th className="w-10">{""}</Th>
                </tr>
              </thead>
              <tbody>
                {view.map((t, i) => {
                  const isLoaded = loaded?.track.id === t.id;
                  const isRangeSelected = selectedIds.has(t.id);
                  const mp3Bitrate = /\bMP3\s+(\d+)\s*kbps/i.exec(t.quality)?.[1];
                  const bitrate = Number(mp3Bitrate);
                  const qualityClass = mp3Bitrate
                    ? bitrate >= 320
                      ? "border-accent text-accent"
                      : bitrate === 128
                        ? "border-muted-foreground text-muted-foreground"
                        : bitrate > 128
                          ? "border-primary text-primary"
                          : "border-destructive text-destructive"
                    : /FLAC|WAV|AIFF/.test(t.quality)
                      ? "border-accent/40 bg-accent/15 text-accent"
                      : "border-border bg-secondary text-muted-foreground";
                  const qualityTitle = mp3Bitrate
                    ? `${bitrate} kbps · ${bitrate >= 320 ? "Perfect" : bitrate === 128 ? "Minimal" : bitrate > 128 ? "OK" : "Warn"}`
                    : t.quality;
                  return (
                    <Fragment key={t.id}>
                    <tr
                      ref={(el) => {
                        rowRefs.current[i] = el;
                      }}
                      onClick={() => {
                        setSel(i);
                        setRangeAnchor(null);
                      }}
                      onDoubleClick={() => load(t)}
                      aria-selected={i === sel || isRangeSelected}
                      className={`cursor-default border-b border-border/40 ${i === sel ? "bg-primary/20 outline outline-1 -outline-offset-1 outline-primary" : isRangeSelected ? "bg-primary/10" : i % 2 ? "bg-row-alt" : ""} ${isLoaded ? "text-accent" : ""} hover:bg-primary/10`}
                    >
                      <td className="w-10 px-1 py-1 text-center">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-7 text-muted-foreground hover:bg-primary hover:text-primary-foreground"
                          onClick={(event) => {
                            event.stopPropagation();
                            void lookupTrackInCollection(t);
                          }}
                          aria-expanded={expandedLookupTrackId === t.id}
                          aria-label={`${t.rekordbox_id ? "Open exact Rekordbox match for" : "Look up similar tracks for"} ${t.title}`}
                          title={expandedLookupTrackId === t.id ? "Collapse lookup results" : "Search in Rekordbox collection"}
                        >
                          <Search size={14} />
                        </Button>
                      </td>
                      <td className="px-2 py-1 font-mono text-muted-foreground">{trackNumbers.get(t.id)}</td>
                      <td className="w-6 px-1 py-1">
                        <span className="flex h-4 w-4 items-center justify-center">
                          {isLoaded &&
                            (playing ? (
                              <Volume2 size={12} className="animate-pulse text-accent" />
                            ) : (
                              <span className="text-accent">▸</span>
                            ))}
                        </span>
                      </td>
                      <td className="max-w-[16rem] truncate px-2 py-1 font-medium">{t.title}</td>
                      <td className="max-w-[12rem] truncate px-2 py-1">{t.artist}</td>
                      <td className="max-w-[12rem] truncate px-2 py-1 text-muted-foreground">
                        {t.album}
                      </td>
                      <td className="px-2 py-1 font-mono tabular-nums">{fmtTime(t.duration)}</td>
                      <td className="px-2 py-1">
                        <span className="flex">
                          {[1, 2, 3, 4, 5].map((n) => (
                            <Star
                              key={n}
                              size={11}
                              className={n <= t.rating ? "fill-gold text-gold" : "text-border"}
                            />
                          ))}
                        </span>
                      </td>
                      <td className="px-2 py-1 font-mono tabular-nums text-accent">{t.bpm}</td>
                      <td className="px-2 py-1 font-mono font-semibold text-primary">{t.key}</td>
                      <td className="px-2 py-1">
                        <span
                          className={`whitespace-nowrap rounded border px-1.5 py-0.5 font-mono text-[10px] ${qualityClass}`}
                          title={qualityTitle}
                        >
                          {t.quality}
                        </span>
                      </td>
                      <td className="px-1 py-1 text-right">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-7 text-muted-foreground hover:text-destructive"
                          onClick={(event) => {
                            event.stopPropagation();
                            void removeTracks([t]);
                          }}
                          aria-label={`Remove ${t.title} from playlist`}
                          title="Remove from playlist"
                        >
                          <Trash2 size={14} />
                        </Button>
                      </td>
                    </tr>
                    {expandedLookupTrackId === t.id && lookupTrack && (
                      <tr>
                        <td colSpan={12} className="px-3 py-2">
                          <CollectionLookupResults
                            sourceTrack={lookupTrack}
                            matches={lookupMatches}
                            loading={lookupLoading}
                            error={lookupError}
                            onPlay={playCollectionMatch}
                            onCollapse={() => setExpandedLookupTrackId(null)}
                          />
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  );
                })}
                {view.length === 0 && (
                  <tr>
                    <td colSpan={12} className="p-8 text-center text-muted-foreground">
                      No tracks
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </main>
      </div>

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Settings</DialogTitle>
            <DialogDescription>Where your local playlist server is running.</DialogDescription>
          </DialogHeader>
          <label className="text-xs text-muted-foreground">Local API URL</label>
          <Input defaultValue={apiUrl} id="api-url" />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setSettingsOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                setApiUrl(
                  (
                    (document.getElementById("api-url") as HTMLInputElement).value ||
                    "http://localhost:8000"
                  ).replace(/\/$/, ""),
                );
                setSettingsOpen(false);
              }}
            >
              Save
            </Button>
          </div>
        </DialogContent>
      </Dialog>

    </div>
  );
}
