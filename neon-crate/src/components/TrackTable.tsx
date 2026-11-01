import { Fragment, useEffect, useRef, type ReactNode } from "react";
import {
  ChevronDown,
  ChevronUp,
  ListPlus,
  LoaderCircle,
  Plus,
  Search,
  Star,
  Trash2,
  Volume2,
} from "lucide-react";
import { CollectionLookupResults } from "@/components/CollectionLookupResults";
import { Button } from "@/components/ui/button";
import { fmtTime, type CollectionMatch, type Track } from "@/lib/crate-data";
import { PLAYLIST_SEPARATORS, type SeparatorType } from "@/lib/cratedeck-api";

export type SortKey = "number" | "title" | "artist" | "duration" | "rating" | "bpm" | "key";
export type SortState = { k: SortKey | null; dir: 1 | -1 };

interface TrackTableProps {
  tracks: Track[];
  trackNumbers: ReadonlyMap<string, number>;
  sort: SortState;
  selectedIndex: number;
  selectedIds: ReadonlySet<string>;
  loadedTrackId: string | null;
  playing: boolean;
  expandedLookupTrackId: string | null;
  lookupTrack: Track | null;
  lookupMatches: CollectionMatch[];
  lookupLoading: boolean;
  lookupError: string | null;
  onSort: (key: SortKey) => void;
  onSelect: (index: number) => void;
  onLoad: (track: Track) => void;
  onLookup: (track: Track) => void;
  onRemove: (track: Track) => void;
  onPlayCollectionMatch: (match: CollectionMatch) => void;
  onSwapCollectionMatch: (sourceTrack: Track, match: CollectionMatch) => void;
  onCollapseLookup: () => void;
  onInsertSeparator: (type: SeparatorType, track: Track) => void;
  separatorType: SeparatorType;
  separatorInserting: boolean;
  onAppendToPlaylist?: (track: Track) => void;
  appendDisabled?: boolean;
  appendPlaylistName?: string;
  appendingTrackId?: string | null;
  readOnly?: boolean;
}

export function TrackTable({
  tracks,
  trackNumbers,
  sort,
  selectedIndex,
  selectedIds,
  loadedTrackId,
  playing,
  expandedLookupTrackId,
  lookupTrack,
  lookupMatches,
  lookupLoading,
  lookupError,
  onSort,
  onSelect,
  onLoad,
  onLookup,
  onRemove,
  onPlayCollectionMatch,
  onSwapCollectionMatch,
  onCollapseLookup,
  onInsertSeparator,
  separatorType,
  separatorInserting,
  onAppendToPlaylist,
  appendDisabled = true,
  appendPlaylistName,
  appendingTrackId,
  readOnly = false,
}: TrackTableProps) {
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  useEffect(() => {
    rowRefs.current[selectedIndex]?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  const Th = ({
    k,
    children,
    className = "",
  }: {
    k?: SortKey;
    children: ReactNode;
    className?: string;
  }) => (
    <th
      onClick={k ? () => onSort(k) : undefined}
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
    <div className="flex-1 overflow-auto">
      <table className="w-full border-collapse text-xs">
        <thead className="text-[10px] text-muted-foreground">
          <tr>
            <Th className="w-10">{""}</Th>
            <Th k="number" className="w-8">
              #
            </Th>
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
          {tracks.map((track, index) => {
            const isLoaded = loadedTrackId === track.id;
            const isRangeSelected = selectedIds.has(track.id);
            const mp3Bitrate = /\bMP3\s+(\d+)\s*kbps/i.exec(track.quality)?.[1];
            const bitrate = Number(mp3Bitrate);
            const qualityClass = mp3Bitrate
              ? bitrate >= 320
                ? "border-accent text-accent"
                : bitrate === 128
                  ? "border-muted-foreground text-muted-foreground"
                  : bitrate > 128
                    ? "border-primary text-primary"
                    : "border-destructive text-destructive"
              : /FLAC|WAV|AIFF/.test(track.quality)
                ? "border-accent/40 bg-accent/15 text-accent"
                : "border-border bg-secondary text-muted-foreground";
            const qualityTitle = mp3Bitrate
              ? `${bitrate} kbps · ${bitrate >= 320 ? "Perfect" : bitrate === 128 ? "Minimal" : bitrate > 128 ? "OK" : "Warn"}`
              : track.quality;
            return (
              <Fragment key={track.id}>
                <tr
                  ref={(element) => {
                    rowRefs.current[index] = element;
                  }}
                  onClick={() => onSelect(index)}
                  onDoubleClick={readOnly ? undefined : () => onLoad(track)}
                  aria-selected={index === selectedIndex || isRangeSelected}
                  className={`group relative cursor-default border-b border-border/40 ${index === selectedIndex ? "bg-primary/20 outline outline-1 -outline-offset-1 outline-primary" : isRangeSelected ? "bg-primary/10" : index % 2 ? "bg-row-alt" : ""} ${isLoaded ? "text-accent" : ""} hover:bg-primary/10`}
                >
                  <td className="w-10 px-1 py-1 text-center">
                    {!readOnly && index > 0 && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className={`absolute bottom-0 left-1/2 z-20 size-5 -translate-x-1/2 translate-y-1/2 rounded-full border border-border bg-card p-0 text-muted-foreground opacity-0 shadow-sm transition-opacity hover:text-primary group-hover:opacity-100 focus-visible:opacity-100 ${separatorInserting ? "pointer-events-none" : ""}`}
                        disabled={separatorInserting}
                        onClick={(event) => {
                          event.stopPropagation();
                          onInsertSeparator(separatorType, track);
                        }}
                        aria-label={`Insert ${PLAYLIST_SEPARATORS.find((item) => item.type === separatorType)?.label ?? "Generic"} separator before ${track.title}`}
                        title={`Insert ${separatorType} separator before this track`}
                      >
                        <Plus size={12} />
                      </Button>
                    )}
                    {!readOnly && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className={`size-7 text-muted-foreground transition-opacity hover:bg-primary hover:text-primary-foreground ${index > 0 ? "group-hover:opacity-0 group-focus-within:opacity-0" : ""}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          onLookup(track);
                        }}
                        aria-expanded={expandedLookupTrackId === track.id}
                        aria-label={`${track.rekordbox_id ? "Open exact Rekordbox match for" : "Look up similar tracks for"} ${track.title}`}
                        title={
                          expandedLookupTrackId === track.id
                            ? "Collapse lookup results"
                            : "Search in Rekordbox collection"
                        }
                      >
                        <Search size={14} />
                      </Button>
                    )}
                  </td>
                  <td className="px-2 py-1 font-mono text-muted-foreground">
                    {trackNumbers.get(track.id)}
                  </td>
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
                  <td className="max-w-[16rem] truncate px-2 py-1 font-medium">{track.title}</td>
                  <td className="max-w-[12rem] truncate px-2 py-1">{track.artist}</td>
                  <td className="max-w-[12rem] truncate px-2 py-1 text-muted-foreground">
                    {track.album}
                  </td>
                  <td className="px-2 py-1 font-mono tabular-nums">{fmtTime(track.duration)}</td>
                  <td className="px-2 py-1">
                    <span className="flex">
                      {[1, 2, 3, 4, 5].map((rating) => (
                        <Star
                          key={rating}
                          size={11}
                          className={rating <= track.rating ? "fill-gold text-gold" : "text-border"}
                        />
                      ))}
                    </span>
                  </td>
                  <td className="px-2 py-1 font-mono tabular-nums text-accent">{track.bpm}</td>
                  <td className="px-2 py-1 font-mono font-semibold text-primary">{track.key}</td>
                  <td className="px-2 py-1">
                    <span
                      className={`whitespace-nowrap rounded border px-1.5 py-0.5 font-mono text-[10px] ${qualityClass}`}
                      title={qualityTitle}
                    >
                      {track.quality}
                    </span>
                  </td>
                  <td className="px-1 py-1 text-right">
                    {readOnly && onAppendToPlaylist ? (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7 text-muted-foreground hover:text-primary"
                        disabled={!track.rekordbox_id || appendDisabled}
                        onClick={(event) => {
                          event.stopPropagation();
                          onAppendToPlaylist(track);
                        }}
                        aria-label={`Insert ${track.title} into ${appendPlaylistName || "a CrateDeck playlist"}`}
                        title={
                          appendPlaylistName
                            ? `Insert into ${appendPlaylistName}`
                            : "Select a CrateDeck playlist first"
                        }
                      >
                        {appendingTrackId === track.id ? (
                          <LoaderCircle size={14} className="animate-spin" />
                        ) : (
                          <ListPlus size={14} />
                        )}
                      </Button>
                    ) : !readOnly ? (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7 text-muted-foreground hover:text-destructive"
                        onClick={(event) => {
                          event.stopPropagation();
                          onRemove(track);
                        }}
                        aria-label={`Remove ${track.title} from playlist`}
                        title="Remove from playlist"
                      >
                        <Trash2 size={14} />
                      </Button>
                    ) : null}
                  </td>
                </tr>
                {!readOnly && expandedLookupTrackId === track.id && lookupTrack && (
                  <tr>
                    <td colSpan={12} className="px-3 py-2">
                      <CollectionLookupResults
                        sourceTrack={lookupTrack}
                        matches={lookupMatches}
                        loading={lookupLoading}
                        error={lookupError}
                        activeTrackId={loadedTrackId}
                        playing={playing}
                        onPlay={onPlayCollectionMatch}
                        onSwap={onSwapCollectionMatch}
                        onCollapse={onCollapseLookup}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
          {tracks.length === 0 && (
            <tr>
              <td colSpan={12} className="p-8 text-center text-muted-foreground">
                No tracks
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
