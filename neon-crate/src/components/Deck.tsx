import { useEffect, useRef, useState, type Ref, useImperativeHandle } from "react";
import { Music2, Pause, Play, SkipBack, SkipForward, SlidersHorizontal, Star } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { fmtTime, type Track } from "@/lib/crate-data";
import type WaveSurferType from "wavesurfer.js";

export interface DeckHandle {
  toggle: () => void;
  seek: (seconds: number) => void;
}

interface Props {
  track: Track | null;
  playlistName: string;
  autoPlay: boolean;
  volume: number;
  muted: boolean;
  onPrev: () => void;
  onNext: () => void;
  onPlayingChange: (p: boolean) => void;
  onEditArtwork: (track: Track) => void;
  ref?: Ref<DeckHandle>;
}

export function Deck({
  track,
  playlistName,
  autoPlay,
  volume,
  muted,
  onPrev,
  onNext,
  onPlayingChange,
  onEditArtwork,
  ref,
}: Props) {
  const box = useRef<HTMLDivElement>(null);
  const ws = useRef<WaveSurferType | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);
  const [rate, setRate] = useState(1);
  const [pitchOpen, setPitchOpen] = useState(false);
  const [artworkFailedFor, setArtworkFailedFor] = useState<string | null>(null);
  const [cue, setCue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const nextRef = useRef(onNext);
  nextRef.current = onNext;
  const settings = useRef({ volume, muted, rate });
  settings.current = { volume, muted, rate };

  useImperativeHandle(
    ref,
    () => ({
      toggle: () => ws.current?.playPause(),
      seek: (seconds) => {
        const player = ws.current;
        if (player)
          player.setTime(
            Math.max(0, Math.min(player.getDuration(), player.getCurrentTime() + seconds)),
          );
      },
    }),
    [],
  );

  useEffect(() => {
    if (!track || !box.current) return;
    let cancelled = false;
    let inst: WaveSurferType | null = null;
    setLoading(true);
    setErr(null);
    setTime(0);
    setDur(track.duration);
    setCue(0);
    (async () => {
      const [{ default: WaveSurfer }, { default: Hover }] = await Promise.all([
        import("wavesurfer.js"),
        import("wavesurfer.js/dist/plugins/hover.esm.js"),
      ]);
      if (cancelled || !box.current) return;
      const css = getComputedStyle(document.documentElement);
      const c = (v: string) => css.getPropertyValue(v).trim();
      inst = WaveSurfer.create({
        container: box.current,
        url: track.url,
        height: 72,
        waveColor: c("--muted-foreground"),
        progressColor: c("--primary"),
        cursorColor: c("--accent"),
        cursorWidth: 2,
        barWidth: 2,
        barGap: 1,
        barRadius: 1,
        normalize: true,
        plugins: [
          Hover.create({
            lineColor: c("--accent"),
            lineWidth: 1,
            labelBackground: c("--deck"),
            labelColor: c("--accent"),
            labelSize: "11px",
          }),
        ],
      });
      ws.current = inst;
      const s = settings.current;
      inst.setVolume(s.muted ? 0 : s.volume);
      inst.setPlaybackRate(s.rate, false);
      inst.on("ready", (d) => {
        setDur(d);
        setLoading(false);
        if (autoPlay) inst?.play().catch(() => {});
      });
      inst.on("timeupdate", setTime);
      inst.on("play", () => {
        setPlaying(true);
        onPlayingChange(true);
      });
      inst.on("pause", () => {
        setPlaying(false);
        onPlayingChange(false);
      });
      inst.on("finish", () => nextRef.current());
      inst.on("error", (e) => {
        setErr(String(e?.message ?? e));
        setLoading(false);
      });
    })();
    return () => {
      cancelled = true;
      inst?.destroy();
      ws.current = null;
      setPlaying(false);
      onPlayingChange(false);
    };
    // oxlint-disable-next-line react/exhaustive-deps
  }, [track?.id]);

  useEffect(() => {
    ws.current?.setVolume(muted ? 0 : volume);
  }, [volume, muted]);
  useEffect(() => {
    ws.current?.setPlaybackRate(rate, false);
  }, [rate]);

  const onCue = () => {
    const w = ws.current;
    if (!w) return;
    if (w.isPlaying()) {
      w.pause();
      w.setTime(cue);
    } else {
      setCue(w.getCurrentTime());
    }
  };

  const pitch = ((rate - 1) * 100).toFixed(1);
  const btn =
    "flex h-9 w-9 items-center justify-center rounded border border-border bg-secondary text-secondary-foreground hover:border-primary hover:text-primary transition-colors";

  return (
    <div className="border-b border-border bg-deck px-4 py-3">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <div className="flex min-w-0 items-center gap-3">
          {track && (
            <button
              type="button"
              onClick={() => onEditArtwork(track)}
              aria-label={`Search artwork for ${track.title}`}
              title="Search Image"
              className="relative flex size-16 shrink-0 cursor-pointer items-center justify-center overflow-hidden border border-border bg-secondary text-muted-foreground hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Music2 size={24} aria-hidden="true" />
              {track.artwork_url && artworkFailedFor !== track.id ? (
                <img
                  key={`${track.id}:${track.artwork_url}`}
                  src={track.artwork_url}
                  alt={`Cover art for ${track.title}`}
                  className="absolute inset-0 size-full object-cover"
                  onError={(event) => {
                    if (track.fallback_artwork_url && !event.currentTarget.dataset.fallback) {
                      event.currentTarget.dataset.fallback = "true";
                      event.currentTarget.src = track.fallback_artwork_url;
                    } else {
                      event.currentTarget.style.display = "none";
                      setArtworkFailedFor(track.id);
                    }
                  }}
                />
              ) : null}
            </button>
          )}
          <div className="min-w-0">
            <div className="truncate text-lg font-semibold text-foreground">
              {track ? `${track.artist} - ${track.title}` : "No track loaded"}
            </div>
            <div className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
              <span className="truncate">
                {track ? track.album : "Select a track and press Enter"}
              </span>
              {track && (
                <span className="shrink-0 rounded bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
                  {playlistName}
                </span>
              )}
            </div>
          </div>
        </div>
        {track && (
          <div className="ml-auto flex flex-col items-end gap-1 font-mono text-xs">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <span className="rounded bg-secondary px-2 py-1 text-primary">{track.key}</span>
              <span className="rounded border border-primary/40 px-2 py-1 text-primary">
                {track.quality}
              </span>
            </div>
            <span
              className="flex gap-0.5"
              role="img"
              aria-label={`Rating: ${track.rating} out of 5 stars`}
            >
              {[1, 2, 3, 4, 5].map((star) => (
                <Star
                  key={star}
                  size={14}
                  className={star <= track.rating ? "fill-gold text-gold" : "text-muted-foreground"}
                />
              ))}
            </span>
          </div>
        )}
      </div>

      <div className="relative rounded border border-border bg-background/60 px-1">
        <div ref={box} className="h-[72px] cursor-pointer" />
        {!track && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
            — waveform —
          </div>
        )}
        {loading && track && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-xs text-primary">
            LOADING WAVEFORM…
          </div>
        )}
        {err && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-destructive">
            Couldn't load audio: {err}
          </div>
        )}
      </div>

      <div className="mt-3 grid grid-cols-1 items-center gap-3 md:grid-cols-[1fr_auto_1fr]">
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={onCue}
            disabled={!track}
            className="h-9 rounded border border-gold/60 bg-secondary px-3 font-mono text-xs font-bold text-gold hover:bg-gold/10 disabled:opacity-40"
          >
            CUE
          </button>
          <button onClick={onPrev} className={btn} aria-label="Previous">
            <SkipBack size={16} />
          </button>
          <button
            onClick={() => ws.current?.playPause()}
            disabled={!track}
            aria-label={playing ? "Pause" : "Play"}
            className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-[0_0_16px] shadow-primary/50 disabled:opacity-40"
          >
            {playing ? <Pause size={18} /> : <Play size={18} className="ml-0.5" />}
          </button>
          <button onClick={onNext} className={btn} aria-label="Next">
            <SkipForward size={16} />
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPitchOpen((open) => !open)}
              className={pitchOpen ? "text-primary" : "text-muted-foreground hover:text-primary"}
              aria-expanded={pitchOpen}
              aria-label={pitchOpen ? "Hide pitch slider" : "Show pitch slider"}
              title="Pitch"
            >
              <SlidersHorizontal size={16} />
            </button>
            {pitchOpen && (
              <>
                <Slider
                  className="w-32"
                  min={0.92}
                  max={1.08}
                  step={0.001}
                  value={[rate]}
                  onValueChange={([v]) => setRate(v ?? 1)}
                  aria-label="Pitch"
                />
                <button
                  onClick={() => setRate(1)}
                  className="w-14 font-mono text-xs text-accent tabular-nums"
                  title="Reset pitch"
                >
                  {Number(pitch) > 0 ? "+" : ""}
                  {pitch}%
                </button>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center justify-center gap-2 font-mono text-xs tabular-nums">
          <span className="rounded bg-destructive px-2 py-1 text-destructive-foreground">
            -{fmtTime(dur - time)}
          </span>
          <span className="rounded bg-primary px-2 py-1 text-primary-foreground">
            {fmtTime(time)}
          </span>
        </div>
        <div className="flex items-center justify-end">
          {track && (
            <span className="rounded bg-secondary px-2 py-1 font-mono text-xs text-accent">
              {(track.bpm * rate).toFixed(2)} BPM
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
