"use client";

import { useEffect, useState, useTransition, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Search, BookOpen, FileText, PlayCircle, Layers, ArrowRight, LayoutGrid } from "lucide-react";
import { api } from "@/lib/api";
import { AppItem, BatchItem, LectureItem } from "@/lib/types";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { LectureCard } from "@/components/lectures/LectureCard";
import { PDFViewer } from "@/components/media/PDFViewer";

function SearchContent() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") || "";
  const [query, setQuery] = useState(initialQuery);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<{
    apps: AppItem[];
    batches: BatchItem[];
    lectures: LectureItem[];
  }>({
    apps: [],
    batches: [],
    lectures: [],
  });

  // PDF modal state
  const [activePdfLectureId, setActivePdfLectureId] = useState<string | null>(null);
  const [activePdfTitle, setActivePdfTitle] = useState<string>("");

  useEffect(() => {
    if (initialQuery) {
      setQuery(initialQuery);
      performSearch(initialQuery);
    }
  }, [initialQuery]);

  const performSearch = async (searchTerm: string) => {
    if (!searchTerm.trim()) {
      setResults({ apps: [], batches: [], lectures: [] });
      return;
    }
    setLoading(true);
    try {
      const data = await api.search(searchTerm.trim());
      setResults({
        apps: data.apps || [],
        batches: data.batches || [],
        lectures: data.lectures || [],
      });
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    performSearch(query);
  };

  const totalResults =
    results.apps.length + results.batches.length + results.lectures.length;

  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { label: "Home", href: "/" },
          { label: "Search & Discovery" },
        ]}
      />

      {/* Search Header */}
      <div className="cw-card-elevated rounded-3xl p-6 sm:p-10 border border-cw-border space-y-6">
        <div className="space-y-2">
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
            Search Course Catalog
          </h1>
          <p className="text-xs sm:text-sm text-cw-muted">
            Find educational apps, course batches, lecture streams, and study notes instantly.
          </p>
        </div>

        <form onSubmit={handleFormSubmit} className="max-w-2xl">
          <div className="relative flex items-center">
            <Search className="w-5 h-5 absolute left-4 text-cw-muted pointer-events-none" />
            <input
              type="text"
              placeholder="Search by topic, chapter, batch name..."
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                if (e.target.value.length > 2) {
                  performSearch(e.target.value);
                }
              }}
              className="w-full pl-12 pr-28 py-3.5 bg-cw-surface border border-cw-border rounded-2xl text-sm sm:text-base text-white placeholder-cw-muted focus:outline-none focus:border-cw-primary focus:ring-2 focus:ring-cw-primary/25 transition-all"
            />
            <button
              type="submit"
              className="absolute right-2 px-5 py-2 bg-cw-primary hover:bg-cw-primary-hover text-white text-xs sm:text-sm font-bold rounded-xl transition-all"
            >
              Search
            </button>
          </div>
        </form>
      </div>

      {/* Results Container */}
      {loading ? (
        <div className="space-y-4 py-8">
          <div className="h-28 cw-card cw-skeleton" />
          <div className="h-28 cw-card cw-skeleton" />
        </div>
      ) : query && totalResults === 0 ? (
        <EmptyState
          title="No Matching Content Found"
          description={`We couldn't find any apps, batches, or lectures matching "${query}". Try searching with different keywords.`}
          actionText="Clear Search"
          actionHref="/search"
        />
      ) : (
        <div className="space-y-10">
          {/* Apps Matches */}
          {results.apps.length > 0 && (
            <section className="space-y-4">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <LayoutGrid className="w-4 h-4 text-cw-primary" />
                <span>Educational Apps ({results.apps.length})</span>
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {results.apps.map((app) => (
                  <Link
                    key={app.id}
                    href={`/apps/${app.slug}`}
                    className="cw-card p-5 flex items-center gap-4 group"
                  >
                    <div className="w-12 h-12 rounded-xl bg-cw-elevated border border-cw-border flex items-center justify-center text-cw-primary font-black text-lg overflow-hidden">
                      {app.icon_url ? (
                        <img src={app.icon_url} alt={app.name} className="w-full h-full object-cover" />
                      ) : (
                        app.name.charAt(0).toUpperCase()
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="font-bold text-sm text-white group-hover:text-cw-primary transition-colors truncate">
                        {app.name}
                      </h3>
                      <p className="text-xs text-cw-muted truncate">
                        {app.description || "Course Wallah learning stream"}
                      </p>
                    </div>
                    <ArrowRight className="w-4 h-4 text-cw-muted group-hover:text-cw-primary group-hover:translate-x-1 transition-all" />
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Batches Matches */}
          {results.batches.length > 0 && (
            <section className="space-y-4">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-indigo-400" />
                <span>Batches & Courses ({results.batches.length})</span>
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {results.batches.map((batch) => (
                  <Link
                    key={batch.id}
                    href={`/batches/${batch.slug}`}
                    className="cw-card p-5 flex flex-col justify-between space-y-3 group"
                  >
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2">
                        {batch.category && (
                          <Badge variant="primary">{batch.category}</Badge>
                        )}
                      </div>
                      <h3 className="font-bold text-sm text-white group-hover:text-cw-primary transition-colors line-clamp-2">
                        {batch.name}
                      </h3>
                    </div>
                    <div className="pt-2 border-t border-cw-border/60 flex items-center justify-between text-xs text-cw-muted">
                      <span>View Syllabus</span>
                      <ArrowRight className="w-3.5 h-3.5 text-cw-primary group-hover:translate-x-1 transition-all" />
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* Lectures Matches */}
          {results.lectures.length > 0 && (
            <section className="space-y-4">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <PlayCircle className="w-4 h-4 text-cyan-400" />
                <span>Lectures & Notes ({results.lectures.length})</span>
              </h2>
              <div className="space-y-3">
                {results.lectures.map((lec) => (
                  <LectureCard
                    key={lec.id}
                    lecture={lec}
                    onOpenPdf={(id, title) => {
                      setActivePdfLectureId(id);
                      setActivePdfTitle(title);
                    }}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* PDF Modal if invoked */}
      {activePdfLectureId && (
        <PDFViewer
          lectureId={activePdfLectureId}
          title={activePdfTitle}
          isOpen={true}
          onClose={() => setActivePdfLectureId(null)}
        />
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4 py-8">
          <div className="h-28 cw-card cw-skeleton" />
          <div className="h-28 cw-card cw-skeleton" />
        </div>
      }
    >
      <SearchContent />
    </Suspense>
  );
}
