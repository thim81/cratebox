import { useState } from "react";
import { ArrowLeftRight, Play, Star, Volume2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fmtTime, type CollectionMatch, type Track } from "@/lib/crate-data";

const resultGrid = "grid min-w-0 grid-cols-[1rem_minmax(8rem,1.4fr)_minmax(7rem,1fr)_minmax(7rem,1fr)_3.5rem_3rem_2.75rem_3rem_2rem_6rem_3rem_4.5rem_4rem] items-center gap-1.5";

function qualityBadgeClass(quality: string) {
  const bitrate = Number(/\bMP3\s+(\d+)\s*kbps/i.exec(quality)?.[1]);
  if (bitrate) {
    return bitrate >= 320
      ? "border-accent text-accent"
      : bitrate === 128
        ? "border-muted-foreground text-muted-foreground"
        : bitrate > 128
          ? "border-primary text-primary"
          : "border-destructive text-destructive";
  }
  return /FLAC|WAV|AIFF/.test(quality)
    ? "border-accent/40 bg-accent/15 text-accent"
    : "border-border bg-secondary text-muted-foreground";
}

interface Props {
  sourceTrack: Track;
  matches: CollectionMatch[];
  loading: boolean;
  error: string | null;
  activeTrackId: string | null;
  playing: boolean;
  onPlay: (match: CollectionMatch) => void;
  onSwap: (sourceTrack: Track, match: CollectionMatch) => void;
  onCollapse: () => void;
}

export function CollectionLookupResults({
  sourceTrack,
  matches,
  loading,
  error,
  activeTrackId,
  playing,
  onPlay,
  onSwap,
  onCollapse,
}: Props) {
  const [showMidMatches, setShowMidMatches] = useState(false);
  const [showLowMatches, setShowLowMatches] = useState(false);
  const sourceMatch = matches.find((match) => match.id === sourceTrack.rekordbox_id);
  const visibleMatches = matches.filter((match) => match.id !== sourceTrack.rekordbox_id);
  const highMatches = visibleMatches.filter((match) => match.similarity >= 70);
  const midMatches = visibleMatches.filter((match) => match.similarity >= 50 && match.similarity < 70);
  const lowMatches = visibleMatches.filter((match) => match.similarity < 50);
  const shownMatches = [
    ...(sourceMatch ? [sourceMatch] : []),
    ...highMatches,
    ...(showMidMatches ? midMatches : []),
    ...(showLowMatches ? lowMatches : []),
  ];

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
          <li className={`${resultGrid} pb-1 text-[8px] font-medium uppercase tracking-wide text-muted-foreground`}>
            <span />
            <span>Title</span>
            <span>Artist</span>
            <span>Album</span>
            <span className="text-center">Stars</span>
            <span className="text-right">Plays</span>
            <span className="text-right">Time</span>
            <span className="text-right">BPM</span>
            <span className="text-right">Key</span>
            <span>Quality</span>
            <span className="text-right">Match</span>
            <span />
            <span />
          </li>
          {shownMatches.map((match) => (
            <li key={match.id} className={`${resultGrid} py-2 ${match.id === sourceTrack.rekordbox_id ? "bg-primary/5" : ""} ${activeTrackId === `collection-${match.id}` ? "text-accent" : ""}`}>
              <span className="flex h-4 items-center justify-center">
                {activeTrackId === `collection-${match.id}` && (playing
                  ? <Volume2 size={12} className="animate-pulse text-accent" />
                  : <span className="text-accent">▸</span>)}
              </span>
              <span className="truncate text-xs font-medium" title={match.title}>{match.title}</span>
              <span className="truncate text-xs text-muted-foreground" title={match.artist}>{match.artist}</span>
              <span className={`truncate text-xs text-muted-foreground ${match.album ? "" : "text-center"}`} title={match.album}>{match.album || "—"}</span>
              <span className="flex justify-center gap-0.5" role="img" aria-label={`Rating: ${match.rating ?? 0} out of 5 stars`}>
                  {[1, 2, 3, 4, 5].map((star) => (
                    <Star key={star} size={10} className={star <= (match.rating ?? 0) ? "fill-gold text-gold" : "text-border"} />
                  ))}
              </span>
              <span className="text-right font-mono text-[10px] text-muted-foreground">{(match.play_count ?? 0).toLocaleString()}</span>
              <span className="text-right font-mono text-[10px] text-muted-foreground">{fmtTime(match.duration)}</span>
              <span className="text-right font-mono text-[10px] text-muted-foreground">{match.bpm || "—"}</span>
              <span className="text-right font-mono text-[10px] text-muted-foreground">{match.key || "—"}</span>
              {match.quality ? (
                <span
                  className={`w-fit max-w-full truncate whitespace-nowrap rounded border px-1 py-px font-mono text-[9px] ${qualityBadgeClass(match.quality)}`}
                  title={match.quality}
                >
                  {match.quality}
                </span>
              ) : (
                <span>—</span>
              )}
              <span className="text-right font-mono text-[10px] text-accent">{match.similarity}%</span>
              {match.id === sourceTrack.rekordbox_id ? (
                <span className="whitespace-nowrap rounded bg-primary/10 px-1 py-1 text-center text-[10px] text-primary">In playlist</span>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-1 text-[10px]"
                  disabled={match.playable === false}
                  onClick={() => onSwap(sourceTrack, match)}
                  aria-label={`Replace ${sourceTrack.title} with ${match.title} in playlist`}
                  title={match.playable === false ? "Audio file is unavailable" : "Replace source track in playlist"}
                >
                  <ArrowLeftRight size={12} /> Swap
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 px-1 text-[10px]"
                disabled={match.playable === false}
                onClick={() => onPlay(match)}
                aria-label={`Play ${match.artist} — ${match.title} in deck`}
                title={match.playable === false ? "Audio file is unavailable" : "Play in main deck"}
              >
                <Play size={12} /> Play
              </Button>
            </li>
          ))}
          {(midMatches.length > 0 || lowMatches.length > 0) && !showMidMatches && (
            <li className="py-1 text-center">
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowMidMatches(true)}>
                Show more ({midMatches.length + lowMatches.length} matches below 70%)
              </Button>
            </li>
          )}
          {showMidMatches && lowMatches.length > 0 && !showLowMatches && (
            <li className="py-1 text-center">
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowLowMatches(true)}>
                Show more ({lowMatches.length} matches below 50%)
              </Button>
            </li>
          )}
        </ul>
      ) : (
        <p className="py-4 text-center text-xs text-muted-foreground">
          {sourceTrack.rekordbox_id
            ? "No Rekordbox track found for this ID."
            : "No similar tracks found in the collection."}
        </p>
      )}
    </section>
  );
}
