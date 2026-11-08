import type { MouseEvent } from "react";

interface Props {
  count: number;
  playlists: { id: string; name: string }[];
  trackId: string;
  onSelect: (playlistId: string) => void;
}

export function PlaylistMembershipBadge({ count, playlists, trackId, onSelect }: Props) {
  const stopPropagation = (event: MouseEvent) => event.stopPropagation();

  return (
    <span className="group/memberships relative inline-flex justify-end">
      <button
        type="button"
        className="rounded border border-border bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground hover:border-primary hover:text-primary"
        aria-label={`${count} Rekordbox playlists`}
        title={playlists.length ? "Show Rekordbox playlists" : `${count} Rekordbox playlists`}
        onClick={stopPropagation}
      >
        {count}
      </button>
      {playlists.length > 0 && (
        <span className="absolute right-0 top-full z-50 hidden min-w-48 pt-1 group-hover/memberships:block group-focus-within/memberships:block">
          <span className="block max-h-56 overflow-y-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-lg">
            <span className="block px-2 py-1 text-left text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
              In Rekordbox playlists
            </span>
            {playlists.map((playlist) => (
              <a
                key={playlist.id}
                href={`/?${new URLSearchParams({
                  rekordbox_playlist_id: playlist.id,
                  rekordbox_track_id: trackId,
                }).toString()}`}
                className="block w-full truncate rounded px-2 py-1.5 text-left text-xs hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:outline-none"
                title={`Open ${playlist.name} at this track`}
                onClick={(event) => {
                  event.stopPropagation();
                  if (
                    event.button === 0 && !event.metaKey && !event.ctrlKey
                    && !event.shiftKey && !event.altKey
                  ) {
                    event.preventDefault();
                    onSelect(playlist.id);
                  }
                }}
              >
                {playlist.name}
              </a>
            ))}
          </span>
        </span>
      )}
    </span>
  );
}
