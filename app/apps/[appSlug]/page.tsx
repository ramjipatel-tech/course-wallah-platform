"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { BookOpen, ArrowRight, LayoutGrid } from "lucide-react";
import { api } from "@/lib/api";
import { AppItem, BatchItem } from "@/lib/types";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { EmptyState } from "@/components/ui/EmptyState";
import { BatchCardSkeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";

export default function AppDetailPage() {
  const params = useParams();
  const appSlug = params.appSlug as string;

  const [app, setApp] = useState<AppItem | null>(null);
  const [batches, setBatches] = useState<BatchItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadAppAndBatches() {
      try {
        const [appData, batchesData] = await Promise.all([
          api.getAppBySlug(appSlug),
          api.getAppBatches(appSlug),
        ]);
        setApp(appData);
        setBatches(batchesData || []);
      } catch (err) {
        console.error("Failed to load app data:", err);
      } finally {
        setLoading(false);
      }
    }
    if (appSlug) {
      loadAppAndBatches();
    }
  }, [appSlug]);

  return (
    <div className="space-y-10">
      <Breadcrumbs
        items={[
          { label: "Educational Apps", href: "/" },
          { label: app ? app.name : appSlug },
        ]}
      />

      {loading ? (
        <div className="h-40 cw-card-elevated cw-skeleton rounded-3xl" />
      ) : app ? (
        <div className="cw-card-elevated rounded-3xl p-8 border border-cw-border flex flex-col sm:flex-row items-start sm:items-center gap-6">
          <div className="w-16 h-16 rounded-2xl bg-cw-elevated border border-cw-border flex items-center justify-center font-black text-2xl text-cw-primary overflow-hidden flex-shrink-0">
            {app.icon_url ? (
              <img src={app.icon_url} alt={app.name} className="w-full h-full object-cover" />
            ) : (
              app.name.charAt(0).toUpperCase()
            )}
          </div>
          <div className="space-y-1.5 flex-1">
            <div className="flex items-center gap-2">
              <Badge variant="primary">Educational Provider</Badge>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
              {app.name}
            </h1>
            <p className="text-xs sm:text-sm text-cw-muted max-w-2xl leading-relaxed">
              {app.description || "Course Wallah curated learning tracks, study series, and academic batches."}
            </p>
          </div>
        </div>
      ) : (
        <EmptyState
          title="App Category Not Found"
          description="The requested app category could not be located in the catalog."
          actionText="Back to Catalog"
          actionHref="/"
        />
      )}

      {/* Batches Section */}
      <section className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <BookOpen className="w-4 h-4" />
            </div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Available Batches
            </h2>
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
        ) : batches.length === 0 ? (
          <EmptyState
            title="Courses are being prepared"
            description="Batches and study modules for this educational app are being formatted. Please check back soon."
            actionText="Browse Other Apps"
            actionHref="/"
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {batches.map((batch) => (
              <Link
                key={batch.id}
                href={`/batches/${batch.slug}`}
                className="cw-card overflow-hidden group flex flex-col"
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

                <div className="p-5 flex-1 flex flex-col justify-between space-y-3">
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
                    <div className="text-xs text-cw-muted">
                      {batch.branch && <span>{batch.branch} &bull; </span>}
                      {batch.semester && <span>{batch.semester}</span>}
                    </div>
                  </div>

                  <div className="pt-3 border-t border-cw-border/60 flex items-center justify-between text-xs text-cw-muted font-semibold">
                    <span>View Curriculum</span>
                    <ArrowRight className="w-4 h-4 text-cw-primary group-hover:translate-x-1.5 transition-transform" />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
