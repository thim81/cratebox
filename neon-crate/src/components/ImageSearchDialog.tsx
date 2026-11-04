import { useEffect, useState, type FormEvent } from "react";
import { FolderOpen, LoaderCircle, Music2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { searchImages } from "@/lib/cratedeck-api";
import type { ImageResult } from "@/lib/crate-data";

interface Props {
  apiUrl: string;
  open: boolean;
  query: string;
  artist?: string;
  album?: string;
  track?: string;
  currentImageUrl?: string;
  embedIntoMp3?: boolean;
  onRevealTrack?: () => void;
  onOpenChange: (open: boolean) => void;
  onChoose: (image: ImageResult) => Promise<void>;
}

export function ImageSearchDialog({
  apiUrl,
  open,
  query: initialQuery,
  artist = "",
  album = "",
  track = "",
  currentImageUrl,
  embedIntoMp3 = false,
  onRevealTrack,
  onOpenChange,
  onChoose,
}: Props) {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<ImageResult[]>([]);
  const [preview, setPreview] = useState<ImageResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [searched, setSearched] = useState(false);
  const [coverArt, setCoverArt] = useState(true);
  const [spotify, setSpotify] = useState(false);
  const [soundcloud, setSoundcloud] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setQuery(initialQuery);
      setResults([]);
      setPreview(null);
      setError(null);
      setSearched(false);
      setCoverArt(true);
      setSpotify(false);
      setSoundcloud(false);
    }
  }, [open, initialQuery, artist, album, track]);

  async function search(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setSearched(true);
    setError(null);
    setPreview(null);
    try {
      setResults(
        await searchImages(apiUrl, query, { artist, album, track, coverArt, spotify, soundcloud }),
      );
    } catch (cause) {
      setResults([]);
      setError(cause instanceof Error ? cause.message : "Image search failed.");
    } finally {
      setLoading(false);
    }
  }

  async function choose(image: ImageResult) {
    setSaving(true);
    setError(null);
    try {
      await onChoose(image);
      onOpenChange(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save artwork.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-5xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Search Image</DialogTitle>
          <DialogDescription>
            Choose a result to use as artwork. Some providers return preview-size images rather than originals.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 md:grid-cols-[200px_minmax(0,1fr)]">
          <aside className="flex flex-col gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Current artwork
            </h3>
            <div className="relative flex aspect-square w-full items-center justify-center overflow-hidden rounded border border-border bg-secondary text-muted-foreground">
              <Music2 size={32} aria-hidden="true" />
              {currentImageUrl && (
                <img
                  src={currentImageUrl}
                  alt="Current artwork"
                  className="absolute inset-0 size-full object-contain"
                  onError={(event) => {
                    event.currentTarget.style.display = "none";
                  }}
                />
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {currentImageUrl
                ? "Compare this image with the search results."
                : "No artwork is currently set."}
            </p>
            {embedIntoMp3 && onRevealTrack && (
              <Button type="button" variant="outline" size="sm" onClick={onRevealTrack}>
                <FolderOpen size={14} /> Show MP3 in Finder
              </Button>
            )}
          </aside>
          <div className="flex min-w-0 flex-col gap-3">
            <form onSubmit={search} className="flex gap-2">
              <Input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search images…"
                maxLength={200}
              />
              <Button type="submit" disabled={loading || !query.trim()}>
                <Search size={14} /> Search
              </Button>
            </form>
            <div className="flex flex-wrap gap-2" aria-label="Search sources">
              {(
                [
                  ["Cover art", coverArt, setCoverArt],
                  ["Spotify", spotify, setSpotify],
                  ["SoundCloud", soundcloud, setSoundcloud],
                ] as const
              ).map(([label, enabled, setEnabled]) => (
                <button
                  key={label}
                  type="button"
                  aria-pressed={enabled}
                  onClick={() => setEnabled((value) => !value)}
                  className={`rounded border px-2.5 py-1 text-xs transition-colors ${enabled ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}
                >
                  {label} {enabled ? "on" : "off"}
                </button>
              ))}
            </div>
            {loading ? (
              <p
                role="status"
                className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground"
              >
                <LoaderCircle className="animate-spin" size={16} />
                Searching images…
              </p>
            ) : null}
            {error ? (
              <p
                role="alert"
                className="rounded border border-destructive/50 p-3 text-sm text-destructive"
              >
                {error}
              </p>
            ) : null}
            {!loading && results.length === 0 && !error ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                {searched
                  ? "No images found. Try another search."
                  : "Search for an artist, track, album, or crate."}
              </p>
            ) : null}
            {preview && (
              <div className="grid gap-3 rounded border border-border p-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                <div className="flex min-h-48 items-center justify-center bg-secondary">
                  <img
                    src={preview.image_url}
                    alt={preview.title || "Image preview"}
                    className="max-h-72 max-w-full object-contain"
                    onError={() =>
                      setError("This image host did not allow the preview. Try another result.")
                    }
                  />
                </div>
                <div className="flex flex-col justify-between gap-3">
                  <div className="max-w-48 space-y-1">
                    <p className="text-[10px] font-medium text-muted-foreground">
                      {preview.source}
                    </p>
                    <p className="text-xs">{preview.title || "Image preview"}</p>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Button onClick={() => void choose(preview)} disabled={saving}>
                      {saving ? "Saving…" : embedIntoMp3 ? "Embed into MP3" : "Use this image"}
                    </Button>
                    <a
                      href={preview.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-center text-xs text-muted-foreground underline"
                    >
                      {preview.source === "Google Images" ? "Open Google results" : "Open source"}
                    </a>
                  </div>
                </div>
              </div>
            )}
            {results.length > 0 && (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
                {results.map((image, index) => (
                  <button
                    key={`${image.image_url}-${index}`}
                    onClick={() => setPreview(image)}
                    className={`overflow-hidden rounded border text-left transition-colors hover:border-primary ${preview?.image_url === image.image_url ? "border-primary" : "border-border"}`}
                    aria-label={`Preview ${image.title || "image result"}`}
                  >
                    <img
                      src={image.thumbnail_url}
                      alt=""
                      loading="lazy"
                      className="aspect-square w-full bg-secondary object-cover"
                      onError={(event) => {
                        event.currentTarget.style.visibility = "hidden";
                      }}
                    />
                    <span className="block truncate px-2 pt-1 text-[9px] font-medium text-primary">
                      {image.source}
                    </span>
                    <span className="block truncate px-2 pb-1 text-[10px] text-muted-foreground">
                      {image.title || "Image result"}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
