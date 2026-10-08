"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { BookOpen, ArrowRight, Sparkles, Layers } from "lucide-react";
import { BatchItem } from "@/lib/types";
import { BatchCardSkeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";

interface BatchSectionProps {
  batches: BatchItem[];
  loading: boolean;
}

export function BatchSection({ batches, loading }: BatchSectionProps) {
  if (!loading && batches.length === 0) {
    return null;
  }

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
    <section id="courses" className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
            <BookOpen className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              Featured Batches
            </h2>
            <p className="text-xs text-cw-muted">
              Explore syllabus, structured chapter modules, and lecture series
            </p>
          </div>
        </div>

        <span className="text-xs text-cw-muted font-semibold px-2.5 py-1 rounded-full bg-cw-surface border border-cw-border">
          {batches.length} Batch{batches.length === 1 ? "" : "es"}
        </span>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <BatchCardSkeleton key={i} />
          ))}
        </div>
      ) : (
        <motion.div 
          variants={container}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
        >
          {batches.map((batch) => (
            <motion.div key={batch.id} variants={item}>
              <Link
                href={`/batches/${batch.slug}`}
                className="cw-card overflow-hidden group flex flex-col h-full transition-all duration-300 hover:border-indigo-500/40 hover:-translate-y-1 hover:shadow-xl hover:shadow-indigo-500/5"
              >
                {batch.thumbnail_url ? (
                  <div className="w-full h-36 bg-cw-elevated relative overflow-hidden">
                    <img
                      src={batch.thumbnail_url}
                      alt={batch.name}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-cw-surface/90 via-transparent to-transparent pointer-events-none" />
                  </div>
                ) : (
                  <div className="w-full h-32 bg-gradient-to-tr from-cw-elevated to-cw-surface flex items-center justify-center text-cw-muted">
                    <BookOpen className="w-8 h-8 opacity-40 text-cw-primary" />
                  </div>
                )}

                <div className="p-5 flex-1 flex flex-col justify-between space-y-4">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      {batch.category && (
                        <Badge variant="primary">{batch.category}</Badge>
                      )}
                      {batch.academic_year && (
                        <Badge variant="neutral">{batch.academic_year}</Badge>
                      )}
                    </div>

                    <h3 className="font-bold text-base text-white group-hover:text-cw-primary transition-colors line-clamp-2">
                      {batch.name}
                    </h3>

                    <div className="text-xs text-cw-muted flex items-center gap-2">
                      {batch.branch && <span>{batch.branch}</span>}
                      {batch.branch && batch.semester && <span>&bull;</span>}
                      {batch.semester && <span>{batch.semester}</span>}
                    </div>
                  </div>

                  <div className="pt-3 border-t border-cw-border/60 flex items-center justify-between text-xs text-cw-muted font-semibold">
                    <span>Explore Curriculum</span>
                    <ArrowRight className="w-4 h-4 text-cw-primary group-hover:translate-x-1.5 transition-transform" />
                  </div>
                </div>
              </Link>
            </motion.div>
          ))}
        </motion.div>
      )}
    </section>
  );
}
