import { LucideIcon, Sparkles, BookOpen } from "lucide-react";
import Link from "next/link";
import { CourseWallahLogo } from "@/components/brand/CourseWallahLogo";

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: LucideIcon;
  actionText?: string;
  actionHref?: string;
}

export function EmptyState({
  title = "Courses are Being Prepared",
  description = "New batches and high-definition video lectures are currently being indexed and processed.",
  icon: Icon = BookOpen,
  actionText,
  actionHref,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center p-12 sm:p-16 text-center cw-card border-dashed border-cw-border/80 my-8 space-y-5">
      <div className="relative">
        <div className="w-20 h-20 rounded-2xl bg-gradient-to-tr from-blue-600/20 via-indigo-600/10 to-cyan-500/20 border border-blue-500/30 flex items-center justify-center text-cw-primary shadow-xl animate-float">
          <Icon className="w-10 h-10 text-cw-primary" />
        </div>
        <div className="absolute -top-1 -right-1 w-6 h-6 rounded-full bg-cw-accent/20 border border-cw-accent/40 flex items-center justify-center">
          <Sparkles className="w-3.5 h-3.5 text-cw-accent" />
        </div>
      </div>

      <div className="space-y-2 max-w-md">
        <h3 className="text-lg sm:text-xl font-bold text-white tracking-tight">{title}</h3>
        <p className="text-xs sm:text-sm text-cw-muted leading-relaxed">{description}</p>
      </div>

      {actionText && actionHref && (
        <Link
          href={actionHref}
          className="px-5 py-2.5 bg-cw-primary hover:bg-cw-primary-hover text-white text-xs sm:text-sm font-semibold rounded-xl shadow-lg shadow-blue-500/25 transition-all"
        >
          {actionText}
        </Link>
      )}
    </div>
  );
}
