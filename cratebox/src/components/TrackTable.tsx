import { Fragment, useLayoutEffect, useRef, useState, type ReactNode } from "react";
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
import { PlaylistMembershipBadge } from "@/components/PlaylistMembershipBadge";
import { SeparatorSwapChoices } from "@/components/SeparatorSwapChoices";
import { Button } from "@/components/ui/button";
import { fmtTime, type CollectionMatch, type Track } from "@/lib/crate-data";
import { PLAYLIST_SEPARATORS, type SeparatorType } from "@/lib/cratebox-api";

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
  expandedSeparatorTrackId: string | null;
  lookupTrack: Track | null;
  lookupMatches: CollectionMatch[];
  lookupLoading: boolean;
  lookupError: string | null;
  addingCollectionTrackId: string | null;
  onSort: (key: SortKey) => void;
  onSelect: (index: number, modifiers: { shiftKey: boolean; toggle: boolean }) => void;
  onLoad: (track: Track) => void;
  onLookup: (track: Track) => void;
  onRemove: (track: Track) => void;
  onPlayCollectionMatch: (match: CollectionMatch) => void;
  onSwapCollectionMatch: (sourceTrack: Track, match: CollectionMatch) => void;
  onAddCollectionMatch: (sourceTrack: Track, match: CollectionMatch) => void;
  onOpenRekordboxPlaylist: (playlistId: string, trackId: string) => void;
  onCollapseLookup: () => void;
  onInsertSeparator: (type: SeparatorType, track: Track) => void;
  onSelectSeparator: (track: Track) => void;
  onReplaceSeparator: (track: Track, type: SeparatorType) => void;
  separatorType: SeparatorType;
  separatorInserting: boolean;
  separatorSwapping?: boolean;
  onAppendToPlaylist?: (track: Track) => void;
  appendDisabled?: boolean;
  appendDestinationSelected?: boolean;
  appendingTrackId?: string | null;
  showAppendAction?: boolean;
  readOnly?: boolean;
  separatorsEnabled?: boolean;
  reorderEnabled?: boolean;
  reordering?: boolean;
  onReorder?: (sourceTrackIds: string[], targetTrackId: string, before: boolean) => void;
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
  expandedSeparatorTrackId,
  lookupTrack,
  lookupMatches,
  lookupLoading,
  lookupError,
  addingCollectionTrackId,
  onSort,
  onSelect,
  onLoad,
  onLookup,
  onRemove,
  onPlayCollectionMatch,
  onSwapCollectionMatch,
  onAddCollectionMatch,
  onOpenRekordboxPlaylist,
  onCollapseLookup,
  onInsertSeparator,
  onSelectSeparator,
  onReplaceSeparator,
  separatorType,
  separatorInserting,
  separatorSwapping = false,
  onAppendToPlaylist,
  appendDisabled = true,
  appendDestinationSelected = false,
  appendingTrackId,
  showAppendAction = false,
  readOnly = false,
  separatorsEnabled = true,
  reorderEnabled = false,
  reordering = false,
  onReorder,
}: TrackTableProps) {
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);
  const scrollportRef = useRef<HTMLDivElement>(null);
  const draggedTrackIds = useRef<string[]>([]);
  const [dropTarget, setDropTarget] = useState<{ trackId: string; before: boolean } | null>(null);

  useLayoutEffect(() => {
    const row = rowRefs.current[selectedIndex];
    const scrollport = scrollportRef.current;
    if (!row || !scrollport) return;

    const scrollportBounds = scrollport.getBoundingClientRect();
    const stickyHeaderHeight = scrollport.querySelector("thead")?.getBoundingClientRect().height ?? 0;
    const rowBounds = row.getBoundingClientRect();
    const visibleTop = scrollportBounds.top + stickyHeaderHeight;
    if (rowBounds.top < visibleTop) {
      scrollport.scrollTop += rowBounds.top - visibleTop;
    } else if (rowBounds.bottom > scrollportBounds.bottom) {
      scrollport.scrollTop += rowBounds.bottom - scrollportBounds.bottom;
    }
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
    <div ref={scrollportRef} className="min-h-0 flex-1 overflow-auto">
      <table className="w-full border-collapse text-xs [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
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
            <Th k="rating">Stars</Th>
            <Th>Cues</Th>
            <Th>Lists</Th>
            <Th>Plays</Th>
            <Th k="bpm">BPM</Th>
            <Th k="key">Key</Th>
            <Th>Quality</Th>
            <Th className="w-16">{""}</Th>
          </tr>
        </thead>
        <tbody>
          {tracks.map((track, index) => {
            const isLoaded = loadedTrackId === track.id;
            const isSelected = selectedIds.has(track.id);
            const separator = PLAYLIST_SEPARATORS.find(
              (separator) => separator.trackId === track.rekordbox_id,
            );
            const isSeparator = Boolean(separator);
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
                  tabIndex={-1}
                  draggable={reorderEnabled && !reordering}
                  onDragStart={(event) => {
                    draggedTrackIds.current = selectedIds.has(track.id)
                      ? tracks.filter((item) => selectedIds.has(item.id)).map((item) => item.id)
                      : [track.id];
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", draggedTrackIds.current.join("\n"));
                  }}
                  onDragOver={(event) => {
                    const sourceTrackIds = draggedTrackIds.current;
                    if (!sourceTrackIds.length) return;
                    if (sourceTrackIds.includes(track.id)) {
                      setDropTarget(null);
                      return;
                    }
                    event.preventDefault();
                    const bounds = event.currentTarget.getBoundingClientRect();
                    const before = event.clientY < bounds.top + bounds.height / 2;
                    event.dataTransfer.dropEffect = "move";
                    setDropTarget({ trackId: track.id, before });
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    const sourceTrackIds = draggedTrackIds.current;
                    if (sourceTrackIds.length && !sourceTrackIds.includes(track.id) && onReorder) {
                      const bounds = event.currentTarget.getBoundingClientRect();
                      const before = event.clientY < bounds.top + bounds.height / 2;
                      onReorder(sourceTrackIds, track.id, before);
                    }
                    draggedTrackIds.current = [];
                    setDropTarget(null);
                  }}
                  onDragEnd={() => {
                    draggedTrackIds.current = [];
                    setDropTarget(null);
                  }}
                  onClick={(event) => {
                    // macOS Control-click may dispatch a contextmenu instead of click.
                    if (event.ctrlKey) return;
                    onSelect(index, {
                      shiftKey: event.shiftKey,
                      toggle: event.metaKey,
                    });
                  }}
                  onContextMenu={(event) => {
                    if (event.ctrlKey) {
                      event.preventDefault();
                      onSelect(index, {
                        shiftKey: event.shiftKey,
                        toggle: !event.shiftKey,
                      });
                    }
                  }}
                  onDoubleClick={() =>
                    readOnly || !isSeparator ? onLoad(track) : onSelectSeparator(track)
                  }
                  aria-selected={isSelected}
                  className={`group relative scroll-mt-8 cursor-default border-b border-border/40 ${reorderEnabled && !reordering ? "cursor-grab active:cursor-grabbing" : ""} ${dropTarget?.trackId === track.id ? (dropTarget.before ? "border-t-2 border-t-primary" : "border-b-2 border-b-primary") : ""} ${isSelected && index === selectedIndex ? "bg-primary/20 outline outline-1 -outline-offset-1 outline-primary" : isSelected ? "bg-primary/10" : index === selectedIndex ? "outline outline-1 -outline-offset-1 outline-primary/60" : index % 2 ? "bg-row-alt" : ""} ${isLoaded ? "text-accent" : ""} hover:bg-primary/10`}
                >
                  <td className="w-10 px-1 py-1 text-center">
                    {!readOnly && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7 text-muted-foreground transition-opacity hover:bg-primary hover:text-primary-foreground"
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelect(index, { shiftKey: false, toggle: false });
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
                  <td className="relative w-6 px-1 py-1">
                    {!readOnly && separatorsEnabled && index > 0 && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className={`absolute bottom-0 left-1/2 z-20 size-5 -translate-x-1/2 translate-y-1/2 rounded-full border border-border bg-card p-0 text-muted-foreground opacity-0 shadow-sm transition-opacity hover:text-primary group-hover:opacity-100 focus-visible:opacity-100 ${separatorInserting ? "pointer-events-none" : ""}`}
                        disabled={separatorInserting}
                        onClick={(event) => {
                          event.stopPropagation();
                          onInsertSeparator(separatorType, track);
                        }}
                        aria-label={`Insert ${PLAYLIST_SEPARATORS.find((item) => item.type === separatorType)?.label ?? "Generic"} separator after ${track.title}`}
                        title={`Insert ${separatorType} separator after this track`}
                      >
                        <Plus size={12} />
                      </Button>
                    )}
                    <span className="flex h-4 w-4 items-center justify-center">
                      {isLoaded &&
                        (playing ? (
                          <Volume2 size={12} className="animate-pulse text-accent" />
                        ) : (
                          <span className="text-accent">▸</span>
                        ))}
                    </span>
                  </td>
                  <td className="max-w-[16rem] px-2 py-1 font-medium">
                    {separator ? (
                      <span className="flex w-full min-w-0 items-center gap-1 text-muted-foreground">
                        <span className="w-3 shrink-0 border-t border-current" aria-hidden="true" />
                        <span className="shrink-0">{separator.label.toUpperCase()}</span>
                        <span
                          className="min-w-2 flex-1 border-t border-current"
                          aria-hidden="true"
                        />
                      </span>
                    ) : (
                      <span className="block truncate">{track.title}</span>
                    )}
                  </td>
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
                  <td className="px-2 py-1 text-right font-mono tabular-nums text-muted-foreground" title="Rekordbox cue points">
                    {track.cue_count ?? 0}
                  </td>
                  <td className="px-2 py-1 text-right">
                    <PlaylistMembershipBadge
                      count={track.playlist_count ?? 0}
                      playlists={track.playlists ?? []}
                      trackId={track.rekordbox_id ?? track.id}
                      onSelect={(playlistId) => onOpenRekordboxPlaylist(playlistId, track.rekordbox_id ?? track.id)}
                    />
                  </td>
                  <td className="px-2 py-1 text-right font-mono tabular-nums text-muted-foreground" title="Rekordbox play count">
                    {(track.play_count ?? 0).toLocaleString()}
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
                  <td className="w-16 px-1 py-1 text-right">
                    <span className="inline-flex items-center justify-end">
                      {(readOnly || showAppendAction) && onAppendToPlaylist ? (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="size-7 text-muted-foreground hover:text-white"
                          disabled={!track.rekordbox_id || appendDisabled}
                          onClick={(event) => {
                            event.stopPropagation();
                            onAppendToPlaylist(track);
                          }}
                          aria-label={`Add ${track.title} to a CrateBox playlist`}
                          title={
                            appendDisabled
                              ? "No CrateBox playlist available"
                              : appendDestinationSelected
                                ? "Add to selected CrateBox playlist"
                                : "Choose a CrateBox playlist"
                          }
                        >
                          {appendingTrackId === track.id ? (
                            <LoaderCircle size={14} className="animate-spin" />
                          ) : (
                            <ListPlus size={14} />
                          )}
                        </Button>
                      ) : null}
                      {!readOnly ? (
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
                    </span>
                  </td>
                </tr>
                {!readOnly && expandedLookupTrackId === track.id && lookupTrack && (
                  <tr>
                    <td colSpan={15} className="px-3 py-2">
                      <CollectionLookupResults
                        sourceTrack={lookupTrack}
                        matches={lookupMatches}
                        loading={lookupLoading}
                        error={lookupError}
                        activeTrackId={loadedTrackId}
                        activeRekordboxId={
                          loadedTrackId
                            ? (tracks.find((item) => item.id === loadedTrackId)?.rekordbox_id ??
                              null)
                            : null
                        }
                        playing={playing}
                        addingTrackId={addingCollectionTrackId}
                        onPlay={onPlayCollectionMatch}
                        onSwap={onSwapCollectionMatch}
                        onAdd={onAddCollectionMatch}
                        onOpenRekordboxPlaylist={onOpenRekordboxPlaylist}
                        onNavigatePlaylist={(direction) => {
                          const sourceIndex = tracks.findIndex(
                            (item) => item.id === lookupTrack.id,
                          );
                          const targetIndex = sourceIndex + (direction === "down" ? 1 : 0);
                          if (targetIndex < 0 || targetIndex >= tracks.length) return;
                          onSelect(targetIndex, { shiftKey: false, toggle: false });
                          rowRefs.current[targetIndex]?.focus();
                        }}
                        onCollapse={onCollapseLookup}
                      />
                    </td>
                  </tr>
                )}
                {!readOnly && separatorsEnabled && isSeparator && expandedSeparatorTrackId === track.id && (
                  <tr>
                    <td colSpan={15} className="px-3 py-2">
                      <SeparatorSwapChoices
                        track={track}
                        onReplace={(type) => onReplaceSeparator(track, type)}
                        onCollapse={() => onSelectSeparator(track)}
                        disabled={separatorSwapping}
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
