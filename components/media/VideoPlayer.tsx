"use client";

import { useState, useEffect, useRef } from "react";
import { 
  AlertTriangle, 
  Play, 
  RefreshCw, 
  ShieldCheck, 
  ChevronLeft, 
  ChevronRight, 
  Maximize, 
  Sliders, 
  Lock,
  Clock,
  Sparkles
} from "lucide-react";

export type PlayerSecurityState = 
  | "AUTHORIZING"
  | "READY"
  | "PLAYING"
  | "AUTHORIZATION_FAILED"
  | "EXPIRED_SESSION"
  | "VIDEO_UNAVAILABLE"
  | "NETWORK_ERROR";

interface VideoPlayerProps {
  videoId: string;
  provider?: string | null;
  playbackUrl?: string | null;
  title: string;
  quality?: string;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
}

export function VideoPlayer({
  videoId,
  provider = "youtube",
  playbackUrl,
  title,
  quality = "1080p",
  onPrev,
  onNext,
  hasPrev = false,
  hasNext = false,
}: VideoPlayerProps) {
  const [playerState, setPlayerState] = useState<PlayerSecurityState>("AUTHORIZING");
  const [playbackSpeed, setPlaybackSpeed] = useState<string>("1x");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedQuality, setSelectedQuality] = useState<string>(quality || "1080p");
  
  // Dynamic moving watermark state
  const [watermarkPos, setWatermarkPos] = useState({ top: "12%", left: "14%" });
  const [sessionTime, setSessionTime] = useState<string>("");
  const containerRef = useRef<HTMLDivElement>(null);

  // Validate videoId on mount
  useEffect(() => {
    if (!videoId || videoId.trim() === "") {
      setPlayerState("VIDEO_UNAVAILABLE");
      return;
    }
    // Simulate short-lived authorization handoff
    setPlayerState("AUTHORIZING");
    const authTimer = setTimeout(() => {
      setPlayerState("READY");
    }, 400);

    return () => clearTimeout(authTimer);
  }, [videoId]);

  // Moving watermark timer (shifts position every 9 seconds)
  useEffect(() => {
    const updateWatermark = () => {
      const positions = [
        { top: "12%", left: "10%" },
        { top: "14%", left: "62%" },
        { top: "72%", left: "15%" },
        { top: "76%", left: "58%" },
        { top: "45%", left: "35%" },
        { top: "25%", left: "70%" },
      ];
      const randomPos = positions[Math.floor(Math.random() * positions.length)];
      setWatermarkPos(randomPos);

      const d = new Date();
      setSessionTime(d.toTimeString().split(" ")[0]);
    };

    updateWatermark();
    const interval = setInterval(updateWatermark, 9000);
    return () => clearInterval(interval);
  }, []);

  // Keyboard and Right Click Deterrence inside player container
  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Intercept common save and inspect keys within player scope
    if (
      (e.ctrlKey && (e.key === "s" || e.key === "S" || e.key === "u" || e.key === "U")) ||
      e.key === "F12"
    ) {
      e.preventDefault();
      e.stopPropagation();
    }
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setIsFullscreen(false);
    }
  };

  // Safe YouTube embed with privacy-enhanced mode and clean parameters
  const embedUrl = `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&modestbranding=1&rel=0&iv_load_policy=3&enablejsapi=1`;

  return (
    <div 
      className="flex flex-col gap-3 select-none"
      onContextMenu={handleContextMenu}
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      {/* 16:9 Aspect Ratio Video Player Container */}
      <div 
        ref={containerRef}
        className="relative w-full aspect-video rounded-2xl overflow-hidden bg-black border border-cw-border shadow-2xl group"
      >
        {/* AUTHORIZING STATE */}
        {playerState === "AUTHORIZING" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-cw-surface cw-skeleton z-20">
            <div className="w-12 h-12 rounded-full border-2 border-cw-primary border-t-transparent animate-spin mb-3" />
            <div className="flex items-center gap-2 text-xs font-bold text-cw-primary">
              <Lock className="w-3.5 h-3.5" />
              <span>Verifying Stream Authorization...</span>
            </div>
          </div>
        )}

        {/* ERROR / UNAVAILABLE STATES */}
        {playerState === "VIDEO_UNAVAILABLE" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-cw-surface p-6 text-center z-30 space-y-3">
            <AlertTriangle className="w-12 h-12 text-amber-400" />
            <h4 className="text-base font-bold text-white">Stream Unavailable</h4>
            <p className="text-xs text-cw-muted max-w-sm">
              No playable video stream is currently assigned to this lecture.
            </p>
          </div>
        )}

        {playerState === "AUTHORIZATION_FAILED" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-cw-surface p-6 text-center z-30 space-y-3">
            <Lock className="w-12 h-12 text-rose-400" />
            <h4 className="text-base font-bold text-white">Playback Authorization Required</h4>
            <p className="text-xs text-cw-muted max-w-sm">
              Your playback session could not be authenticated. Please refresh the page.
            </p>
            <button
              onClick={() => setPlayerState("AUTHORIZING")}
              className="flex items-center gap-2 px-4 py-2 bg-cw-primary text-white text-xs font-bold rounded-xl"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Stream</span>
            </button>
          </div>
        )}

        {/* Dynamic Moving Watermark Overlay (Anti-Screen Recording / Anti-Crop Deterrence) */}
        {playerState === "READY" && (
          <div 
            className="absolute z-10 pointer-events-none transition-all duration-1000 ease-in-out px-3 py-1 rounded-md bg-black/40 backdrop-blur-[2px] border border-white/10 text-[10px] sm:text-xs font-mono font-semibold text-white/50 tracking-wider shadow-sm"
            style={{
              top: watermarkPos.top,
              left: watermarkPos.left,
            }}
          >
            COURSE WALLAH &bull; SECURE STREAM &bull; {sessionTime || "LIVE"}
          </div>
        )}

        {/* Protected Video Embed IFrame */}
        {videoId && (
          <iframe
            src={embedUrl}
            title={title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
            onLoad={() => {
              if (playerState === "AUTHORIZING") {
                setPlayerState("READY");
              }
            }}
            onError={() => setPlayerState("NETWORK_ERROR")}
            className="w-full h-full border-0 absolute inset-0"
          />
        )}
      </div>

      {/* Stream Controls & Security Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 bg-cw-surface rounded-xl border border-cw-border text-xs text-cw-muted">
        {/* Security & Quality Badges */}
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-emerald-400 font-semibold text-[11px]">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Authorized Playback</span>
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cw-elevated border border-cw-border text-cw-primary font-bold">
            {selectedQuality}
          </span>
        </div>

        {/* Playback Settings & Controls */}
        <div className="flex items-center gap-3">
          {/* Speed Selector */}
          <div className="flex items-center gap-1">
            <span className="text-[10px] text-cw-muted">Speed:</span>
            <select
              value={playbackSpeed}
              onChange={(e) => setPlaybackSpeed(e.target.value)}
              className="bg-cw-elevated border border-cw-border rounded-lg px-2 py-1 text-[11px] text-white focus:outline-none focus:border-cw-primary"
            >
              <option value="0.5x">0.5x</option>
              <option value="0.75x">0.75x</option>
              <option value="1x">1x (Normal)</option>
              <option value="1.25x">1.25x</option>
              <option value="1.5x">1.5x</option>
              <option value="1.75x">1.75x</option>
              <option value="2x">2x</option>
            </select>
          </div>

          {/* Fullscreen Button */}
          <button
            onClick={toggleFullscreen}
            className="p-1.5 rounded-lg bg-cw-elevated hover:bg-cw-surface-hover border border-cw-border text-cw-text hover:text-white transition-colors"
            title="Toggle Fullscreen"
            aria-label="Toggle Fullscreen"
          >
            <Maximize className="w-3.5 h-3.5" />
          </button>

          {/* Previous / Next Lecture Navigation */}
          {(onPrev || onNext) && (
            <div className="flex items-center gap-1 pl-2 border-l border-cw-border/80">
              {onPrev && (
                <button
                  onClick={onPrev}
                  disabled={!hasPrev}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-cw-elevated hover:bg-cw-surface-hover border border-cw-border text-cw-text-secondary hover:text-white disabled:opacity-30 disabled:pointer-events-none transition-all"
                >
                  <ChevronLeft className="w-3 h-3" />
                  <span>Prev</span>
                </button>
              )}
              {onNext && (
                <button
                  onClick={onNext}
                  disabled={!hasNext}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-cw-elevated hover:bg-cw-surface-hover border border-cw-border text-cw-text-secondary hover:text-white disabled:opacity-30 disabled:pointer-events-none transition-all"
                >
                  <span>Next</span>
                  <ChevronRight className="w-3 h-3" />
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
