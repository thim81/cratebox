import { ListMusic, RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fmtTime, type Playlist } from "@/lib/crate-data";

interface CrateSidebarProps {
  playlists: Playlist[];
  activeId: string;
  filter: string;
  apiError: string | null;
  refreshing: boolean;
  onFilterChange: (filter: string) => void;
  onRefresh: () => void;
  onSelectPlaylist: (playlistId: string) => void;
}

export function CrateSidebar({
  playlists,
  activeId,
  filter,
  apiError,
  refreshing,
  onFilterChange,
  onRefresh,
  onSelectPlaylist,
}: CrateSidebarProps) {
  const crates = playlists.filter((playlist) =>
    playlist.name.toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="p-2">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={filter}
            onChange={(event) => onFilterChange(event.target.value)}
            placeholder="Filter crates…"
            className="h-8 pl-7 text-xs"
          />
        </div>
      </div>
      <div className="flex items-center justify-between px-3 pb-1">
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          Crates
        </span>
        <Button
          size="icon"
          variant="ghost"
          className="size-7"
          onClick={onRefresh}
          disabled={refreshing}
          aria-label="Refresh playlists"
          title="Refresh playlists"
        >
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {apiError && (
          <div className="m-2 rounded border border-destructive/50 p-2 text-xs text-destructive">
            {apiError}
          </div>
        )}
        {crates.map((playlist) => (
          <button
            key={playlist.id}
            onClick={() => onSelectPlaylist(playlist.id)}
            className={`block w-full border-l-2 px-3 py-2 text-left transition-colors ${playlist.id === activeId ? "border-primary bg-sidebar-accent" : "border-transparent hover:bg-sidebar-accent/60"}`}
          >
            <div className="flex items-center gap-2 text-sm font-medium">
              <ListMusic
                size={14}
                className={playlist.id === activeId ? "text-primary" : "text-muted-foreground"}
              />
              <span className="truncate">{playlist.name}</span>
            </div>
            <div className="mt-0.5 flex gap-3 pl-6 font-mono text-[10px] text-muted-foreground">
              <span>{playlist.trackCount} trk</span>
              <span>{fmtTime(playlist.duration)}</span>
              <span>{playlist.created}</span>
            </div>
          </button>
        ))}
      </div>
      <div className="border-t border-sidebar-border p-2 font-mono text-[10px] leading-relaxed text-muted-foreground">
        ↑↓ browse · ⌘↑↓ load · ⇧↑↓ select · ⌘⌫ remove · ←→ seek 5s
      </div>
    </aside>
  );
}
