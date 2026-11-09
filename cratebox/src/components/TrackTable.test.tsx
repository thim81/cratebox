import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TrackTable } from "@/components/TrackTable";
import type { Track } from "@/lib/crate-data";

const makeTrack = (id: string): Track => ({
  id,
  title: "Track",
  artist: "Artist",
  album: "Album",
  duration: 180,
  rating: 0,
  bpm: 120,
  key: "8A",
  quality: "MP3 320kbps",
  url: `/audio/${id}`,
});

const makeProps = (tracks: Track[], selectedIndex: number, selectedIds: Set<string>) => ({
  tracks,
  trackNumbers: new Map<string, number>(),
  sort: { k: null, dir: 1 as const },
  selectedIndex,
  selectedIds,
  loadedTrackId: null,
  playing: false,
  expandedLookupTrackId: null,
  expandedSeparatorTrackId: null,
  lookupTrack: null,
  lookupMatches: [],
  lookupLoading: false,
  lookupError: null,
  addingCollectionTrackId: null,
  onSort: vi.fn(),
  onSelect: vi.fn(),
  onLoad: vi.fn(),
  onLookup: vi.fn(),
  onRemove: vi.fn(),
  onPlayCollectionMatch: vi.fn(),
  onSwapCollectionMatch: vi.fn(),
  onAddCollectionMatch: vi.fn(),
  onOpenRekordboxPlaylist: vi.fn(),
  onCollapseLookup: vi.fn(),
  onInsertSeparator: vi.fn(),
  onSelectSeparator: vi.fn(),
  onReplaceSeparator: vi.fn(),
  separatorType: "generic" as const,
  separatorInserting: false,
});

describe("TrackTable", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
  });

  it("keeps its row scroller constrained within the flex layout", () => {
    act(() =>
      root.render(<TrackTable {...makeProps([], 0, new Set())} />),
    );

    expect(container.querySelector(".flex.min-h-0.flex-1.overflow-auto")).not.toBeNull();
  });

  it("scrolls the selected row inside the tracklist viewport", () => {
    const bounds = (top: number, bottom: number) => ({
      x: 0,
      y: top,
      top,
      bottom,
      left: 0,
      right: 300,
      width: 300,
      height: bottom - top,
      toJSON: () => ({}),
    });
    let selectedRowBounds = bounds(110, 140);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function () {
      if (this.classList.contains("overflow-auto")) return bounds(0, 100);
      if (this.tagName === "THEAD") return bounds(0, 20);
      if (this.tagName === "TR" && this.getAttribute("aria-selected") === "true") {
        return selectedRowBounds;
      }
      return bounds(20, 50);
    });
    const tracks = [makeTrack("track-1"), makeTrack("track-2")];

    act(() => root.render(<TrackTable {...makeProps(tracks, 0, new Set(["track-1"]))} />));

    expect(container.querySelector(".overflow-auto")?.scrollTop).toBe(40);

    selectedRowBounds = bounds(-10, 20);
    act(() => root.render(<TrackTable {...makeProps(tracks, 1, new Set(["track-2"]))} />));

    expect(container.querySelector(".overflow-auto")?.scrollTop).toBe(10);
  });
});
