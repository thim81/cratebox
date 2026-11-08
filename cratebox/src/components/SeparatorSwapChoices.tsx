import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PLAYLIST_SEPARATORS, type SeparatorType } from "@/lib/cratebox-api";
import type { Track } from "@/lib/crate-data";

interface Props {
  track: Track;
  onReplace: (type: SeparatorType) => void;
  onCollapse: () => void;
  disabled?: boolean;
}

export function SeparatorSwapChoices({ track, onReplace, onCollapse, disabled = false }: Props) {
  const current = PLAYLIST_SEPARATORS.find((separator) => separator.trackId === track.rekordbox_id);

  return (
    <section
      className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-card/70 p-3"
      aria-label="Replace playlist separator"
    >
      <div className="mr-auto min-w-0">
        <h2 className="text-xs font-semibold">Replace separator</h2>
        <p className="truncate text-[10px] text-muted-foreground">
          Current: {current?.label ?? track.title}
        </p>
      </div>
      {PLAYLIST_SEPARATORS.map((separator) => (
        <Button
          key={separator.type}
          size="sm"
          variant={current?.type === separator.type ? "secondary" : "outline"}
          className="h-7"
          disabled={disabled || current?.type === separator.type}
          onClick={() => onReplace(separator.type)}
          aria-label={`Replace with ${separator.label} separator`}
        >
          {separator.label}
        </Button>
      ))}
      <Button
        size="icon"
        variant="ghost"
        className="size-7"
        disabled={disabled}
        onClick={onCollapse}
        aria-label="Close separator choices"
      >
        <X size={14} />
      </Button>
    </section>
  );
}
