import { useEffect, useRef, useState, type FormEvent } from "react";
import { LoaderCircle, Plus, Search, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { fmtTime, type CollectionMatch, type Track } from "@/lib/crate-data";
import { lookupCollection } from "@/lib/cratedeck-api";

interface Props {
  apiUrl: string;
  open: boolean;
  anchorTrack: Track | null;
  addingTrackId: string | null;
  onOpenChange: (open: boolean) => void;
  onAdd: (track: Track, match: CollectionMatch) => Promise<void>;
}

export function CollectionTrackSearchDialog({
  apiUrl,
  open,
  anchorTrack,
  addingTrackId,
  onOpenChange,
  onAdd,
}: Props) {
  const [artist, setArtist] = useState("");
  const [title, setTitle] = useState("");
  const [matches, setMatches] = useState<CollectionMatch[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const requestId = useRef(0);

  useEffect(() => {
    if (!open) return;
    setArtist("");
    setTitle("");
    setMatches([]);
    setError(null);
    setSearched(false);
  }, [open, anchorTrack]);

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
        {!loading && matches.length > 0 && (
          <div className="overflow-x-auto rounded border border-border">
            <div className="grid min-w-[920px] grid-cols-[minmax(10rem,1.4fr)_minmax(8rem,1fr)_minmax(8rem,1fr)_4.5rem_3.5rem_6rem_4rem_4rem_4.5rem_5rem] gap-2 bg-muted/50 px-3 py-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              <span>Title</span>
              <span>Artist</span>
              <span>Album</span>
              <span className="text-center">Stars</span>
              <span className="text-right">Plays</span>
              <span>Quality</span>
              <span className="text-right">Time</span>
              <span className="text-right">Lists</span>
              <span className="text-right">Match</span>
              <span />
            </div>
            {matches.map((match) => (
              <div
                key={match.id}
                className="grid min-w-[920px] grid-cols-[minmax(10rem,1.4fr)_minmax(8rem,1fr)_minmax(8rem,1fr)_4.5rem_3.5rem_6rem_4rem_4rem_4.5rem_5rem] items-center gap-2 border-t border-border px-3 py-2 text-xs"
              >
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
                <span className="text-right font-mono text-muted-foreground">{match.playlist_count ?? 0}</span>
                <span className="text-right font-mono text-accent">{match.similarity}%</span>
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
