import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { LoaderCircle, Pause, Play, Plus, Search, Star, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PlaylistMembershipBadge } from "@/components/PlaylistMembershipBadge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { fmtTime, type CollectionMatch, type Track } from "@/lib/crate-data";
import { lookupCollection } from "@/lib/cratedeck-api";

interface Props {
  apiUrl: string;
  open: boolean;
  anchorTrack: Track | null;
  addingTrackId: string | null;
  activeTrackId: string | null;
  activeRekordboxId: string | null;
  playing: boolean;
  currentTime: number;
  duration: number;
  onOpenChange: (open: boolean) => void;
  onAdd: (track: Track, match: CollectionMatch) => Promise<void>;
  onPlay: (match: CollectionMatch) => void;
  onSeekTo: (seconds: number) => void;
  onOpenRekordboxPlaylist: (playlistId: string, trackId: string) => void;
}

export function CollectionTrackSearchDialog({
  apiUrl,
  open,
  anchorTrack,
  addingTrackId,
  activeTrackId,
  activeRekordboxId,
  playing,
  currentTime,
  duration,
  onOpenChange,
  onAdd,
  onPlay,
  onSeekTo,
  onOpenRekordboxPlaylist,
}: Props) {
  const [artist, setArtist] = useState("");
  const [title, setTitle] = useState("");
  const [matches, setMatches] = useState<CollectionMatch[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const requestId = useRef(0);
  const resultsRef = useRef<HTMLDivElement>(null);
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const activeMatch = matches.find(
    (match) =>
      activeTrackId === `collection-${match.id}` || activeRekordboxId === match.id,
  );

  useEffect(() => {
    if (!open) return;
    setArtist("");
    setTitle("");
    setMatches([]);
    setError(null);
    setSearched(false);
  }, [open, anchorTrack]);

  useEffect(() => {
    setSelectedMatchId(matches[0]?.id ?? null);
    if (matches.length) {
      resultsRef.current?.querySelector<HTMLElement>("[data-add-result]")?.focus();
    }
  }, [matches]);

  async function search(event: FormEvent) {
    event.preventDefault();
    const request = ++requestId.current;
    setLoading(true);
    setError(null);
    setMatches([]);
    setSearched(true);
    try {
      const results = await lookupCollection(apiUrl, {
        id: "collection-search",
        rekordbox_id: null,
        artist,
        title,
        album: "",
        duration: 0,
        rating: 0,
        bpm: 0,
        key: "",
        quality: "",
        url: "",
      });
      if (request === requestId.current) setMatches(results);
    } catch (cause) {
      if (request === requestId.current) {
        setError(cause instanceof Error ? cause.message : "Collection lookup failed.");
      }
    } finally {
      if (request === requestId.current) setLoading(false);
    }
  }

  function navigateResults(event: KeyboardEvent<HTMLDivElement>) {
    if (!["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) return;
    const target = event.target as HTMLElement;
    const row = target.closest<HTMLElement>("[data-add-result]");
    if (!row || target.closest("button")) return;
    const match = matches.find((item) => item.id === row.dataset.addResult);
    if (!match) return;

    event.preventDefault();
    event.stopPropagation();
    if (event.key === "Enter" || event.key === " ") {
      if (match.playable !== false) onPlay(match);
      return;
    }
    const rows = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>("[data-add-result]"),
    );
    const next = rows[rows.indexOf(row) + (event.key === "ArrowDown" ? 1 : -1)];
    if (next) {
      setSelectedMatchId(next.dataset.addResult ?? null);
      next.focus();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-7xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add a track</DialogTitle>
          <DialogDescription>
            Search by artist, title, or both. The selected result will be inserted after
            {anchorTrack ? ` “${anchorTrack.title}”` : " the selected track"}.
          </DialogDescription>
        </DialogHeader>
        <form className="grid gap-2 sm:grid-cols-[1fr_1.4fr_auto]" onSubmit={search}>
          <Input
            value={artist}
            onChange={(event) => setArtist(event.target.value)}
            placeholder="Artist"
            aria-label="Artist"
          />
          <Input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Track title"
            aria-label="Track title"
          />
          <Button type="submit" disabled={loading || (!artist.trim() && !title.trim())}>
            {loading ? <LoaderCircle className="animate-spin" /> : <Search />}
            Search
          </Button>
        </form>
        {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        {loading && <p className="py-4 text-center text-sm text-muted-foreground">Searching the collection…</p>}
        {activeMatch && (
          <div className="flex items-center gap-3 rounded-md border border-border bg-secondary/50 px-3 py-2">
            <Button
              size="icon"
              variant="secondary"
              className="size-8 shrink-0"
              onClick={() => onPlay(activeMatch)}
              aria-label={playing ? "Pause lookup track" : "Play lookup track"}
              title={playing ? "Pause" : "Play"}
            >
              {playing ? <Pause size={15} /> : <Play size={15} />}
            </Button>
            <span className="min-w-0 max-w-56 truncate text-xs font-medium" title={`${activeMatch.artist} — ${activeMatch.title}`}>
              {activeMatch.artist} — {activeMatch.title}
            </span>
            <Slider
              className="min-w-24 flex-1"
              min={0}
              max={Math.max(duration || activeMatch.duration, 1)}
              step={0.1}
              value={[Math.min(currentTime, duration || activeMatch.duration)]}
              onValueChange={([seconds]) => onSeekTo(seconds ?? 0)}
              aria-label="Seek in lookup track"
            />
            <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
              {fmtTime(currentTime)} / {fmtTime(duration || activeMatch.duration)}
            </span>
          </div>
        )}
        {!loading && matches.length > 0 && (
          <div
            ref={resultsRef}
            className="overflow-x-auto rounded border border-border"
            onKeyDown={navigateResults}
          >
            <div className="grid min-w-[970px] grid-cols-[1rem_minmax(10rem,1.4fr)_minmax(8rem,1fr)_minmax(8rem,1fr)_4.5rem_3.5rem_6rem_4rem_4rem_4.5rem_2.5rem_5rem] gap-2 bg-muted/50 px-3 py-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              <span />
              <span>Title</span>
              <span>Artist</span>
              <span>Album</span>
              <span className="text-center">Stars</span>
              <span className="text-right">Plays</span>
              <span>Quality</span>
              <span className="text-right">Time</span>
              <span className="text-right">Lists</span>
              <span className="text-right">Match</span>
              <span className="sr-only">Play</span>
              <span />
            </div>
            {matches.map((match) => (
              <div
                key={match.id}
                data-add-result={match.id}
                tabIndex={0}
                aria-current={selectedMatchId === match.id ? "true" : undefined}
                className={`grid min-w-[970px] grid-cols-[1rem_minmax(10rem,1.4fr)_minmax(8rem,1fr)_minmax(8rem,1fr)_4.5rem_3.5rem_6rem_4rem_4rem_4.5rem_2.5rem_5rem] items-center gap-2 border-t border-border px-3 py-2 text-xs outline-none focus-visible:ring-1 focus-visible:ring-primary ${selectedMatchId === match.id ? "bg-primary/10" : ""} ${activeTrackId === `collection-${match.id}` || activeRekordboxId === match.id ? "text-accent" : ""}`}
                onClick={(event) => {
                  if ((event.target as HTMLElement).closest("button")) return;
                  setSelectedMatchId(match.id);
                  event.currentTarget.focus();
                }}
                onDoubleClick={(event) => {
                  if ((event.target as HTMLElement).closest("button") || match.playable === false)
                    return;
                  onPlay(match);
                }}
              >
                <span className="flex h-4 items-center justify-center" aria-hidden="true">
                  {(activeTrackId === `collection-${match.id}` || activeRekordboxId === match.id) &&
                    (playing ? (
                      <Volume2 size={12} className="animate-pulse text-accent" />
                    ) : (
                      <span className="text-accent">▸</span>
                    ))}
                </span>
                <span className="truncate font-medium" title={match.title}>{match.title}</span>
                <span className="truncate text-muted-foreground" title={match.artist}>{match.artist}</span>
                <span className="truncate text-muted-foreground" title={match.album}>{match.album || "—"}</span>
                <span
                  className="flex justify-center gap-0.5"
                  role="img"
                  aria-label={`Rating: ${match.rating ?? 0} out of 5 stars`}
                >
                  {[1, 2, 3, 4, 5].map((star) => (
                    <Star
                      key={star}
                      size={10}
                      className={star <= (match.rating ?? 0) ? "fill-gold text-gold" : "text-border"}
                    />
                  ))}
                </span>
                <span className="text-right font-mono text-muted-foreground">
                  {(match.play_count ?? 0).toLocaleString()}
                </span>
                {match.quality ? (
                  <span
                    className="w-fit max-w-full truncate whitespace-nowrap rounded border border-accent px-1 py-px font-mono text-[9px] text-accent"
                    title={match.quality}
                  >
                    {match.quality}
                  </span>
                ) : <span className="text-muted-foreground">—</span>}
                <span className="text-right font-mono text-muted-foreground">{fmtTime(match.duration)}</span>
                <span className="text-right">
                  <PlaylistMembershipBadge
                    count={match.playlist_count ?? 0}
                    playlists={match.playlists ?? []}
                    onSelect={(playlistId) => {
                      onOpenRekordboxPlaylist(playlistId, match.id);
                      onOpenChange(false);
                    }}
                  />
                </span>
                <span className="text-right font-mono text-accent">{match.similarity}%</span>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-7 justify-self-center"
                  disabled={match.playable === false}
                  aria-label={
                    (activeTrackId === `collection-${match.id}` || activeRekordboxId === match.id) && playing
                      ? `Pause ${match.title}`
                      : `Play ${match.title}`
                  }
                  title={
                    (activeTrackId === `collection-${match.id}` || activeRekordboxId === match.id) && playing
                      ? "Pause"
                      : "Play"
                  }
                  onClick={() => onPlay(match)}
                >
                  {(activeTrackId === `collection-${match.id}` || activeRekordboxId === match.id) && playing
                    ? <Pause size={14} />
                    : <Play size={14} />}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-[10px]"
                  disabled={!anchorTrack || match.playable === false || addingTrackId !== null}
                  onClick={async () => {
                    if (!anchorTrack) return;
                    await onAdd(anchorTrack, match);
                    onOpenChange(false);
                  }}
                >
                  {addingTrackId === match.id ? <LoaderCircle className="animate-spin" /> : <Plus />}
                  Add
                </Button>
              </div>
            ))}
          </div>
        )}
        {!loading && !error && matches.length === 0 && searched && (
          <p className="py-4 text-center text-sm text-muted-foreground">No matching tracks found.</p>
        )}
      </DialogContent>
    </Dialog>
  );
}
