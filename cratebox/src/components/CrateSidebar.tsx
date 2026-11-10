import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowLeft, Download, Folder, ListMusic, LoaderCircle, MoreHorizontal, Package, Pencil, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cratePlaylistDownloadUrl } from "@/lib/cratebox-api";
import { fmtTime, type Playlist, type RekordboxPlaylist } from "@/lib/crate-data";

interface CrateSidebarProps {
  apiUrl: string;
  lightMode: boolean;
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
  creatingPlaylist: boolean;
  onFilterChange: (filter: string) => void;
  onSourceChange: (source: "crate" | "rekordbox") => void;
  onRefresh: () => void;
  onRefreshRekordbox: () => void;
  onCreatePlaylist: (name: string) => Promise<boolean>;
  onRenamePlaylist: (playlist: Playlist, name: string) => Promise<boolean>;
  onSelectPlaylist: (playlistId: string) => void;
  onDeletePlaylist: (playlist: Playlist) => void;
  onSelectRekordboxPlaylist: (playlistId: string) => void;
  onOpenRekordboxFolder: (folderId: string) => void;
  onGoUpRekordboxFolder: () => void;
}

export function CrateSidebar({
  apiUrl,
  lightMode,
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
  creatingPlaylist,
  onFilterChange,
  onSourceChange,
  onRefresh,
  onRefreshRekordbox,
  onCreatePlaylist,
  onRenamePlaylist,
  onSelectPlaylist,
  onDeletePlaylist,
  onSelectRekordboxPlaylist,
  onOpenRekordboxFolder,
  onGoUpRekordboxFolder,
}: CrateSidebarProps) {
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newPlaylistName, setNewPlaylistName] = useState("");
  const [renamePlaylist, setRenamePlaylist] = useState<Playlist | null>(null);
  const [renameName, setRenameName] = useState("");
  const [renamingPlaylist, setRenamingPlaylist] = useState(false);
  const activeRekordboxPlaylistRef = useRef<HTMLButtonElement>(null);
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

  useEffect(() => {
    if (source === "rekordbox" && activeRekordboxId) {
      activeRekordboxPlaylistRef.current?.scrollIntoView({ block: "nearest" });
    }
  }, [activeRekordboxId, rekordboxFolderId, source]);

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      <div
        className="grid grid-cols-2 gap-1 border-b border-sidebar-border px-2 pt-2"
        role="tablist"
        aria-label="Playlist sources"
      >
        <Button
          size="sm"
          variant="ghost"
          className={`gap-1.5 rounded-none border-b-2 hover:text-sidebar-accent-foreground ${source === "crate" ? "border-primary bg-primary/15 text-primary hover:bg-primary/20" : "border-transparent bg-sidebar-accent hover:bg-sidebar-accent/80"}`}
          role="tab"
          aria-selected={source === "crate"}
          onClick={() => onSourceChange("crate")}
        >
          <img src="/favicon.svg" alt="" aria-hidden="true" className="size-4" />
          CrateBox
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className={`gap-1.5 rounded-none border-b-2 hover:text-sidebar-accent-foreground ${source === "rekordbox" ? "border-primary bg-primary/15 text-primary hover:bg-primary/20" : "border-transparent bg-sidebar-accent hover:bg-sidebar-accent/80"}`}
          role="tab"
          aria-selected={source === "rekordbox"}
          onClick={() => onSourceChange("rekordbox")}
        >
          <img
            src={lightMode ? "/rekordbox_light.png" : "/rekordbox_dark.png"}
            alt=""
            aria-hidden="true"
            className="size-4"
          />
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
        <div className="flex items-center gap-1">
          {source === "crate" && (
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              onClick={() => setCreateDialogOpen(true)}
              aria-label="Create playlist"
              title="Create playlist"
            >
              <Plus size={14} />
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
      </div>
      <div className="flex-1 overflow-y-auto">
        {apiError && (
          <div className="m-2 rounded border border-destructive/50 p-2 text-xs text-destructive">
            {apiError}
          </div>
        )}
        {source === "crate" &&
          crates.map((playlist) => (
            <div
              key={playlist.id}
              className={`group flex w-full items-center border-b border-l-2 transition-colors ${playlist.id === activeId ? "border-primary bg-primary/15" : "border-b-sidebar-border border-l-transparent hover:bg-sidebar-accent/60"}`}
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
                  <span className={`truncate ${playlist.id === activeId ? "text-primary" : ""}`}>{playlist.name}</span>
                </div>
                <div className="mt-0.5 flex gap-3 pl-6 font-mono text-[10px] text-muted-foreground">
                  <span>{playlist.trackCount} trk</span>
                  <span>{fmtTime(playlist.duration)}</span>
                  <span>{playlist.created}</span>
                </div>
              </button>
              <div className="shrink-0 pr-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                <details
                  className="group/menu relative"
                  onBlur={(event) => {
                    if (!event.currentTarget.contains(event.relatedTarget)) {
                      event.currentTarget.removeAttribute("open");
                    }
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      event.currentTarget.removeAttribute("open");
                      event.currentTarget.querySelector("summary")?.focus();
                    }
                  }}
                >
                  <summary
                    className="flex size-7 cursor-pointer list-none items-center justify-center rounded text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden"
                    aria-label={`Actions for ${playlist.name}`}
                    title="Playlist actions"
                  >
                    <MoreHorizontal size={16} />
                  </summary>
                  <div className="absolute right-0 top-full z-50 mt-1 min-w-40 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md">
                    <Button
                      asChild
                      variant="ghost"
                      className="h-8 w-full justify-start gap-2 px-2 text-xs"
                    >
                      <a
                        href={cratePlaylistDownloadUrl(apiUrl, playlist.id)}
                        aria-label={`Download ${playlist.name} M3U8`}
                        title="Download M3U8"
                      >
                        <Download size={14} />
                        Download M3U8
                      </a>
                    </Button>
                    <Button
                      variant="ghost"
                      className="h-8 w-full justify-start gap-2 px-2 text-xs"
                      onClick={(event) => {
                        event.currentTarget.closest("details")?.removeAttribute("open");
                        setRenameName(playlist.name);
                        setRenamePlaylist(playlist);
                      }}
                    >
                      <Pencil size={14} />
                      Rename playlist
                    </Button>
                    <Button
                      variant="ghost"
                      className="h-8 w-full justify-start gap-2 px-2 text-xs text-destructive hover:text-destructive"
                      aria-label={`Delete ${playlist.name}`}
                      onClick={(event) => {
                        event.currentTarget.closest("details")?.removeAttribute("open");
                        onDeletePlaylist(playlist);
                      }}
                    >
                      <Trash2 size={14} />
                      Delete playlist
                    </Button>
                  </div>
                </details>
              </div>
            </div>
          ))}
        {source === "rekordbox" && rekordboxError && (
          <div className="m-2 rounded border border-destructive/50 p-2 text-xs text-destructive">
            {rekordboxError}
          </div>
        )}
        {source === "rekordbox" &&
          rekordboxEntries.map((playlist) => (
            <button
              key={playlist.id}
              ref={playlist.id === activeRekordboxId ? activeRekordboxPlaylistRef : undefined}
              onClick={() =>
                playlist.is_folder
                  ? onOpenRekordboxFolder(playlist.id)
                  : onSelectRekordboxPlaylist(playlist.id)
              }
              className={`flex w-full items-center gap-2 border-b border-l-2 border-b-sidebar-border px-3 py-2 text-left transition-colors ${playlist.id === activeRekordboxId ? "border-l-primary bg-primary/15" : "border-l-transparent hover:bg-sidebar-accent/60"}`}
            >
              {playlist.is_folder ? (
                <Folder
                  size={14}
                  className={`shrink-0 ${playlist.id === activeRekordboxId ? "text-primary" : "text-muted-foreground"}`}
                />
              ) : (
                <ListMusic
                  size={14}
                  className={`shrink-0 ${playlist.id === activeRekordboxId ? "text-primary" : "text-muted-foreground"}`}
                />
              )}
              <span className="min-w-0 flex-1">
                <span
                  className={`block truncate text-sm font-medium ${playlist.id === activeRekordboxId ? "text-primary" : ""}`}
                >
                  {playlist.name}
                </span>
                <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground">
                  {playlist.is_folder ? "Folder" : `${playlist.track_count} trk`}
                  {playlist.is_smart_playlist ? " · Smart" : ""}
                </span>
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
          : "Read only · Copy to CrateBox to edit"}
      </div>
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New CrateBox playlist</DialogTitle>
            <DialogDescription>Create an empty playlist to add tracks to.</DialogDescription>
          </DialogHeader>
          <form
            className="flex gap-2"
            onSubmit={async (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              const name = newPlaylistName.trim();
              if (!name || creatingPlaylist) return;
              if (await onCreatePlaylist(name)) {
                setCreateDialogOpen(false);
                setNewPlaylistName("");
              }
            }}
          >
            <Input
              autoFocus
              value={newPlaylistName}
              onChange={(event) => setNewPlaylistName(event.target.value)}
              placeholder="Playlist name"
              aria-label="Playlist name"
              maxLength={200}
            />
            <Button type="submit" disabled={!newPlaylistName.trim() || creatingPlaylist}>
              {creatingPlaylist ? <LoaderCircle className="animate-spin" /> : <Plus />}
              Create
            </Button>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog
        open={renamePlaylist !== null}
        onOpenChange={(open) => {
          if (!open && !renamingPlaylist) setRenamePlaylist(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename CrateBox playlist</DialogTitle>
            <DialogDescription>
              The playlist and its CrateBox metadata will be renamed together.
            </DialogDescription>
          </DialogHeader>
          <form
            className="flex gap-2"
            onSubmit={async (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              if (!renamePlaylist || !renameName.trim() || renamingPlaylist) return;
              setRenamingPlaylist(true);
              try {
                if (await onRenamePlaylist(renamePlaylist, renameName.trim())) {
                  setRenamePlaylist(null);
                  setRenameName("");
                }
              } finally {
                setRenamingPlaylist(false);
              }
            }}
          >
            <Input
              autoFocus
              value={renameName}
              onChange={(event) => setRenameName(event.target.value)}
              placeholder="Playlist name"
              aria-label="New playlist name"
              maxLength={200}
            />
            <Button type="submit" disabled={!renameName.trim() || renamingPlaylist}>
              {renamingPlaylist ? <LoaderCircle className="animate-spin" /> : <Pencil />}
              Rename
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </aside>
  );
}
