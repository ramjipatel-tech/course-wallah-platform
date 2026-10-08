"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { LayoutGrid, ArrowRight, Sparkles } from "lucide-react";
import { AppItem } from "@/lib/types";
import { AppCardSkeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";

interface AppGridProps {
  apps: AppItem[];
  loading: boolean;
}

export function AppGrid({ apps, loading }: AppGridProps) {
  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.08,
      },
    },
  };

  const item = {
    hidden: { opacity: 0, y: 15 },
    show: { opacity: 1, y: 0, transition: { duration: 0.4 } },
  };

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-cw-primary">
            <LayoutGrid className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              Educational Apps
            </h2>
            <p className="text-xs text-cw-muted">Browse organized subject channels and faculty batches</p>
          </div>
        </div>

        <span className="text-xs text-cw-muted font-semibold px-2.5 py-1 rounded-full bg-cw-surface border border-cw-border">
          {apps.length} App{apps.length === 1 ? "" : "s"}
        </span>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <AppCardSkeleton key={i} />
          ))}
        </div>
      ) : apps.length === 0 ? (
        <EmptyState
          title="Courses are being prepared"
          description="Courses and study modules ingested via the Course Wallah Telegram bot will automatically appear here."
        />
      ) : (
        <motion.div 
          variants={container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
        >
          {apps.map((app) => (
            <motion.div key={app.id} variants={item}>
              <Link
                href={`/apps/${app.slug}`}
                className="cw-card p-6 flex flex-col justify-between group h-full transition-all duration-300 hover:border-blue-500/40 hover:-translate-y-1 hover:shadow-xl hover:shadow-blue-500/5"
              >
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="w-12 h-12 rounded-xl bg-cw-elevated border border-cw-border flex items-center justify-center text-cw-primary font-black text-xl overflow-hidden group-hover:scale-105 group-hover:border-blue-500/40 transition-all duration-300">
                      {app.icon_url ? (
                        <img src={app.icon_url} alt={app.name} className="w-full h-full object-cover" />
                      ) : (
                        app.name.charAt(0).toUpperCase()
                      )}
                    </div>
                    <span className="text-[10px] font-mono font-bold text-emerald-400 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      ACTIVE
                    </span>
                  </div>

                  <div className="space-y-1">
                    <h3 className="font-bold text-base text-white group-hover:text-cw-primary transition-colors">
                      {app.name}
                    </h3>
                    <p className="text-xs text-cw-muted line-clamp-2 leading-relaxed">
                      {app.description || "Comprehensive engineering curriculum, recorded sessions, and PDF lecture notes."}
                    </p>
                  </div>
                </div>

                <div className="pt-4 mt-4 border-t border-cw-border/60 flex items-center justify-between text-xs text-cw-muted font-semibold">
                  <span>View Batches</span>
                  <ArrowRight className="w-4 h-4 text-cw-primary group-hover:translate-x-1.5 transition-transform" />
                </div>
              </Link>
            </motion.div>
          ))}
        </motion.div>
      )}
    </section>
  );
}
