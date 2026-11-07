import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import {
  Circle,
  CircleAlert,
  CircleCheck,
  Copy,
  Disc3,
  FolderOpen,
  ImageOff,
  ListPlus,
  LoaderCircle,
  Plus,
  Search,
  Settings,
  Sun,
  Moon,
  Volume2,
  VolumeX,
} from "lucide-react";
import { Deck, type DeckHandle } from "@/components/Deck";
import { ImageSearchDialog } from "@/components/ImageSearchDialog";
import { CollectionTrackSearchDialog } from "@/components/CollectionTrackSearchDialog";
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
  collectionArtworkUrl,
  appendRekordboxTracks,
  insertRekordboxTrackAfter,
  copyRekordboxPlaylist,
  deletePlaylistTracks,
  getCollectionStatus,
  createPlaylist,
  getPlaylist,
  getPlaylists,
  getRekordboxPlaylists,
  getRekordboxPlaylistTracks,
  insertPlaylistSeparator,
  replacePlaylistSeparator,
  lookupCollection,
  PLAYLIST_SEPARATORS,
  reorderPlaylistTrack,
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
  validateSearch: (search: Record<string, unknown>) => {
    const validated: {
      rekordbox_playlist_id?: string;
      rekordbox_track_id?: string;
      crate_playlist_id?: string;
      crate_track_id?: string;
    } = {};
    const playlistId = search["rekordbox_playlist_id"];
    const trackId = search["rekordbox_track_id"];
    if (typeof playlistId === "string" || (typeof playlistId === "number" && Number.isSafeInteger(playlistId))) {
      validated.rekordbox_playlist_id = String(playlistId);
    }
    if (typeof trackId === "string" || (typeof trackId === "number" && Number.isSafeInteger(trackId))) {
      validated.rekordbox_track_id = String(trackId);
    }
    for (const key of ["crate_playlist_id", "crate_track_id"] as const) {
      const value = search[key];
      if (typeof value === "string" || (typeof value === "number" && Number.isSafeInteger(value))) {
        validated[key] = String(value);
      }
    }
    return validated;
  },
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
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const updateCrateUrl = useCallback((playlistId: string, trackId?: string) => {
    void navigate({
      search: (previous) => {
        const next = { ...previous, crate_playlist_id: playlistId };
        delete next.rekordbox_playlist_id;
        delete next.rekordbox_track_id;
        if (trackId) next.crate_track_id = trackId;
        else delete next.crate_track_id;
        return next;
      },
      replace: true,
    });
  }, [navigate]);
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [lightMode, setLightMode] = useState(false);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [activeId, setActiveId] = useState(search.crate_playlist_id ?? "");
  const [tracks, setTracks] = useState<Track[]>([]);
  const [playlistSource, setPlaylistSource] = useState<"crate" | "rekordbox">("crate");
  const selectedTrackByPlaylist = useRef(new Map<string, string>(
    search.crate_playlist_id && search.crate_track_id
      ? [[`crate:${search.crate_playlist_id}`, search.crate_track_id]]
      : [],
  ));
  const pendingRekordboxJump = useRef<{ playlistId: string; trackId: string } | null>(null);
  const appliedRekordboxDeepLink = useRef<string | null>(null);
  const activePlaylistContext = useRef({ id: activeId, source: playlistSource });
  const playlistTracksGeneration = useRef(0);
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
  const [creatingPlaylist, setCreatingPlaylist] = useState(false);
  const [collectionStatus, setCollectionStatus] = useState<CollectionStatus>({
    state: "idle",
    message: null,
  });
  const [expandedLookupTrackId, setExpandedLookupTrackId] = useState<string | null>(null);
  const [expandedSeparatorTrackId, setExpandedSeparatorTrackId] = useState<string | null>(null);
  const [lookupTrack, setLookupTrack] = useState<Track | null>(null);
  const [lookupMatches, setLookupMatches] = useState<CollectionMatch[]>([]);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const lookupRequestId = useRef(0);
  const [apiError, setApiError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [separatorInserting, setSeparatorInserting] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [pendingSeparatorInsert, setPendingSeparatorInsert] = useState<{
    track: Track;
    type: SeparatorType;
    playlistId: string;
    playlistName: string;
  } | null>(null);
  const [pendingSeparatorReplacement, setPendingSeparatorReplacement] = useState<{
    track: Track;
    type: SeparatorType;
  } | null>(null);
  const [pendingCollectionSwap, setPendingCollectionSwap] = useState<{
    sourceTrack: Track;
    match: CollectionMatch;
  } | null>(null);
  const [pendingRemoval, setPendingRemoval] = useState<{
    tracks: Track[];
    playlistId: string;
    playlistName: string;
  } | null>(null);
  const [removingTracks, setRemovingTracks] = useState(false);
  const [separatorType, setSeparatorType] = useState<SeparatorType>("generic");
  const [appendingTrackId, setAppendingTrackId] = useState<string | null>(null);
  const [addingCollectionTrackId, setAddingCollectionTrackId] = useState<string | null>(null);
  const [addTrackSearchOpen, setAddTrackSearchOpen] = useState(false);
  const [appendPlaylistId, setAppendPlaylistId] = useState("");
  const [pendingAppendTrack, setPendingAppendTrack] = useState<Track | null>(null);
  const [crateQ, setCrateQ] = useState("");
  const [q, setQ] = useState("");
  const [missingArtworkOnly, setMissingArtworkOnly] = useState(false);
  const [sort, setSort] = useState<SortState>({ k: null, dir: 1 });
  const [sel, setSel] = useState(0);
  const [rangeAnchor, setRangeAnchor] = useState<number | null>(null);
  const [selectedTrackIds, setSelectedTrackIds] = useState<Set<string>>(() => new Set());
  const [loaded, setLoaded] = useState<{ track: Track; playlist: string } | null>(null);
  const [autoPlay, setAutoPlay] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [playbackDuration, setPlaybackDuration] = useState(0);
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
  const removeConfirmRef = useRef<HTMLButtonElement>(null);

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

  const createCratePlaylist = useCallback(async (name: string) => {
    setCreatingPlaylist(true);
    setApiError(null);
    try {
      const created = await createPlaylist(apiUrl, name);
      setPlaylists(await getPlaylists(apiUrl));
      setTracks([]);
      setActiveId(created.id);
      setPlaylistSource("crate");
      updateCrateUrl(created.id);
      setSel(0);
      setQ("");
      setRangeAnchor(null);
      return true;
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "Could not create the playlist.");
      return false;
    } finally {
      setCreatingPlaylist(false);
    }
  }, [apiUrl, updateCrateUrl]);

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
    setApiError(null);
    if (source === "crate" && activeId) {
      updateCrateUrl(activeId, selectedTrackByPlaylist.current.get(`crate:${activeId}`));
    }
    if (source === "rekordbox" && !rekordboxLoaded) void refreshRekordboxPlaylists();
  };

  const selectCratePlaylist = (playlistId: string) => {
    setPlaylistSource("crate");
    setActiveId(playlistId);
    setApiError(null);
    updateCrateUrl(playlistId, selectedTrackByPlaylist.current.get(`crate:${playlistId}`));
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
      if (loaded?.track.id === id || loaded?.track.rekordbox_id === match.id) {
        deck.current?.toggle();
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
        artwork_url: collectionArtworkUrl(apiUrl, match.id),
      };
      setAutoPlay(true);
      setLoaded({ track, playlist: "Rekordbox collection" });
    },
    [apiUrl, loaded],
  );

  useEffect(() => {
    void refreshPlaylists();
  }, [refreshPlaylists]);

  useEffect(() => {
    void refreshCollectionStatus();
  }, [refreshCollectionStatus]);

  useEffect(() => {
    const generation = ++playlistTracksGeneration.current;
    let active = true;
    setRangeAnchor(null);
    setExpandedSeparatorTrackId(null);
    setPendingSeparatorReplacement(null);
    if (!activeId) {
      setTracks([]);
      return;
    }
    getPlaylist(apiUrl, activeId)
      .then((playlist) => {
        if (active && generation === playlistTracksGeneration.current) {
          setTracks(playlist.tracks ?? []);
        }
      })
      .catch(() => {
        if (active && generation === playlistTracksGeneration.current) setTracks([]);
      });
    return () => {
      active = false;
    };
  }, [activeId, apiUrl]);

  const activePl = playlists.find((p) => p.id === activeId);
  const appendDestination = playlists.find((p) => p.id === appendPlaylistId);
  const activeRekordboxPlaylist = rekordboxPlaylists.find(
    (playlist) => playlist.id === activeRekordboxId,
  );
  const activeRekordboxFolder = rekordboxPlaylists.find(
    (playlist) => playlist.id === rekordboxFolderId,
  );
  useEffect(() => {
    setRangeAnchor(null);
    if (
      !rekordboxLoaded || !activeRekordboxId || !activeRekordboxPlaylist
      || activeRekordboxPlaylist.is_folder
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
  }, [apiUrl, activeRekordboxId, activeRekordboxPlaylist, rekordboxLoaded]);

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
      updateCrateUrl(copied.name);
    } catch (error) {
      setRekordboxError(error instanceof Error ? error.message : "Could not copy the playlist.");
    } finally {
      setCopyingRekordboxId(null);
    }
  }, [activeRekordboxPlaylist, apiUrl, rekordboxTracks.length, refreshPlaylists, updateCrateUrl]);

  const appendTracksToPlaylist = useCallback(
    async (tracks: Track[], destinationId: string) => {
      const destination = playlists.find((playlist) => playlist.id === destinationId);
      const trackIds = tracks.flatMap((track) => track.rekordbox_id ? [track.rekordbox_id] : []);
      if (
        playlistSource !== "rekordbox" || !destination || !tracks.length ||
        trackIds.length !== tracks.length || appendingTrackId !== null
      ) return;

      const generation = ++playlistTracksGeneration.current;
      setAppendingTrackId(tracks.length === 1 ? tracks[0]?.id ?? "__selection__" : "__selection__");
      setApiError(null);
      try {
        await appendRekordboxTracks(apiUrl, destination.id, trackIds);
        await refreshPlaylists();
        toast.success(
          tracks.length === 1
            ? `Added “${tracks[0]?.title ?? "track"}” to ${destination.name}.`
            : `Added ${tracks.length} selected tracks to ${destination.name}.`,
        );
        if (
          generation === playlistTracksGeneration.current &&
          activePlaylistContext.current.source === "crate" &&
          activePlaylistContext.current.id === destination.id
        ) {
          try {
            const playlist = await getPlaylist(apiUrl, destination.id, true);
            if (
              generation === playlistTracksGeneration.current &&
              activePlaylistContext.current.source === "crate" &&
              activePlaylistContext.current.id === destination.id
            ) {
              setTracks(playlist.tracks ?? []);
            }
          } catch {
            // The playlist update succeeded; the next selection will reload its tracks.
          }
        }
      } catch (error) {
        setApiError(
          `Couldn't add ${tracks.length === 1 ? tracks[0]?.title ?? "track" : "the selected tracks"} to ${destination.name} (${error instanceof Error ? error.message : "request failed"})`,
        );
      } finally {
        setAppendingTrackId(null);
      }
    },
    [apiUrl, appendingTrackId, playlistSource, playlists, refreshPlaylists],
  );
  const appendTrackToPlaylist = useCallback(
    (track: Track, destinationId: string) => appendTracksToPlaylist([track], destinationId),
    [appendTracksToPlaylist],
  );
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
        ...(track.artwork_url !== undefined ? { currentImageUrl: track.artwork_url } : {}),
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
          current.map((track) => {
            if (track.id !== imageTarget.trackId) return track;
            const { fallback_artwork_url: _fallbackArtworkUrl, ...trackWithoutFallback } = track;
            return { ...trackWithoutFallback, artwork_url: result.artwork_url };
          }),
        );
      }
      setLoaded((current) => {
        if (
          current?.playlist !== imageTarget.playlistId ||
          current.track.id !== imageTarget.trackId
        ) {
          return current;
        }
        const { fallback_artwork_url: _fallbackArtworkUrl, ...trackWithoutFallback } =
          current.track;
        return {
          ...current,
          track: { ...trackWithoutFallback, artwork_url: result.artwork_url },
        };
      });
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
        (!missingArtworkOnly ||
          (!t.has_artwork &&
            !PLAYLIST_SEPARATORS.some((separator) => separator.trackId === t.rekordbox_id))) &&
        (!s ||
          [t.title, t.artist, t.album, t.genre ?? "", t.key, String(t.bpm), t.quality].some((v) =>
            v.toLowerCase().includes(s),
          )),
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
  }, [currentTracks, missingArtworkOnly, q, sort, trackNumbers]);
  const selectedTrack = view[sel] ?? null;

  const selectionKey = `${playlistSource}:${playlistSource === "crate" ? activeId : activeRekordboxId}`;
  const headerPlaylistName =
    playlistSource === "rekordbox"
      ? (activeRekordboxPlaylist?.name ?? activeRekordboxFolder?.name ?? "Rekordbox playlists")
      : (activePl?.name ?? "");
  const selectTrackAt = useCallback(
    (index: number, list: Track[] = view, preserveSelection = false) => {
      setSel(index);
      const track = list[index];
      if (track) {
        selectedTrackByPlaylist.current.set(selectionKey, track.id);
        if (!preserveSelection) setSelectedTrackIds(new Set([track.id]));
      } else {
        selectedTrackByPlaylist.current.delete(selectionKey);
        if (!preserveSelection) setSelectedTrackIds(new Set());
      }
      if (playlistSource === "crate" && activeId) updateCrateUrl(activeId, track?.id);
    },
    [activeId, playlistSource, selectionKey, updateCrateUrl, view],
  );

  useEffect(() => {
    const rememberedId = selectedTrackByPlaylist.current.get(selectionKey);
    const rememberedIndex = rememberedId
      ? view.findIndex((track) => track.id === rememberedId)
      : -1;
    const nextIndex = rememberedIndex >= 0 ? rememberedIndex : 0;
    setSel(nextIndex);
    setSelectedTrackIds(view[nextIndex] ? new Set([view[nextIndex].id]) : new Set());
    setRangeAnchor(null);
  }, [selectionKey, view]);

  useEffect(() => {
    const pending = pendingRekordboxJump.current;
    if (
      !pending || playlistSource !== "rekordbox" || pending.playlistId !== activeRekordboxId
    ) return;
    const index = view.findIndex((track) => track.rekordbox_id === pending.trackId);
    if (index < 0) return;
    selectTrackAt(index);
    pendingRekordboxJump.current = null;
  }, [activeRekordboxId, playlistSource, selectTrackAt, view]);

  const openRekordboxPlaylistAtTrack = useCallback((playlistId: string, trackId: string) => {
    pendingRekordboxJump.current = { playlistId, trackId };
    setExpandedLookupTrackId(null);
    setQ("");
    setMissingArtworkOnly(false);
    setSort({ k: null, dir: 1 });
    if (playlistSource === "rekordbox" && activeRekordboxId === playlistId) {
      const index = view.findIndex((track) => track.rekordbox_id === trackId);
      if (index >= 0) {
        selectTrackAt(index);
        pendingRekordboxJump.current = null;
      }
      return;
    }
    setRekordboxTracks([]);
    setPlaylistSource("rekordbox");
    setActiveRekordboxId(playlistId);
    setRekordboxFolderId(null);
    if (!rekordboxLoaded) void refreshRekordboxPlaylists();
  }, [
    activeRekordboxId,
    playlistSource,
    rekordboxLoaded,
    refreshRekordboxPlaylists,
    selectTrackAt,
    view,
  ]);

  const navigateToRekordboxPlaylistAtTrack = useCallback((playlistId: string, trackId: string) => {
    void navigate({
      search: {
        rekordbox_playlist_id: playlistId,
        rekordbox_track_id: trackId,
      },
    });
  }, [navigate]);

  useEffect(() => {
    const playlistId = search.rekordbox_playlist_id;
    const trackId = search.rekordbox_track_id;
    const deepLink = playlistId && trackId ? `${playlistId}:${trackId}` : null;
    if (appliedRekordboxDeepLink.current === deepLink) return;
    appliedRekordboxDeepLink.current = deepLink;
    if (playlistId && trackId) {
      openRekordboxPlaylistAtTrack(playlistId, trackId);
    } else if (playlistSource === "rekordbox") {
      pendingRekordboxJump.current = null;
      setPlaylistSource("crate");
    }
  }, [
    openRekordboxPlaylistAtTrack,
    playlistSource,
    search.rekordbox_playlist_id,
    search.rekordbox_track_id,
  ]);

  useEffect(() => {
    const playlist = rekordboxPlaylists.find(
      (item) => item.id === search.rekordbox_playlist_id && !item.is_folder,
    );
    if (playlist) setRekordboxFolderId(playlist.parent_id);
  }, [rekordboxPlaylists, search.rekordbox_playlist_id]);

  const activePlaylistName = activePl?.name ?? "";
  const swapCollectionMatch = useCallback(
    async (sourceTrack: Track, match: CollectionMatch) => {
      if (!activeId) return;
      try {
        const result = await swapPlaylistTrack(apiUrl, activeId, sourceTrack.id, match.id);
        const playlist = await getPlaylist(apiUrl, activeId, true);
        const updatedTracks = playlist.tracks ?? [];
        setTracks(updatedTracks);
        setRangeAnchor(null);
        const replacementTrack = updatedTracks.find((track) => track.id === result.track_id);
        const replacementIndex = updatedTracks.findIndex((track) => track.id === result.track_id);
        selectTrackAt(replacementIndex >= 0 ? replacementIndex : 0, updatedTracks);
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
    [activeId, activePlaylistName, apiUrl, loaded, refreshPlaylists, selectTrackAt],
  );
  const requestCollectionSwap = useCallback((sourceTrack: Track, match: CollectionMatch) => {
    setPendingCollectionSwap({ sourceTrack, match });
  }, []);
  const addCollectionMatch = useCallback(
    async (sourceTrack: Track, match: CollectionMatch) => {
      if (!activeId || playlistSource !== "crate" || addingCollectionTrackId) return;
      const requestPlaylistId = activeId;
      const generation = ++playlistTracksGeneration.current;
      setAddingCollectionTrackId(match.id);
      setApiError(null);
      try {
        const result = await insertRekordboxTrackAfter(
          apiUrl,
          requestPlaylistId,
          sourceTrack.id,
          match.id,
        );
        toast.success(`Added “${match.title}” after “${sourceTrack.title}”.`);
        try {
          const [playlist] = await Promise.all([
            getPlaylist(apiUrl, requestPlaylistId, true),
            refreshPlaylists(),
          ]);
          if (
            generation === playlistTracksGeneration.current &&
            activePlaylistContext.current.id === requestPlaylistId &&
            activePlaylistContext.current.source === "crate"
          ) {
            const updatedTracks = playlist.tracks ?? [];
            setTracks(updatedTracks);
            const addedIndex = updatedTracks.findIndex((track) => track.id === result.track_id);
            if (addedIndex >= 0) selectTrackAt(addedIndex, updatedTracks);
            setApiError(null);
          }
        } catch (error) {
          if (activePlaylistContext.current.id === requestPlaylistId) {
            setApiError(
              `Track added, but the playlist could not be refreshed (${error instanceof Error ? error.message : "request failed"})`,
            );
          }
        }
      } catch (error) {
        if (activePlaylistContext.current.id === requestPlaylistId) {
          setApiError(
            `Couldn't add track (${error instanceof Error ? error.message : "request failed"})`,
          );
        }
      } finally {
        setAddingCollectionTrackId(null);
      }
    },
    [activeId, addingCollectionTrackId, apiUrl, playlistSource, refreshPlaylists, selectTrackAt],
  );

  const addSeparator = useCallback((type: SeparatorType, track: Track) => {
    if (!activeId || playlistSource !== "crate") return;
    if (!PLAYLIST_SEPARATORS.some((item) => item.type === type)) return;
    setPendingSeparatorInsert({
      track,
      type,
      playlistId: activeId,
      playlistName: activePlaylistName || "this playlist",
    });
  }, [activeId, activePlaylistName, playlistSource]);

  const confirmAddSeparator = useCallback(async () => {
    const pending = pendingSeparatorInsert;
    if (!pending) return;
    const { track, type, playlistId: requestPlaylistId } = pending;
      setSeparatorInserting(true);
      try {
        await insertPlaylistSeparator(apiUrl, requestPlaylistId, type, track.id);
        const playlist = await getPlaylist(apiUrl, requestPlaylistId, true);
        await refreshPlaylists();
        if (
          activePlaylistContext.current.id !== requestPlaylistId ||
          activePlaylistContext.current.source !== "crate"
        ) {
          setPendingSeparatorInsert(null);
          return;
        }
        const updatedTracks = playlist.tracks ?? [];
        setTracks(updatedTracks);
        setRangeAnchor(null);
        const query = q.toLowerCase();
        const nextView = updatedTracks.filter(
          (item) =>
            !query ||
            [item.title, item.artist, item.album, item.genre ?? "", item.key, String(item.bpm), item.quality].some(
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
        selectTrackAt(targetIndex >= 0 ? targetIndex : 0, nextView);
        setApiError(null);
        setPendingSeparatorInsert(null);
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
  }, [
      apiUrl,
      pendingSeparatorInsert,
      q,
      refreshPlaylists,
      selectTrackAt,
      sort,
    ]);

  const selectSeparator = useCallback((track: Track) => {
    setExpandedSeparatorTrackId((current) => (current === track.id ? null : track.id));
  }, []);

  const replaceSeparator = useCallback((track: Track, type: SeparatorType) => {
    setPendingSeparatorReplacement({ track, type });
  }, []);

  const confirmReplaceSeparator = useCallback(async () => {
    const pending = pendingSeparatorReplacement;
    if (!activeId || playlistSource !== "crate" || !pending?.track.rekordbox_id) return;
    const requestPlaylistId = activeId;
    const { track, type } = pending;
    const generation = ++playlistTracksGeneration.current;
    setSeparatorInserting(true);
    try {
      await replacePlaylistSeparator(apiUrl, requestPlaylistId, track.id, type);
      const [playlist] = await Promise.all([
        getPlaylist(apiUrl, requestPlaylistId, true),
        refreshPlaylists(),
      ]);
      if (
        generation !== playlistTracksGeneration.current ||
        activePlaylistContext.current.id !== requestPlaylistId ||
        activePlaylistContext.current.source !== "crate"
      )
        return;
      setTracks(playlist.tracks ?? []);
      setExpandedSeparatorTrackId(null);
      setPendingSeparatorReplacement(null);
      setApiError(null);
    } catch (error) {
      setPendingSeparatorReplacement(null);
      if (
        activePlaylistContext.current.id === requestPlaylistId &&
        activePlaylistContext.current.source === "crate"
      ) {
        setApiError(
          `Couldn't replace separator (${error instanceof Error ? error.message : "request failed"})`,
        );
      }
    } finally {
      setSeparatorInserting(false);
    }
  }, [activeId, apiUrl, pendingSeparatorReplacement, playlistSource, refreshPlaylists]);

  const selectedRange = useMemo(() => {
    return view.filter((track) => selectedTrackIds.has(track.id));
  }, [view, selectedTrackIds]);
  const selectedIds = selectedTrackIds;
  const selectedRekordboxTracks = useMemo(() => {
    const selected = new Set(selectedRange.map((track) => track.id));
    return rekordboxTracks.filter((track) => selected.has(track.id));
  }, [rekordboxTracks, selectedRange]);
  const appendSelectedRekordboxTracks = useCallback(() => {
    if (appendDestination) {
      void appendTracksToPlaylist(selectedRekordboxTracks, appendDestination.id);
    }
  }, [appendDestination, appendTracksToPlaylist, selectedRekordboxTracks]);
  const reorderTrack = useCallback(
    async (sourceTrackIds: string[], targetTrackId: string, before: boolean) => {
      if (!activeId || playlistSource !== "crate" || reordering) return;
      const requestPlaylistId = activeId;
      const selectedTrackId = view[sel]?.id;
      setReordering(true);
      try {
        await reorderPlaylistTrack(apiUrl, requestPlaylistId, sourceTrackIds, targetTrackId, before);
        const playlist = await getPlaylist(apiUrl, requestPlaylistId, true);
        if (
          activePlaylistContext.current.id !== requestPlaylistId ||
          activePlaylistContext.current.source !== "crate"
        )
          return;
        const updatedTracks = playlist.tracks ?? [];
        setTracks(updatedTracks);
        setRangeAnchor(null);
        const selectedIndex = updatedTracks.findIndex((track) => track.id === selectedTrackId);
        selectTrackAt(selectedIndex >= 0 ? selectedIndex : 0, updatedTracks);
        setApiError(null);
      } catch (error) {
        if (
          activePlaylistContext.current.id === requestPlaylistId &&
          activePlaylistContext.current.source === "crate"
        ) {
          setApiError(
            `Couldn't reorder track (${error instanceof Error ? error.message : "request failed"})`,
          );
        }
      } finally {
        setReordering(false);
      }
    },
    [activeId, apiUrl, playlistSource, reordering, sel, selectTrackAt, view],
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
      let track = t;
      let playlist = activePl?.name ?? "";
      if (playlistSource === "rekordbox") {
        if (!t.rekordbox_id) return;
        track = {
          ...t,
          url: collectionStreamUrl(apiUrl, t.rekordbox_id),
          artwork_url: collectionArtworkUrl(apiUrl, t.rekordbox_id),
        };
        playlist = activeRekordboxPlaylist?.name ?? "Rekordbox collection";
      }
      setAutoPlay(play);
      setLoaded({ track, playlist });
    },
    [activePl?.name, activeRekordboxPlaylist?.name, apiUrl, playlistSource],
  );

  const step = (d: number) => {
    if (!loaded) return;
    const stepTracks = view;
    const i = stepTracks.findIndex(
      (t) =>
        t.id === loaded.track.id ||
        (t.rekordbox_id && t.rekordbox_id === loaded.track.rekordbox_id),
    );
    if (i < 0) {
      const targetIndex = d > 0 ? 0 : stepTracks.length - 1;
      if (stepTracks[targetIndex]) {
        load(stepTracks[targetIndex], true);
        selectTrackAt(targetIndex);
      }
      return;
    }
    const n = stepTracks[i + d];
    if (n) {
      load(n, true);
      selectTrackAt(i + d);
    }
  };

  const removeTracks = useCallback(
    (toRemove: Track[]) => {
      if (!toRemove.length || playlistSource === "rekordbox" || !activeId) return;
      setPendingRemoval({
        tracks: toRemove,
        playlistId: activeId,
        playlistName: activePl?.name ?? "this playlist",
      });
    },
    [activeId, activePl?.name, playlistSource],
  );

  const confirmRemoveTracks = useCallback(async () => {
    if (!pendingRemoval || removingTracks) return;
    const { tracks: toRemove, playlistId, playlistName } = pendingRemoval;
    setRemovingTracks(true);
    try {
      await deletePlaylistTracks(
        apiUrl,
        playlistId,
        toRemove.map((track) => track.id),
      );
      const stillActive = activeId === playlistId && playlistSource === "crate";
      if (stillActive) {
        const removedIds = new Set(toRemove.map((track) => track.id));
        const positions = toRemove
          .map((track) => view.findIndex((item) => item.id === track.id))
          .filter((index) => index >= 0);
        const firstIndex = positions.length ? Math.min(...positions) : 0;
        const remainingView = view.filter((track) => !removedIds.has(track.id));
        const nextIndex = Math.max(0, Math.min(firstIndex, remainingView.length - 1));
        const updatedPlaylist = await getPlaylist(apiUrl, playlistId, true);
        const updatedTracks = updatedPlaylist.tracks ?? [];
        setTracks(updatedTracks);
        setRangeAnchor(null);
        selectTrackAt(nextIndex, remainingView);
        if (loaded?.playlist === playlistName) {
          if (removedIds.has(loaded.track.id)) {
            setLoaded(null);
          } else {
            const refreshedLoaded = updatedTracks.find((track) =>
              loaded.track.rekordbox_id
                ? track.rekordbox_id === loaded.track.rekordbox_id
                : track.id === loaded.track.id,
            );
            if (refreshedLoaded) setLoaded({ ...loaded, track: refreshedLoaded });
          }
        }
      }
      setApiError(null);
      await refreshPlaylists();
      setPendingRemoval(null);
    } catch (error) {
      setApiError(
        `Couldn't remove track (${error instanceof Error ? error.message : "request failed"})`,
      );
    } finally {
      setRemovingTracks(false);
    }
  }, [
    activeId,
    apiUrl,
    loaded,
    pendingRemoval,
    playlistSource,
    refreshPlaylists,
    removingTracks,
    selectTrackAt,
    view,
  ]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || settingsOpen) return;
      if (e.metaKey && e.key === "Backspace") {
        e.preventDefault();
        if (playlistSource === "crate") {
          void removeTracks(selectedRange.length ? selectedRange : view[sel] ? [view[sel]] : []);
        }
      } else if (
        e.key.toLowerCase() === "l" &&
        !e.metaKey &&
        !e.ctrlKey &&
        !e.altKey &&
        playlistSource === "crate" &&
        view[sel]
      ) {
        e.preventDefault();
        void lookupTrackInCollection(view[sel]);
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const lookupSection = expandedLookupTrackId
          ? Array.from(document.querySelectorAll<HTMLElement>("[data-lookup-source-track]")).find(
              (element) => element.dataset["lookupSourceTrack"] === expandedLookupTrackId,
            )
          : null;
        const lookupRows = Array.from(
          lookupSection?.querySelectorAll<HTMLElement>("[data-lookup-result]") ?? [],
        );
        if (e.key === "ArrowDown" && view[sel]?.id === expandedLookupTrackId && lookupRows[0]) {
          e.preventDefault();
          lookupRows[0].focus();
          return;
        }
        if (
          e.key === "ArrowUp" &&
          view[sel - 1]?.id === expandedLookupTrackId &&
          lookupRows.length
        ) {
          e.preventDefault();
          selectTrackAt(sel - 1);
          lookupRows[lookupRows.length - 1]?.focus();
          return;
        }
        e.preventDefault();
        if (view.length) {
          const next = Math.max(
            0,
            Math.min(view.length - 1, sel + (e.key === "ArrowDown" ? 1 : -1)),
          );
          if (e.shiftKey) {
            const anchor = rangeAnchor ?? sel;
            selectTrackAt(next, view, true);
            setRangeAnchor(anchor);
            setSelectedTrackIds(new Set(
              view.slice(Math.min(anchor, next), Math.max(anchor, next) + 1).map((track) => track.id),
            ));
          } else {
            selectTrackAt(next);
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
    selectTrackAt,
    expandedLookupTrackId,
    lookupTrackInCollection,
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
        onTimeChange={setPlaybackTime}
        onDurationChange={setPlaybackDuration}
        onEditArtwork={editLoadedArtwork}
        onRevealTrack={(track) => void showTrackInFinder(track)}
      />

      <ImageSearchDialog
        apiUrl={apiUrl}
        open={imageTarget !== null}
        query={imageTarget?.query ?? ""}
        {...(imageTarget?.artist !== undefined ? { artist: imageTarget.artist } : {})}
        {...(imageTarget?.album !== undefined ? { album: imageTarget.album } : {})}
        {...(imageTarget?.searchTrack !== undefined ? { track: imageTarget.searchTrack } : {})}
        {...(imageTarget?.currentImageUrl !== undefined
          ? { currentImageUrl: imageTarget.currentImageUrl }
          : {})}
        embedIntoMp3={Boolean(imageTarget?.trackId)}
        {...(sourceTrackToReveal
          ? { onRevealTrack: () => void showTrackInFinder(sourceTrackToReveal) }
          : {})}
        onOpenChange={(open) => {
          if (!open) setImageTarget(null);
        }}
        onChoose={chooseArtwork}
      />

      <CollectionTrackSearchDialog
        apiUrl={apiUrl}
        open={addTrackSearchOpen}
        anchorTrack={selectedTrack}
        addingTrackId={addingCollectionTrackId}
        activeTrackId={loaded?.track.id ?? null}
        activeRekordboxId={loaded?.track.rekordbox_id ?? null}
        playing={playing}
        currentTime={playbackTime}
        duration={playbackDuration}
        onOpenChange={setAddTrackSearchOpen}
        onAdd={addCollectionMatch}
        onPlay={playCollectionMatch}
        onSeekTo={(seconds) => deck.current?.seek(seconds - playbackTime)}
        onOpenRekordboxPlaylist={navigateToRekordboxPlaylistAtTrack}
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
          creatingPlaylist={creatingPlaylist}
          onFilterChange={setCrateQ}
          onSourceChange={changePlaylistSource}
          onRefresh={() => void refreshPlaylists()}
          onRefreshRekordbox={() => void refreshRekordboxPlaylists()}
          onCreatePlaylist={createCratePlaylist}
          onSelectPlaylist={selectCratePlaylist}
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
          <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 border-b border-border px-3 py-2">
            <div className="flex min-w-0 items-center gap-3">
              <h1 className="truncate text-sm font-semibold">
                {headerPlaylistName || "—"}
              </h1>
              {headerPlaylistName && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-7 shrink-0"
                  aria-label="Copy playlist name"
                  title="Copy playlist name"
                  onClick={() =>
                    void navigator.clipboard
                      .writeText(headerPlaylistName)
                      .then(() => toast.success("Playlist name copied"))
                      .catch(() => toast.error("Could not copy playlist name"))
                  }
                >
                  <Copy size={14} />
                </Button>
              )}
              {view[sel] && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-7 shrink-0"
                  aria-label={`Show ${view[sel].title} in Finder`}
                  title="Show selected track in Finder"
                  onClick={() => void showTrackInFinder(view[sel])}
                >
                  <FolderOpen size={14} />
                </Button>
              )}
              {playlistSource === "rekordbox" &&
                activeRekordboxPlaylist &&
                !activeRekordboxPlaylist.is_folder && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 shrink-0"
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
              <span className="shrink-0 font-mono text-xs text-muted-foreground">
                {view.length} tracks
              </span>
            </div>
            {playlistSource === "crate" ? (
              <Button
                size="sm"
                variant="outline"
                className="h-8 gap-1.5"
                disabled={!selectedTrack || addingCollectionTrackId !== null}
                onClick={() => setAddTrackSearchOpen(true)}
              >
                <Plus size={14} />
                Add track
              </Button>
            ) : <span />}
            <div className="flex shrink-0 items-center justify-end gap-2">
              {playlistSource === "crate" && (
                <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  Insert separator
                  <select
                    aria-label="Separator type to insert"
                    className="h-8 rounded border border-input bg-background px-2 text-xs text-foreground"
                    value={separatorType}
                    disabled={separatorInserting}
                    onChange={(event) =>
                      setSeparatorType(event.currentTarget.value as SeparatorType)
                    }
                  >
                    {PLAYLIST_SEPARATORS.map(({ type, label }) => (
                      <option key={type} value={type}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {playlistSource === "rekordbox" &&
                activeRekordboxPlaylist &&
                !activeRekordboxPlaylist.is_folder && (
                  <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <select
                      aria-label="Local CrateDeck playlist to insert into"
                      className="h-8 max-w-56 rounded border border-input bg-background px-2 text-xs text-foreground"
                      value={appendPlaylistId}
                      disabled={playlists.length === 0 || appendingTrackId !== null}
                      onChange={(event) => {
                        setAppendPlaylistId(event.currentTarget.value);
                        setApiError(null);
                      }}
                    >
                      <option value="">Select CrateDeck playlist</option>
                      {playlists.map((playlist) => (
                        <option key={playlist.id} value={playlist.id}>
                          {playlist.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              {playlistSource === "rekordbox" && selectedRange.length > 1 && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 shrink-0"
                  disabled={
                    !appendDestination ||
                    appendingTrackId !== null ||
                    selectedRekordboxTracks.length !== selectedRange.length
                  }
                  onClick={appendSelectedRekordboxTracks}
                  title={
                    appendDestination
                      ? `Add ${selectedRange.length} selected tracks to ${appendDestination.name}`
                      : "Select a CrateDeck playlist first"
                  }
                >
                  {appendingTrackId === "__selection__" ? (
                    <LoaderCircle size={13} className="animate-spin" />
                  ) : (
                    <ListPlus size={14} />
                  )}
                  Add selected ({selectedRange.length})
                </Button>
              )}
              <div className="relative w-72">
                <Search
                  size={14}
                  className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  value={q}
                  onChange={(e) => {
                    setQ(e.target.value);
                    setRangeAnchor(null);
                  }}
                  placeholder="Search title, artist, key, BPM…"
                  className="h-8 pl-7 text-xs"
                />
              </div>
              <Button
                size="icon"
                variant={missingArtworkOnly ? "secondary" : "ghost"}
                className="size-8 shrink-0"
                aria-label={missingArtworkOnly ? "Show all tracks" : "Show tracks without artwork"}
                aria-pressed={missingArtworkOnly}
                title={missingArtworkOnly ? "Show all tracks" : "Show tracks without artwork"}
                onClick={() => {
                  setMissingArtworkOnly((value) => !value);
                  setRangeAnchor(null);
                }}
              >
                <ImageOff size={14} />
              </Button>
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
            expandedSeparatorTrackId={expandedSeparatorTrackId}
            lookupTrack={lookupTrack}
            lookupMatches={lookupMatches}
            lookupLoading={lookupLoading}
            lookupError={lookupError}
            addingCollectionTrackId={addingCollectionTrackId}
            onSort={toggleSort}
            onSelect={(index, modifiers) => {
              if (modifiers.shiftKey) {
                const anchor = rangeAnchor ?? sel;
                selectTrackAt(index, view, true);
                setRangeAnchor(anchor);
                setSelectedTrackIds(new Set(
                  view
                    .slice(Math.min(anchor, index), Math.max(anchor, index) + 1)
                    .map((track) => track.id),
                ));
              } else if (modifiers.toggle) {
                selectTrackAt(index, view, true);
                setRangeAnchor(index);
                const trackId = view[index]?.id;
                if (trackId) {
                  setSelectedTrackIds((current) => {
                    const next = new Set(current);
                    if (next.has(trackId)) next.delete(trackId);
                    else next.add(trackId);
                    return next;
                  });
                }
              } else {
                selectTrackAt(index);
                setRangeAnchor(index);
              }
            }}
            onLoad={load}
            onLookup={(track) => void lookupTrackInCollection(track)}
            onRemove={(track) => void removeTracks([track])}
            onPlayCollectionMatch={playCollectionMatch}
            onSwapCollectionMatch={requestCollectionSwap}
            onAddCollectionMatch={addCollectionMatch}
            onOpenRekordboxPlaylist={navigateToRekordboxPlaylistAtTrack}
            onCollapseLookup={() => setExpandedLookupTrackId(null)}
            onSelectSeparator={selectSeparator}
            onReplaceSeparator={(track, type) => void replaceSeparator(track, type)}
            onInsertSeparator={(type, track) => void addSeparator(type, track)}
            separatorType={separatorType}
            separatorInserting={separatorInserting}
            separatorSwapping={separatorInserting}
            onAppendToPlaylist={(track) => {
              setApiError(null);
              if (appendDestination) {
                void appendTrackToPlaylist(track, appendDestination.id);
              } else {
                setPendingAppendTrack(track);
              }
            }}
            appendDisabled={playlists.length === 0 || appendingTrackId !== null}
            appendDestinationSelected={Boolean(appendDestination)}
            appendingTrackId={appendingTrackId}
            readOnly={playlistSource === "rekordbox"}
            reorderEnabled={playlistSource === "crate" && sort.k === null && !q}
            reordering={reordering}
            onReorder={(sourceTrackIds, targetTrackId, before) =>
              void reorderTrack(sourceTrackIds, targetTrackId, before)
            }
          />
        </main>
      </div>

      <Dialog
        open={pendingAppendTrack !== null}
        onOpenChange={(open) => {
          if (!open) setPendingAppendTrack(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Select a CrateDeck playlist</DialogTitle>
            <DialogDescription>
              Choose where to add “{pendingAppendTrack?.title ?? "this track"}”.
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[60vh] space-y-2 overflow-y-auto">
            {playlists.map((playlist) => (
              <Button
                key={playlist.id}
                variant="outline"
                className="w-full justify-start"
                onClick={() => {
                  const track = pendingAppendTrack;
                  if (!track) return;
                  setAppendPlaylistId(playlist.id);
                  setPendingAppendTrack(null);
                  void appendTrackToPlaylist(track, playlist.id);
                }}
              >
                {playlist.name}
              </Button>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={pendingRemoval !== null}
        onOpenChange={(open) => {
          if (!open && !removingTracks) setPendingRemoval(null);
        }}
      >
        <DialogContent
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            removeConfirmRef.current?.focus();
          }}
        >
          <DialogHeader>
            <DialogTitle>
              {pendingRemoval?.tracks.length === 1 ? "Remove track?" : "Remove selected tracks?"}
            </DialogTitle>
            <DialogDescription>
              {pendingRemoval?.tracks.length === 1
                ? `Remove “${pendingRemoval.tracks[0]?.title ?? "this track"}” from “${pendingRemoval.playlistName}”?`
                : `Remove ${pendingRemoval?.tracks.length ?? 0} selected tracks from “${pendingRemoval?.playlistName ?? "this playlist"}”?`}{" "}
              The audio file{pendingRemoval?.tracks.length === 1 ? "" : "s"} will stay on disk.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              disabled={removingTracks}
              onClick={() => setPendingRemoval(null)}
            >
              Cancel
            </Button>
            <Button
              ref={removeConfirmRef}
              variant="destructive"
              disabled={removingTracks}
              onClick={() => void confirmRemoveTracks()}
            >
              {removingTracks ? <LoaderCircle size={14} className="animate-spin" /> : null}
              Remove
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={pendingSeparatorInsert !== null}
        onOpenChange={(open) => {
          if (!open && !separatorInserting) setPendingSeparatorInsert(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Insert separator?</DialogTitle>
            <DialogDescription>
              {(() => {
                const separator = PLAYLIST_SEPARATORS.find(
                  (item) => item.type === pendingSeparatorInsert?.type,
                );
                return `Insert the ${separator?.label ?? "selected"} separator after “${pendingSeparatorInsert?.track.title}” in “${pendingSeparatorInsert?.playlistName}”? The playlist and its JSON plan will be updated.`;
              })()}
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              disabled={separatorInserting}
              onClick={() => setPendingSeparatorInsert(null)}
            >
              Cancel
            </Button>
            <Button disabled={separatorInserting} onClick={() => void confirmAddSeparator()}>
              {separatorInserting ? <LoaderCircle size={14} className="animate-spin" /> : null}
              Insert
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={pendingSeparatorReplacement !== null}
        onOpenChange={(open) => {
          if (!open && !separatorInserting) setPendingSeparatorReplacement(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Replace separator?</DialogTitle>
            <DialogDescription>
              {(() => {
                const current = PLAYLIST_SEPARATORS.find(
                  (item) => item.trackId === pendingSeparatorReplacement?.track.rekordbox_id,
                );
                const replacement = PLAYLIST_SEPARATORS.find(
                  (item) => item.type === pendingSeparatorReplacement?.type,
                );
                return `Replace ${current?.label ?? "this"} with ${replacement?.label ?? "the selected"} in “${activePlaylistName || "this playlist"}”? The playlist and its JSON plan will be updated.`;
              })()}
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              disabled={separatorInserting}
              onClick={() => setPendingSeparatorReplacement(null)}
            >
              Cancel
            </Button>
            <Button disabled={separatorInserting} onClick={() => void confirmReplaceSeparator()}>
              {separatorInserting ? <LoaderCircle size={14} className="animate-spin" /> : null}
              Replace
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={pendingCollectionSwap !== null}
        onOpenChange={(open) => {
          if (!open) setPendingCollectionSwap(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Replace track?</DialogTitle>
            <DialogDescription>
              Replace “{pendingCollectionSwap?.sourceTrack.title}” in “
              {activePlaylistName || "this playlist"}” with “{pendingCollectionSwap?.match.title}”?
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPendingCollectionSwap(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                const pending = pendingCollectionSwap;
                setPendingCollectionSwap(null);
                if (pending) void swapCollectionMatch(pending.sourceTrack, pending.match);
              }}
            >
              Replace
            </Button>
          </div>
        </DialogContent>
      </Dialog>

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
