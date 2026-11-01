import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  Circle,
  CircleAlert,
  CircleCheck,
  Copy,
  Disc3,
  LoaderCircle,
  Search,
  Settings,
  Sun,
  Moon,
  Volume2,
  VolumeX,
} from "lucide-react";
import { Deck, type DeckHandle } from "@/components/Deck";
import { ImageSearchDialog } from "@/components/ImageSearchDialog";
import { CrateSidebar } from "@/components/CrateSidebar";
import { TrackTable, type SortKey, type SortState } from "@/components/TrackTable";
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
  collectionStreamUrl,
  copyRekordboxPlaylist,
  deletePlaylistTracks,
  getCollectionStatus,
  getPlaylist,
  getPlaylists,
  getRekordboxPlaylists,
  getRekordboxPlaylistTracks,
  insertPlaylistSeparator,
  lookupCollection,
  PLAYLIST_SEPARATORS,
  revealTrackInFinder,
  swapPlaylistTrack,
  saveArtwork,
  embedArtwork,
} from "@/lib/cratedeck-api";
import {
  fmtTime,
  type CollectionMatch,
  type CollectionStatus,
  type Playlist,
  type RekordboxPlaylist,
  type Track,
} from "@/lib/crate-data";
import type { SeparatorType } from "@/lib/cratedeck-api";

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

const SEEK_SECONDS = 5;
const camelot = (k: string) => parseInt(k) * 2 + (k.endsWith("B") ? 1 : 0);

function Index() {
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [lightMode, setLightMode] = useState(false);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [activeId, setActiveId] = useState("");
  const [tracks, setTracks] = useState<Track[]>([]);
  const [playlistSource, setPlaylistSource] = useState<"crate" | "rekordbox">("crate");
  const activePlaylistContext = useRef({ id: activeId, source: playlistSource });
  useLayoutEffect(() => {
    activePlaylistContext.current = { id: activeId, source: playlistSource };
  }, [activeId, playlistSource]);
  const [rekordboxPlaylists, setRekordboxPlaylists] = useState<RekordboxPlaylist[]>([]);
  const [activeRekordboxId, setActiveRekordboxId] = useState("");
  const [rekordboxFolderId, setRekordboxFolderId] = useState<string | null>(null);
  const [rekordboxTracks, setRekordboxTracks] = useState<Track[]>([]);
  const [rekordboxError, setRekordboxError] = useState<string | null>(null);
  const [rekordboxRefreshing, setRekordboxRefreshing] = useState(false);
  const [rekordboxLoaded, setRekordboxLoaded] = useState(false);
  const [copyingRekordboxId, setCopyingRekordboxId] = useState<string | null>(null);
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
  const [separatorInserting, setSeparatorInserting] = useState(false);
  const [crateQ, setCrateQ] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortState>({ k: null, dir: 1 });
  const [sel, setSel] = useState(0);
  const [rangeAnchor, setRangeAnchor] = useState<number | null>(null);
  const [loaded, setLoaded] = useState<{ track: Track; playlist: string } | null>(null);
  const [autoPlay, setAutoPlay] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(0.8);
  const [muted, setMuted] = useState(false);
  const [imageTarget, setImageTarget] = useState<{
    playlistId: string;
    trackId?: string;
    query: string;
    artist?: string;
    album?: string;
    searchTrack?: string;
    sourceTrack?: Track;
    currentImageUrl?: string;
  } | null>(null);
  const deck = useRef<DeckHandle>(null);

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
      const data = await getPlaylists(apiUrl);
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
      setCollectionStatus(await getCollectionStatus(apiUrl));
    } catch {
      setCollectionStatus({ state: "error", message: "Local API unavailable" });
    }
  }, [apiUrl]);

  const refreshRekordboxPlaylists = useCallback(async () => {
    setRekordboxRefreshing(true);
    setRekordboxError(null);
    try {
      const data = await getRekordboxPlaylists(apiUrl);
      setRekordboxPlaylists(data);
      setActiveRekordboxId((current) =>
        data.some((playlist) => playlist.id === current && !playlist.is_folder) ? current : "",
      );
      setRekordboxFolderId((current) =>
        current && data.some((playlist) => playlist.id === current && playlist.is_folder)
          ? current
          : null,
      );
      setRekordboxLoaded(true);
    } catch (error) {
      setRekordboxError(
        error instanceof Error ? error.message : "Could not load Rekordbox playlists.",
      );
      setRekordboxLoaded(false);
    } finally {
      setRekordboxRefreshing(false);
      void refreshCollectionStatus();
    }
  }, [apiUrl, refreshCollectionStatus]);

  const changePlaylistSource = (source: "crate" | "rekordbox") => {
    setPlaylistSource(source);
    if (source === "rekordbox" && !rekordboxLoaded) void refreshRekordboxPlaylists();
  };

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
        const matches = await lookupCollection(apiUrl, track);
        if (lookupRequestId.current === requestId) {
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
            setTracks((current) =>
              current.map((item) => (item.id === track.id ? applyMetadata(item) : item)),
            );
            setLoaded((current) =>
              current?.track.id === track.id
                ? { ...current, track: applyMetadata(current.track) }
                : current,
            );
          }
        }
      } catch (error) {
        if (lookupRequestId.current === requestId) {
          setLookupError(error instanceof Error ? error.message : "Collection lookup failed.");
        }
      } finally {
        if (lookupRequestId.current === requestId) setLookupLoading(false);
        void refreshCollectionStatus();
      }
    },
    [apiUrl, expandedLookupTrackId, refreshCollectionStatus],
  );

  const playCollectionMatch = useCallback(
    (match: CollectionMatch) => {
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
        url: collectionStreamUrl(apiUrl, match.id),
      };
      setAutoPlay(true);
      setLoaded({ track, playlist: "Rekordbox collection" });
    },
    [apiUrl, loaded, playing],
  );

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
    getPlaylist(apiUrl, activeId)
      .then((playlist) => setTracks(playlist.tracks ?? []))
      .catch(() => setTracks([]));
  }, [activeId, apiUrl]);

  const activePl = playlists.find((p) => p.id === activeId);
  const activeRekordboxPlaylist = rekordboxPlaylists.find(
    (playlist) => playlist.id === activeRekordboxId,
  );
  const activeRekordboxFolder = rekordboxPlaylists.find(
    (playlist) => playlist.id === rekordboxFolderId,
  );
  useEffect(() => {
    setSel(0);
    setRangeAnchor(null);
    if (
      playlistSource !== "rekordbox" ||
      !activeRekordboxId ||
      activeRekordboxPlaylist?.is_folder
    ) {
      setRekordboxTracks([]);
      return;
    }
    let cancelled = false;
    setRekordboxTracks([]);
    setRekordboxError(null);
    getRekordboxPlaylistTracks(apiUrl, activeRekordboxId)
      .then((items) => {
        if (!cancelled) setRekordboxTracks(items);
      })
      .catch((error) => {
        if (!cancelled) {
          setRekordboxError(
            error instanceof Error ? error.message : "Could not load playlist tracks.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiUrl, activeRekordboxId, activeRekordboxPlaylist?.is_folder, playlistSource]);

  const copySelectedRekordboxPlaylist = useCallback(async () => {
    const playlist = activeRekordboxPlaylist;
    if (!playlist || playlist.is_folder || !rekordboxTracks.length) return;
    const name = window.prompt("Name for the CrateDeck copy:", playlist.name)?.trim();
    if (!name) return;
    setCopyingRekordboxId(playlist.id);
    try {
      let copied;
      try {
        copied = await copyRekordboxPlaylist(apiUrl, playlist.id, name);
      } catch (error) {
        if (error instanceof Error && error.message.toLowerCase().includes("already exists")) {
          if (
            !window.confirm(
              `A CrateDeck playlist named “${name}” already exists. Replace its M3U8 and JSON files with this Rekordbox playlist?`,
            )
          )
            return;
          copied = await copyRekordboxPlaylist(apiUrl, playlist.id, name, true);
        } else {
          throw error;
        }
      }
      await refreshPlaylists();
      setRekordboxError(null);
      setActiveId(copied.name);
      setPlaylistSource("crate");
    } catch (error) {
      setRekordboxError(error instanceof Error ? error.message : "Could not copy the playlist.");
    } finally {
      setCopyingRekordboxId(null);
    }
  }, [activeRekordboxPlaylist, apiUrl, rekordboxTracks.length, refreshPlaylists]);
  const editLoadedArtwork = (track: Track) => {
    const playlist = playlists.find((item) => item.name === loaded?.playlist);
    if (playlist) {
      setImageTarget({
        playlistId: playlist.id,
        trackId: track.id,
        query: `${track.artist} ${track.title}`.trim(),
        artist: track.artist,
        album: track.album,
        searchTrack: track.title,
        sourceTrack: track,
        currentImageUrl: track.artwork_url,
      });
    }
  };
  const showTrackInFinder = useCallback(
    async (track: Track) => {
      try {
        await revealTrackInFinder(apiUrl, track);
        setApiError(null);
      } catch (error) {
        setApiError(error instanceof Error ? error.message : "Could not reveal track in Finder.");
      }
    },
    [apiUrl],
  );
  const chooseArtwork = async (image: import("@/lib/crate-data").ImageResult) => {
    if (!imageTarget) return;
    if (imageTarget.trackId) {
      const result = await embedArtwork(
        apiUrl,
        imageTarget.playlistId,
        imageTarget.trackId,
        image.image_url,
      );
      if (activeId === imageTarget.playlistId) {
        setTracks((current) =>
          current.map((track) =>
            track.id === imageTarget.trackId
              ? { ...track, artwork_url: result.artwork_url, fallback_artwork_url: undefined }
              : track,
          ),
        );
      }
      setLoaded((current) =>
        current?.playlist === imageTarget.playlistId && current.track.id === imageTarget.trackId
          ? {
              ...current,
              track: {
                ...current.track,
                fallback_artwork_url: undefined,
                artwork_url: result.artwork_url,
              },
            }
          : current,
      );
    } else {
      await saveArtwork(apiUrl, imageTarget.playlistId, image.image_url);
      setPlaylists((current) =>
        current.map((playlist) =>
          playlist.id === imageTarget.playlistId
            ? { ...playlist, artwork_url: image.image_url }
            : playlist,
        ),
      );
    }
  };
  const currentTracks = playlistSource === "rekordbox" ? rekordboxTracks : tracks;
  const trackNumbers = useMemo(
    () => new Map(currentTracks.map((track, index) => [track.id, index + 1])),
    [currentTracks],
  );

  const view = useMemo(() => {
    const s = q.toLowerCase();
    let list = currentTracks.filter(
      (t) =>
        !s ||
        [t.title, t.artist, t.album, t.key, String(t.bpm), t.quality].some((v) =>
          v.toLowerCase().includes(s),
        ),
    );
    if (sort.k) {
      const k = sort.k;
      list = [...list].sort((a, b) => {
        const va =
            k === "key" ? camelot(a.key) : k === "number" ? (trackNumbers.get(a.id) ?? 0) : a[k],
          vb = k === "key" ? camelot(b.key) : k === "number" ? (trackNumbers.get(b.id) ?? 0) : b[k];
        return (
          (typeof va === "string"
            ? va.localeCompare(vb as string)
            : (va as number) - (vb as number)) * sort.dir
        );
      });
    }
    return list;
  }, [currentTracks, q, sort, trackNumbers]);

  const activePlaylistName = activePl?.name ?? "";
  const swapCollectionMatch = useCallback(
    async (sourceTrack: Track, match: CollectionMatch) => {
      if (
        !activeId ||
        !window.confirm(
          `Replace “${sourceTrack.title}” in “${activePlaylistName || "this playlist"}” with “${match.title}”?`,
        )
      )
        return;
      try {
        const result = await swapPlaylistTrack(apiUrl, activeId, sourceTrack.id, match.id);
        const playlist = await getPlaylist(apiUrl, activeId, true);
        const updatedTracks = playlist.tracks ?? [];
        setTracks(updatedTracks);
        setRangeAnchor(null);
        setSel(
          Math.max(
            0,
            view.findIndex((track) => track.id === sourceTrack.id),
          ),
        );
        const replacementTrack = updatedTracks.find((track) => track.id === result.track_id);
        if (replacementTrack) {
          setLookupTrack(replacementTrack);
          setExpandedLookupTrackId(replacementTrack.id);
          if (loaded?.track.id === sourceTrack.id) {
            setAutoPlay(true);
            setLoaded({ track: replacementTrack, playlist: activePlaylistName });
          }
        }
        setApiError(null);
        await refreshPlaylists();
      } catch (error) {
        setApiError(
          `Couldn't swap track (${error instanceof Error ? error.message : "request failed"})`,
        );
      }
    },
    [activeId, activePlaylistName, apiUrl, loaded, refreshPlaylists, view],
  );

  const addSeparator = useCallback(
    async (type: SeparatorType, track: Track) => {
      if (!activeId || playlistSource !== "crate") return;
      const requestPlaylistId = activeId;
      const separator = PLAYLIST_SEPARATORS.find((item) => item.type === type);
      if (
        !separator ||
        !window.confirm(
          `Insert the ${separator.label} separator before “${track.title}” in “${activePlaylistName || "this playlist"}”? The playlist and its JSON plan will be updated.`,
        )
      )
        return;

      setSeparatorInserting(true);
      try {
        await insertPlaylistSeparator(apiUrl, requestPlaylistId, type, track.id);
        const playlist = await getPlaylist(apiUrl, requestPlaylistId, true);
        await refreshPlaylists();
        if (
          activePlaylistContext.current.id !== requestPlaylistId ||
          activePlaylistContext.current.source !== "crate"
        )
          return;
        const updatedTracks = playlist.tracks ?? [];
        setTracks(updatedTracks);
        setRangeAnchor(null);
        const query = q.toLowerCase();
        const nextView = updatedTracks.filter(
          (item) =>
            !query ||
            [item.title, item.artist, item.album, item.key, String(item.bpm), item.quality].some(
              (value) => value.toLowerCase().includes(query),
            ),
        );
        if (sort.k) {
          const nextNumbers = new Map(updatedTracks.map((item, index) => [item.id, index + 1]));
          const key = sort.k;
          nextView.sort((a, b) => {
            const left =
              key === "key"
                ? camelot(a.key)
                : key === "number"
                  ? (nextNumbers.get(a.id) ?? 0)
                  : a[key];
            const right =
              key === "key"
                ? camelot(b.key)
                : key === "number"
                  ? (nextNumbers.get(b.id) ?? 0)
                  : b[key];
            return (
              (typeof left === "string"
                ? left.localeCompare(right as string)
                : (left as number) - (right as number)) * sort.dir
            );
          });
        }
        const targetIndex = nextView.findIndex((item) => item.id === track.id);
        setSel(targetIndex >= 0 ? targetIndex : 0);
        setApiError(null);
      } catch (error) {
        if (
          activePlaylistContext.current.id === requestPlaylistId &&
          activePlaylistContext.current.source === "crate"
        ) {
          setApiError(
            `Couldn't insert separator (${error instanceof Error ? error.message : "request failed"})`,
          );
        }
      } finally {
        setSeparatorInserting(false);
      }
    },
    [activeId, activePlaylistName, apiUrl, playlistSource, q, refreshPlaylists, sort],
  );

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
    (t: Track | undefined, play = true, fromDeckNavigation = false) => {
      if (!t || (playlistSource === "rekordbox" && !fromDeckNavigation)) return;
      setAutoPlay(play);
      setLoaded({ track: t, playlist: activePl?.name ?? "" });
    },
    [activePl?.name, playlistSource],
  );

  const step = (d: number) => {
    if (!loaded) return;
    const stepTracks = playlistSource === "rekordbox" ? tracks : view;
    const i = stepTracks.findIndex((t) => t.id === loaded.track.id);
    if (i < 0) {
      const targetIndex = d > 0 ? 0 : stepTracks.length - 1;
      if (stepTracks[targetIndex]) {
        load(stepTracks[targetIndex], true, playlistSource === "rekordbox");
        if (playlistSource === "crate") setSel(targetIndex);
      }
      return;
    }
    const n = stepTracks[i + d];
    if (n) {
      load(n, true, playlistSource === "rekordbox");
      if (playlistSource === "crate") setSel(i + d);
    }
  };

  const removeTracks = useCallback(
    async (toRemove: Track[]) => {
      if (!toRemove.length || playlistSource === "rekordbox") return;
      const prompt =
        toRemove.length === 1
          ? `Remove “${toRemove[0]!.title}” from “${activePl?.name ?? "this playlist"}”? The audio file will stay on disk.`
          : `Remove ${toRemove.length} selected tracks from “${activePl?.name ?? "this playlist"}”? The audio files will stay on disk.`;
      if (!window.confirm(prompt)) return;
      try {
        await deletePlaylistTracks(
          apiUrl,
          activeId,
          toRemove.map((track) => track.id),
        );
        const removedIds = new Set(toRemove.map((track) => track.id));
        const positions = toRemove
          .map((track) => view.findIndex((item) => item.id === track.id))
          .filter((index) => index >= 0);
        const firstIndex = positions.length ? Math.min(...positions) : 0;
        const remainingView = view.filter((track) => !removedIds.has(track.id));
        const nextIndex = Math.max(0, Math.min(firstIndex, remainingView.length - 1));
        const updatedPlaylist = await getPlaylist(apiUrl, activeId, true);
        const updatedTracks = updatedPlaylist.tracks ?? [];
        setTracks(updatedTracks);
        setRangeAnchor(null);
        setSel(nextIndex);
        if (loaded) {
          if (removedIds.has(loaded.track.id)) {
            setLoaded(null);
          } else {
            const refreshedLoaded = updatedTracks.find((track) =>
              loaded.track.rekordbox_id
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
    [activeId, activePl?.name, apiUrl, view, loaded, playlistSource, refreshPlaylists],
  );

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || settingsOpen) return;
      if (e.metaKey && e.key === "Backspace") {
        e.preventDefault();
        if (playlistSource === "crate") {
          void removeTracks(selectedRange.length ? selectedRange : view[sel] ? [view[sel]] : []);
        }
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
            if (playlistSource === "crate" && e.metaKey) load(view[next]);
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
        if (playlistSource === "crate") {
          setRangeAnchor(null);
          load(view[sel]);
        }
      } else if (e.key === " ") {
        e.preventDefault();
        if (loaded) deck.current?.toggle();
        else if (playlistSource === "crate") load(view[sel]);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [
    view,
    sel,
    loaded,
    load,
    settingsOpen,
    rangeAnchor,
    selectedRange,
    removeTracks,
    playlistSource,
  ]);

  const toggleSort = (k: SortKey) => {
    setRangeAnchor(null);
    setSort((s) =>
      s.k === k ? (s.dir === 1 ? { k, dir: -1 } : { k: null, dir: 1 }) : { k, dir: 1 },
    );
  };
  const sourceTrackToReveal = imageTarget?.sourceTrack;
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
            title={
              collectionStatus.message
                ? `${collectionStatusLabel}: ${collectionStatus.message}`
                : collectionStatusLabel
            }
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
        onEditArtwork={editLoadedArtwork}
        onRevealTrack={(track) => void showTrackInFinder(track)}
      />

      <ImageSearchDialog
        apiUrl={apiUrl}
        open={imageTarget !== null}
        query={imageTarget?.query ?? ""}
        artist={imageTarget?.artist}
        album={imageTarget?.album}
        track={imageTarget?.searchTrack}
        currentImageUrl={imageTarget?.currentImageUrl}
        embedIntoMp3={Boolean(imageTarget?.trackId)}
        onRevealTrack={
          sourceTrackToReveal ? () => void showTrackInFinder(sourceTrackToReveal) : undefined
        }
        onOpenChange={(open) => {
          if (!open) setImageTarget(null);
        }}
        onChoose={chooseArtwork}
      />

      <div className="flex min-h-0 flex-1">
        <CrateSidebar
          lightMode={lightMode}
          playlists={playlists}
          rekordboxPlaylists={rekordboxPlaylists}
          activeId={activeId}
          activeRekordboxId={activeRekordboxId}
          rekordboxFolderId={rekordboxFolderId}
          source={playlistSource}
          filter={crateQ}
          apiError={apiError}
          rekordboxError={rekordboxError}
          refreshing={refreshing}
          rekordboxRefreshing={rekordboxRefreshing}
          onFilterChange={setCrateQ}
          onSourceChange={changePlaylistSource}
          onRefresh={() => void refreshPlaylists()}
          onRefreshRekordbox={() => void refreshRekordboxPlaylists()}
          onSelectPlaylist={setActiveId}
          onSelectRekordboxPlaylist={setActiveRekordboxId}
          onOpenRekordboxFolder={(folderId) => {
            setRekordboxFolderId(folderId);
            setActiveRekordboxId("");
          }}
          onGoUpRekordboxFolder={() => {
            setRekordboxFolderId(activeRekordboxFolder?.parent_id ?? null);
            setActiveRekordboxId("");
          }}
        />

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-3 border-b border-border px-3 py-2">
            <h1 className="truncate text-sm font-semibold">
              {playlistSource === "rekordbox"
                ? (activeRekordboxPlaylist?.name ??
                  activeRekordboxFolder?.name ??
                  "Rekordbox playlists")
                : (activePl?.name ?? "—")}
            </h1>
            {playlistSource === "rekordbox" &&
              activeRekordboxPlaylist &&
              !activeRekordboxPlaylist.is_folder && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7"
                  disabled={
                    rekordboxTracks.length === 0 || copyingRekordboxId === activeRekordboxId
                  }
                  onClick={() => void copySelectedRekordboxPlaylist()}
                >
                  {copyingRekordboxId === activeRekordboxId ? (
                    <LoaderCircle size={13} className="animate-spin" />
                  ) : (
                    <Copy size={13} />
                  )}
                  Copy to CrateDeck
                </Button>
              )}
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
          <TrackTable
            tracks={view}
            trackNumbers={trackNumbers}
            sort={sort}
            selectedIndex={sel}
            selectedIds={selectedIds}
            loadedTrackId={loaded?.track.id ?? null}
            playing={playing}
            expandedLookupTrackId={expandedLookupTrackId}
            lookupTrack={lookupTrack}
            lookupMatches={lookupMatches}
            lookupLoading={lookupLoading}
            lookupError={lookupError}
            onSort={toggleSort}
            onSelect={(index) => {
              setSel(index);
              setRangeAnchor(null);
            }}
            onLoad={load}
            onLookup={(track) => void lookupTrackInCollection(track)}
            onRemove={(track) => void removeTracks([track])}
            onPlayCollectionMatch={playCollectionMatch}
            onSwapCollectionMatch={swapCollectionMatch}
            onCollapseLookup={() => setExpandedLookupTrackId(null)}
            onInsertSeparator={(type, track) => void addSeparator(type, track)}
            separatorInserting={separatorInserting}
            readOnly={playlistSource === "rekordbox"}
          />
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
