import { Play, Star, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fmtTime, type CollectionMatch, type Track } from "@/lib/crate-data";

interface Props {
  sourceTrack: Track;
  matches: CollectionMatch[];
  loading: boolean;
  error: string | null;
  onPlay: (match: CollectionMatch) => void;
  onCollapse: () => void;
}

export function CollectionLookupResults({
  sourceTrack,
  matches,
  loading,
  error,
  onPlay,
  onCollapse,
}: Props) {
  return (
    <section className="rounded-md border border-border bg-card/70 p-3" aria-label="Rekordbox lookup results">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-xs font-semibold">
            {sourceTrack.rekordbox_id ? "Rekordbox track" : "Similar Rekordbox tracks"}
          </h2>
          <p className="truncate text-[10px] text-muted-foreground">
            {sourceTrack.artist} — {sourceTrack.title}
          </p>
        </div>
        <Button size="icon" variant="ghost" className="size-7 shrink-0" onClick={onCollapse} aria-label="Collapse lookup results">
          <X size={14} />
        </Button>
      </div>

      {loading ? (
        <p className="py-4 text-center text-xs text-muted-foreground" role="status">Searching the collection…</p>
      ) : error ? (
        <p className="py-3 text-xs text-destructive" role="alert">{error}</p>
      ) : matches.length ? (
        <ul className="divide-y divide-border">
          {matches.map((match) => (
            <li key={match.id} className="flex items-center justify-between gap-3 py-2">
              <div className="min-w-0">
                <div className="truncate text-xs font-medium">{match.title}</div>
                <div className="truncate text-[10px] text-muted-foreground">
                  {match.artist}{match.album ? ` — ${match.album}` : ""}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px]">
                  <span className="flex gap-0.5" role="img" aria-label={`Rating: ${match.rating ?? 0} out of 5 stars`}>
                    {[1, 2, 3, 4, 5].map((star) => (
                      <Star key={star} size={10} className={star <= (match.rating ?? 0) ? "fill-gold text-gold" : "text-border"} />
                    ))}
                  </span>
                  <span className="font-mono text-muted-foreground">{(match.play_count ?? 0).toLocaleString()} plays</span>
                  <span className="font-mono text-muted-foreground">
                    {fmtTime(match.duration)}{match.bpm ? ` · ${match.bpm} BPM` : ""}{match.key ? ` · ${match.key}` : ""}
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="rounded bg-secondary px-2 py-1 font-mono text-[10px] text-accent">
                  {match.id === sourceTrack.rekordbox_id ? "Exact" : `${match.similarity}%`}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-[10px]"
                  disabled={match.playable === false}
                  onClick={() => onPlay(match)}
                  aria-label={`Play ${match.artist} — ${match.title} in deck`}
                  title={match.playable === false ? "Audio file is unavailable" : "Play in main deck"}
                >
                  <Play size={12} /> Play
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="py-4 text-center text-xs text-muted-foreground">
          {sourceTrack.rekordbox_id ? "No Rekordbox track found for this ID." : "No similar tracks found in the collection."}
        </p>
      )}
    </section>
  );
}
