import { ArrowLeft, Folder, ListMusic, Package, RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fmtTime, type Playlist, type RekordboxPlaylist } from "@/lib/crate-data";

interface CrateSidebarProps {
  playlists: Playlist[];
  rekordboxPlaylists: RekordboxPlaylist[];
  activeId: string;
  activeRekordboxId: string;
  rekordboxFolderId: string | null;
  source: "crate" | "rekordbox";
  filter: string;
  apiError: string | null;
  rekordboxError: string | null;
  refreshing: boolean;
  rekordboxRefreshing: boolean;
  onFilterChange: (filter: string) => void;
  onSourceChange: (source: "crate" | "rekordbox") => void;
  onRefresh: () => void;
  onRefreshRekordbox: () => void;
  onSelectPlaylist: (playlistId: string) => void;
  onSelectRekordboxPlaylist: (playlistId: string) => void;
  onOpenRekordboxFolder: (folderId: string) => void;
  onGoUpRekordboxFolder: () => void;
}

export function CrateSidebar({
  playlists,
  rekordboxPlaylists,
  activeId,
  activeRekordboxId,
  rekordboxFolderId,
  source,
  filter,
  apiError,
  rekordboxError,
  refreshing,
  rekordboxRefreshing,
  onFilterChange,
  onSourceChange,
  onRefresh,
  onRefreshRekordbox,
  onSelectPlaylist,
  onSelectRekordboxPlaylist,
  onOpenRekordboxFolder,
  onGoUpRekordboxFolder,
}: CrateSidebarProps) {
  const crates = playlists.filter((playlist) =>
    playlist.name.toLowerCase().includes(filter.toLowerCase()),
  );
  const currentRekordboxFolder = rekordboxPlaylists.find(
    (playlist) => playlist.id === rekordboxFolderId,
  );
  const rekordboxEntries = rekordboxPlaylists
    .filter((playlist) => playlist.parent_id === rekordboxFolderId)
    .filter((playlist) => playlist.name.toLowerCase().includes(filter.toLowerCase()))
    .sort((left, right) => left.sequence - right.sequence);

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="grid grid-cols-2 gap-1 p-2 pb-1" role="tablist" aria-label="Playlist sources">
        <Button
          size="sm"
          variant={source === "crate" ? "secondary" : "ghost"}
          className="gap-1.5"
          role="tab"
          aria-selected={source === "crate"}
          onClick={() => onSourceChange("crate")}
        >
          <img src="/favicon.svg" alt="" aria-hidden="true" className="size-4" />
          CrateDeck
        </Button>
        <Button
          size="sm"
          variant={source === "rekordbox" ? "secondary" : "ghost"}
          className="gap-1.5"
          role="tab"
          aria-selected={source === "rekordbox"}
          onClick={() => onSourceChange("rekordbox")}
        >
          <img src="/rekordbox.ico" alt="" aria-hidden="true" className="size-4" />
          Rekordbox
        </Button>
      </div>
      <div className="p-2">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={filter}
            onChange={(event) => onFilterChange(event.target.value)}
            placeholder={source === "crate" ? "Filter crates…" : "Filter Rekordbox playlists…"}
            className="h-8 pl-7 text-xs"
          />
        </div>
      </div>
      <div className="flex items-center justify-between px-3 pb-1">
        <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {source === "crate" ? <Package size={12} /> : <ListMusic size={12} />}
          {source === "crate"
            ? "Crates"
            : `Rekordbox · ${currentRekordboxFolder?.name ?? "Level 0"} · Read only`}
        </span>
        {source === "rekordbox" && rekordboxFolderId && (
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            onClick={onGoUpRekordboxFolder}
            aria-label="Back to parent folder"
            title="Back to parent folder"
          >
            <ArrowLeft size={13} />
          </Button>
        )}
        <Button
          size="icon"
          variant="ghost"
          className="size-7"
          onClick={source === "crate" ? onRefresh : onRefreshRekordbox}
          disabled={source === "crate" ? refreshing : rekordboxRefreshing}
          aria-label={source === "crate" ? "Refresh playlists" : "Refresh Rekordbox playlists"}
          title={source === "crate" ? "Refresh playlists" : "Refresh Rekordbox playlists"}
        >
          <RefreshCw
            size={13}
            className={
              (source === "crate" ? refreshing : rekordboxRefreshing) ? "animate-spin" : ""
            }
          />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {source === "crate" && apiError && (
          <div className="m-2 rounded border border-destructive/50 p-2 text-xs text-destructive">
            {apiError}
          </div>
        )}
        {source === "crate" &&
          crates.map((playlist) => (
            <div
              key={playlist.id}
              className={`flex w-full items-center border-l-2 transition-colors ${playlist.id === activeId ? "border-primary bg-sidebar-accent" : "border-transparent hover:bg-sidebar-accent/60"}`}
            >
              <button
                onClick={() => onSelectPlaylist(playlist.id)}
                className="min-w-0 flex-1 px-3 py-2 text-left"
              >
                <div className="flex items-center gap-2 text-sm font-medium">
                  <span className="relative flex size-5 shrink-0 items-center justify-center">
                    <ListMusic
                      size={14}
                      className={
                        playlist.id === activeId ? "text-primary" : "text-muted-foreground"
                      }
                    />
                    {playlist.artwork_url && (
                      <img
                        src={playlist.artwork_url}
                        alt=""
                        className="absolute inset-0 size-5 rounded object-cover"
                        onError={(event) => {
                          event.currentTarget.style.display = "none";
                        }}
                      />
                    )}
                  </span>
                  <span className="truncate">{playlist.name}</span>
                </div>
                <div className="mt-0.5 flex gap-3 pl-6 font-mono text-[10px] text-muted-foreground">
                  <span>{playlist.trackCount} trk</span>
                  <span>{fmtTime(playlist.duration)}</span>
                  <span>{playlist.created}</span>
                </div>
              </button>
            </div>
          ))}
        {source === "rekordbox" && rekordboxError && (
          <div className="m-2 rounded border border-destructive/50 p-2 text-xs text-destructive">
            {rekordboxError}
          </div>
        )}
        {source === "rekordbox" &&
          rekordboxEntries.map((playlist, index) => (
            <button
              key={playlist.id}
              onClick={() =>
                playlist.is_folder
                  ? onOpenRekordboxFolder(playlist.id)
                  : onSelectRekordboxPlaylist(playlist.id)
              }
              className={`flex w-full items-center gap-2 border-l-2 px-3 py-2 text-left transition-colors ${playlist.id === activeRekordboxId ? "border-primary bg-sidebar-accent" : "border-transparent hover:bg-sidebar-accent/60"}`}
            >
              {playlist.is_folder ? (
                <Folder size={14} className="shrink-0 text-muted-foreground" />
              ) : (
                <ListMusic size={14} className="shrink-0 text-muted-foreground" />
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{playlist.name}</span>
                <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground">
                  {playlist.is_folder ? "Folder" : `${playlist.track_count} trk`}
                  {playlist.is_smart_playlist ? " · Smart" : ""}
                </span>
              </span>
              <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
                {index + 1}
              </span>
            </button>
          ))}
        {source === "rekordbox" && rekordboxRefreshing && rekordboxPlaylists.length === 0 && (
          <div className="p-3 text-xs text-muted-foreground">Loading Rekordbox playlists…</div>
        )}
        {source === "rekordbox" &&
          !rekordboxRefreshing &&
          !rekordboxError &&
          rekordboxPlaylists.length === 0 && (
            <div className="p-3 text-xs text-muted-foreground">
              No Rekordbox playlists loaded. Refresh to connect.
            </div>
          )}
      </div>
      <div className="border-t border-sidebar-border p-2 font-mono text-[10px] leading-relaxed text-muted-foreground">
        {source === "crate"
          ? "↑↓ browse · ⌘↑↓ load · ⇧↑↓ select · ⌘⌫ remove · ←→ seek 5s"
          : "Read only · Copy to CrateDeck to edit"}
      </div>
    </aside>
  );
}
