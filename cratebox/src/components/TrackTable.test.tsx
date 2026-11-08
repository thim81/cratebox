import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TrackTable } from "@/components/TrackTable";

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
  });

  it("keeps its row scroller constrained within the flex layout", () => {
    act(() =>
      root.render(
        <TrackTable
          tracks={[]}
          trackNumbers={new Map()}
          sort={{ k: null, dir: 1 }}
          selectedIndex={0}
          selectedIds={new Set()}
          loadedTrackId={null}
          playing={false}
          expandedLookupTrackId={null}
          expandedSeparatorTrackId={null}
          lookupTrack={null}
          lookupMatches={[]}
          lookupLoading={false}
          lookupError={null}
          addingCollectionTrackId={null}
          onSort={vi.fn()}
          onSelect={vi.fn()}
          onLoad={vi.fn()}
          onLookup={vi.fn()}
          onRemove={vi.fn()}
          onPlayCollectionMatch={vi.fn()}
          onSwapCollectionMatch={vi.fn()}
          onAddCollectionMatch={vi.fn()}
          onOpenRekordboxPlaylist={vi.fn()}
          onCollapseLookup={vi.fn()}
          onInsertSeparator={vi.fn()}
          onSelectSeparator={vi.fn()}
          onReplaceSeparator={vi.fn()}
          separatorType="generic"
          separatorInserting={false}
        />,
      ),
    );

    expect(container.querySelector(".flex.min-h-0.flex-1.overflow-auto")).not.toBeNull();
  });
});
