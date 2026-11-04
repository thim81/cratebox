import { useState, type KeyboardEvent } from "react";
import { ArrowLeftRight, LoaderCircle, Pause, Play, Plus, Star, Volume2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fmtTime, type CollectionMatch, type Track } from "@/lib/crate-data";

const resultGrid =
  "grid min-w-0 grid-cols-[1rem_minmax(8rem,1.4fr)_minmax(7rem,1fr)_minmax(7rem,1fr)_3.5rem_2.5rem_3rem_2.75rem_3rem_2rem_6rem_3rem_4.5rem_4rem_2rem] items-center gap-1.5";

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
  activeRekordboxId: string | null;
  playing: boolean;
  addingTrackId: string | null;
  onPlay: (match: CollectionMatch) => void;
  onSwap: (sourceTrack: Track, match: CollectionMatch) => void;
  onAdd: (sourceTrack: Track, match: CollectionMatch) => void;
  onNavigatePlaylist: (direction: "up" | "down") => void;
  onCollapse: () => void;
}

export function CollectionLookupResults({
  sourceTrack,
  matches,
  loading,
  error,
  activeTrackId,
  activeRekordboxId,
  playing,
  addingTrackId,
  onPlay,
  onSwap,
  onAdd,
  onNavigatePlaylist,
  onCollapse,
}: Props) {
  const [showMidMatches, setShowMidMatches] = useState(false);
  const [showLowMatches, setShowLowMatches] = useState(false);
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const sourceMatch = matches.find((match) => match.id === sourceTrack.rekordbox_id);
  const visibleMatches = matches.filter((match) => match.id !== sourceTrack.rekordbox_id);
  const highMatches = visibleMatches.filter((match) => match.similarity >= 70);
  const midMatches = visibleMatches.filter(
    (match) => match.similarity >= 50 && match.similarity < 70,
  );
  const lowMatches = visibleMatches.filter((match) => match.similarity < 50);
  const isActiveMatch = (match: CollectionMatch) =>
    activeTrackId === `collection-${match.id}` || activeRekordboxId === match.id;
  const shownMatches = [
    ...(sourceMatch ? [sourceMatch] : []),
    ...highMatches,
    ...(showMidMatches ? midMatches : []),
    ...(showLowMatches ? lowMatches : []),
  ];
  const navigateResults = (event: KeyboardEvent<HTMLElement>) => {
    if (!["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) return;
    const target = event.target as HTMLElement;
    const row = target.closest<HTMLElement>("[data-lookup-result]");
    if (!row) return;

    if (event.key === "Enter" || event.key === " ") {
      if (target.closest("button")) {
        event.stopPropagation();
        return;
      }
      const match = shownMatches.find((item) => item.id === row.dataset.lookupResult);
      if (match && match.playable !== false) {
        event.preventDefault();
        event.stopPropagation();
        onPlay(match);
      }
      return;
    }

    const rows = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>("[data-lookup-result]"),
    );
    const next = rows[rows.indexOf(row) + (event.key === "ArrowDown" ? 1 : -1)];
    if (next) {
      event.preventDefault();
      event.stopPropagation();
      next.focus();
    } else {
      event.preventDefault();
      event.stopPropagation();
      onNavigatePlaylist(event.key === "ArrowDown" ? "down" : "up");
    }
  };

  return (
    <section
      data-lookup-source-track={sourceTrack.id}
      className="rounded-md border border-border bg-card/70 p-3"
      aria-label="Rekordbox lookup results"
      onKeyDown={navigateResults}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-xs font-semibold">
            {sourceTrack.rekordbox_id ? "Rekordbox track" : "Similar Rekordbox tracks"}
          </h2>
          <p className="truncate text-[10px] text-muted-foreground">
            {sourceTrack.artist} — {sourceTrack.title}
          </p>
        </div>
        <Button
          size="icon"
          variant="ghost"
          className="size-7 shrink-0"
          onClick={onCollapse}
          aria-label="Collapse lookup results"
        >
          <X size={14} />
        </Button>
      </div>

      {loading ? (
        <p className="py-4 text-center text-xs text-muted-foreground" role="status">
          Searching the collection…
        </p>
      ) : error ? (
        <p className="py-3 text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : matches.length ? (
        <ul className="divide-y divide-border">
          <li
            className={`${resultGrid} pb-1 text-[8px] font-medium uppercase tracking-wide text-muted-foreground`}
          >
            <span />
            <span>Title</span>
            <span>Artist</span>
            <span>Album</span>
            <span className="text-center">Stars</span>
            <span className="text-right" title="Cue points">Cues</span>
            <span className="text-right">Plays</span>
            <span className="text-right">Time</span>
            <span className="text-right">BPM</span>
            <span className="text-right">Key</span>
            <span>Quality</span>
            <span className="text-right">Match</span>
            <span />
            <span />
            <span />
          </li>
          {shownMatches.map((match) => (
            <li
              key={match.id}
              data-lookup-result={match.id}
              data-selected={selectedMatchId === match.id || undefined}
              tabIndex={0}
              className={`${resultGrid} cursor-default py-2 outline-none focus-visible:ring-1 focus-visible:ring-primary ${match.id === sourceTrack.rekordbox_id ? "bg-primary/5" : ""} ${selectedMatchId === match.id ? "bg-primary/10 ring-1 ring-inset ring-primary/60" : ""} ${isActiveMatch(match) ? "text-accent" : ""}`}
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("button")) return;
                setSelectedMatchId(match.id);
              }}
              onDoubleClick={(event) => {
                if ((event.target as HTMLElement).closest("button") || match.playable === false)
                  return;
                onPlay(match);
              }}
              title={
                match.playable === false
                  ? "Audio file is unavailable"
                  : "Double-click to load and play"
              }
            >
              <span className="flex h-4 items-center justify-center">
                {isActiveMatch(match) &&
                  (playing ? (
                    <Volume2 size={12} className="animate-pulse text-accent" />
                  ) : (
                    <span className="text-accent">▸</span>
                  ))}
              </span>
              <span className="truncate text-xs font-medium" title={match.title}>
                {match.title}
              </span>
              <span className="truncate text-xs text-muted-foreground" title={match.artist}>
                {match.artist}
              </span>
              <span
                className={`truncate text-xs text-muted-foreground ${match.album ? "" : "text-center"}`}
                title={match.album}
              >
                {match.album || "—"}
              </span>
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
              <span className="text-right font-mono text-[10px] text-muted-foreground">
                {match.cue_count ?? 0}
              </span>
              <span className="text-right font-mono text-[10px] text-muted-foreground">
                {(match.play_count ?? 0).toLocaleString()}
              </span>
              <span className="text-right font-mono text-[10px] text-muted-foreground">
                {fmtTime(match.duration)}
              </span>
              <span className="text-right font-mono text-[10px] text-muted-foreground">
                {match.bpm || "—"}
              </span>
              <span className="text-right font-mono text-[10px] text-muted-foreground">
                {match.key || "—"}
              </span>
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
              <span className="text-right font-mono text-[10px] text-accent">
                {match.similarity}%
              </span>
              {match.id === sourceTrack.rekordbox_id ? (
                <span className="col-span-2 whitespace-nowrap rounded bg-primary/10 px-1 py-1 text-center text-[10px] text-primary">
                  In playlist
                </span>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-1 text-[10px]"
                  disabled={match.playable === false}
                  onClick={() => onSwap(sourceTrack, match)}
                  aria-label={`Replace ${sourceTrack.title} with ${match.title} in playlist`}
                  title={
                    match.playable === false
                      ? "Audio file is unavailable"
                      : "Replace source track in playlist"
                  }
                >
                  <ArrowLeftRight size={12} /> Swap
                </Button>
              )}
              {match.id !== sourceTrack.rekordbox_id && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-1 text-[10px]"
                  disabled={match.playable === false || addingTrackId !== null}
                  onClick={() => onAdd(sourceTrack, match)}
                  aria-label={`Add ${match.title} after ${sourceTrack.title} in playlist`}
                  title={
                    match.playable === false
                      ? "Audio file is unavailable"
                      : "Add after source track"
                  }
                >
                  {addingTrackId === match.id ? (
                    <LoaderCircle size={12} className="animate-spin" />
                  ) : (
                    <Plus size={12} />
                  )}
                  Add
                </Button>
              )}
              <Button
                size="icon"
                variant="outline"
                className="size-7"
                disabled={match.playable === false}
                onClick={() => onPlay(match)}
                aria-label={`${isActiveMatch(match) && playing ? "Pause" : "Play"} ${match.artist} — ${match.title} in deck`}
                title={
                  match.playable === false
                    ? "Audio file is unavailable"
                    : isActiveMatch(match) && playing
                      ? "Pause in main deck"
                      : "Play in main deck"
                }
              >
                {isActiveMatch(match) && playing ? <Pause size={12} /> : <Play size={12} />}
              </Button>
            </li>
          ))}
          {(midMatches.length > 0 || lowMatches.length > 0) && !showMidMatches && (
            <li className="py-1 text-center">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => setShowMidMatches(true)}
              >
                Show more ({midMatches.length + lowMatches.length} matches below 70%)
              </Button>
            </li>
          )}
          {showMidMatches && lowMatches.length > 0 && !showLowMatches && (
            <li className="py-1 text-center">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => setShowLowMatches(true)}
              >
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
