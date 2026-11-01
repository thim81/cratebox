export function artworkImageKey(track: { id: string; artwork_url?: string }): string {
  return `${track.id}:${track.artwork_url ?? ""}`;
}

export function shouldShowArtwork(
  track: { id: string; artwork_url?: string },
  failedImageKey: string | null,
): boolean {
  return Boolean(track.artwork_url && artworkImageKey(track) !== failedImageKey);
}
