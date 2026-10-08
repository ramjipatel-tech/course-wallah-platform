"use client";

import Link from "next/link";
import { PlayCircle, FileText, Clock, AlertCircle, Sparkles, CheckCircle2 } from "lucide-react";
import { LectureItem } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";

interface LectureCardProps {
  lecture: LectureItem;
  onOpenPdf?: (lectureId: string, pdfTitle: string) => void;
}

export function LectureCard({ lecture, onOpenPdf }: LectureCardProps) {
  const hasVideo = lecture.has_video;
  const hasPdf = lecture.has_pdf;
  const durationSec = lecture.video?.duration || 0;

  const formatDuration = (sec: number) => {
    if (!sec) return null;
    const mins = Math.floor(sec / 60);
    const remainingSecs = Math.floor(sec % 60);
    return `${mins}:${remainingSecs < 10 ? "0" : ""}${remainingSecs}`;
  };

  return (
    <div className="cw-card p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 group">
      <div className="flex items-start gap-3.5 flex-1 min-w-0">
        {/* Lecture Number Badge */}
        <div className="w-10 h-10 rounded-xl bg-cw-elevated border border-cw-border flex items-center justify-center font-mono font-black text-sm text-cw-primary group-hover:border-blue-500/40 group-hover:scale-105 transition-all flex-shrink-0">
          #{lecture.lecture_index}
        </div>

        {/* Title and Metadata */}
        <div className="space-y-1.5 flex-1 min-w-0">
          <h4 className="font-bold text-sm sm:text-base text-white group-hover:text-cw-primary transition-colors truncate">
            {lecture.title}
          </h4>

          <div className="flex items-center gap-3 text-xs text-cw-muted flex-wrap">
            {durationSec > 0 && (
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5 text-cw-muted" />
                <span>{formatDuration(durationSec)}</span>
              </span>
            )}

            {/* Media Badges */}
            {hasVideo && hasPdf && (
              <Badge variant="primary">Video + Notes</Badge>
            )}
            {hasVideo && !hasPdf && (
              <Badge variant="accent">Video</Badge>
            )}
            {!hasVideo && hasPdf && (
              <Badge variant="success">PDF Notes Available</Badge>
            )}
            {!hasVideo && !hasPdf && (
              <Badge variant="neutral">Media Unavailable</Badge>
            )}
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2 self-end sm:self-center flex-shrink-0">
        {/* State A & B: Watch Video button if video exists */}
        {hasVideo && (
          <Link
            href={`/lectures/${lecture.id}`}
            className="flex items-center gap-1.5 px-4 py-2 bg-cw-primary hover:bg-cw-primary-hover text-white text-xs sm:text-sm font-semibold rounded-xl shadow-lg shadow-blue-500/20 transition-all hover:scale-105"
          >
            <PlayCircle className="w-4 h-4" />
            <span>Watch Video</span>
          </Link>
        )}

        {/* State A & C: Notes button if PDF exists */}
        {hasPdf && (
          <button
            onClick={() => {
              if (onOpenPdf) {
                onOpenPdf(lecture.id, lecture.title);
              } else {
                window.location.href = `/lectures/${lecture.id}`;
              }
            }}
            className="flex items-center gap-1.5 px-4 py-2 bg-cw-elevated hover:bg-cw-surface-hover text-cw-text border border-cw-border hover:border-emerald-500/40 text-xs sm:text-sm font-semibold rounded-xl transition-all"
          >
            <FileText className="w-4 h-4 text-emerald-400" />
            <span>Open Notes</span>
          </button>
        )}

        {/* State D: Neither */}
        {!hasVideo && !hasPdf && (
          <div className="flex items-center gap-1.5 text-xs text-cw-muted px-3 py-1.5 bg-cw-elevated/60 border border-cw-border rounded-xl">
            <AlertCircle className="w-3.5 h-3.5 text-cw-muted" />
            <span>Unavailable</span>
          </div>
        )}
      </div>
    </div>
  );
}
