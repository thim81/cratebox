import { useEffect, useRef, useState, type Ref, useImperativeHandle } from "react";
import { Pause, Play, SkipBack, SkipForward, Volume2, VolumeX } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { fmtTime, type Track } from "@/lib/crate-data";
import type WaveSurferType from "wavesurfer.js";

export interface DeckHandle {
  toggle: () => void;
}

interface Props {
  track: Track | null;
  playlistName: string;
  autoPlay: boolean;
  onPrev: () => void;
  onNext: () => void;
  onPlayingChange: (p: boolean) => void;
  ref?: Ref<DeckHandle>;
}

export function Deck({ track, playlistName, autoPlay, onPrev, onNext, onPlayingChange, ref }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const ws = useRef<WaveSurferType | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);
  const [vol, setVol] = useState(0.8);
  const [muted, setMuted] = useState(false);
  const [rate, setRate] = useState(1);
  const [cue, setCue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const nextRef = useRef(onNext);
  nextRef.current = onNext;
  const settings = useRef({ vol, muted, rate });
  settings.current = { vol, muted, rate };

  useImperativeHandle(ref, () => ({ toggle: () => ws.current?.playPause() }), []);

  useEffect(() => {
    if (!track || !box.current) return;
    let cancelled = false;
    let inst: WaveSurferType | null = null;
    setLoading(true); setErr(null); setTime(0); setDur(track.duration); setCue(0);
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
          Hover.create({ lineColor: c("--accent"), lineWidth: 1, labelBackground: c("--deck"), labelColor: c("--accent"), labelSize: "11px" }),
        ],
      });
      ws.current = inst;
      const s = settings.current;
      inst.setVolume(s.muted ? 0 : s.vol);
      inst.setPlaybackRate(s.rate, false);
      inst.on("ready", (d) => { setDur(d); setLoading(false); if (autoPlay) inst?.play().catch(() => {}); });
      inst.on("timeupdate", setTime);
      inst.on("play", () => { setPlaying(true); onPlayingChange(true); });
      inst.on("pause", () => { setPlaying(false); onPlayingChange(false); });
      inst.on("finish", () => nextRef.current());
      inst.on("error", (e) => { setErr(String(e?.message ?? e)); setLoading(false); });
    })();
    return () => { cancelled = true; inst?.destroy(); ws.current = null; setPlaying(false); onPlayingChange(false); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track?.id]);

  useEffect(() => { ws.current?.setVolume(muted ? 0 : vol); }, [vol, muted]);
  useEffect(() => { ws.current?.setPlaybackRate(rate, false); }, [rate]);

  const onCue = () => {
    const w = ws.current; if (!w) return;
    if (w.isPlaying()) { w.pause(); w.setTime(cue); } else { setCue(w.getCurrentTime()); }
  };

  const pitch = ((rate - 1) * 100).toFixed(1);
  const btn = "flex h-9 w-9 items-center justify-center rounded border border-border bg-secondary text-secondary-foreground hover:border-primary hover:text-primary transition-colors";

  return (
    <div className="border-b border-border bg-deck px-4 py-3">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <div className="min-w-0">
          <div className="truncate text-lg font-semibold text-foreground">{track?.title ?? "No track loaded"}</div>
          <div className="truncate text-sm text-muted-foreground">
            {track ? `${track.artist} — ${track.album}` : "Select a track and press Enter"}
          </div>
        </div>
        {track && (
          <div className="ml-auto flex flex-wrap items-center gap-2 font-mono text-xs">
            <span className="rounded bg-secondary px-2 py-1 text-accent">{(track.bpm * rate).toFixed(1)} BPM</span>
            <span className="rounded bg-secondary px-2 py-1 text-primary">{track.key}</span>
            <span className="rounded border border-primary/40 px-2 py-1 text-primary">{track.quality}</span>
            <span className="rounded bg-secondary px-2 py-1 text-muted-foreground">{playlistName}</span>
          </div>
        )}
      </div>

      <div className="relative rounded border border-border bg-background/60 px-1">
        <div ref={box} className="h-[72px] cursor-pointer" />
        {!track && <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">— waveform —</div>}
        {loading && track && <div className="pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-xs text-primary">LOADING WAVEFORM…</div>}
        {err && <div className="absolute inset-0 flex items-center justify-center text-xs text-destructive">Couldn't load audio: {err}</div>}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button onClick={onCue} disabled={!track} className="h-9 rounded border border-gold/60 bg-secondary px-3 font-mono text-xs font-bold text-gold hover:bg-gold/10 disabled:opacity-40">CUE</button>
        <button onClick={onPrev} className={btn} aria-label="Previous"><SkipBack size={16} /></button>
        <button onClick={() => ws.current?.playPause()} disabled={!track} aria-label={playing ? "Pause" : "Play"}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-[0_0_16px] shadow-primary/50 disabled:opacity-40">
          {playing ? <Pause size={18} /> : <Play size={18} className="ml-0.5" />}
        </button>
        <button onClick={onNext} className={btn} aria-label="Next"><SkipForward size={16} /></button>

        <div className="font-mono text-sm tabular-nums">
          <span className="text-primary">{fmtTime(time)}</span>
          <span className="mx-1 text-muted-foreground">/</span>
          <span className="text-destructive">-{fmtTime(dur - time)}</span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="font-mono text-[10px] text-muted-foreground">PITCH</span>
          <Slider className="w-32" min={0.92} max={1.08} step={0.001} value={[rate]} onValueChange={([v]) => setRate(v ?? 1)} />
          <button onClick={() => setRate(1)} className="w-14 font-mono text-xs text-accent tabular-nums" title="Reset">{Number(pitch) > 0 ? "+" : ""}{pitch}%</button>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setMuted((m) => !m)} className="text-muted-foreground hover:text-primary" aria-label="Mute">
            {muted || vol === 0 ? <VolumeX size={18} /> : <Volume2 size={18} />}
          </button>
          <Slider className="w-28" min={0} max={1} step={0.01} value={[muted ? 0 : vol]} onValueChange={([v]) => { setVol(v ?? 0); setMuted(false); }} />
        </div>
      </div>
    </div>
  );
}
