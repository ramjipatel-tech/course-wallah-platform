"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { 
  BookOpen, 
  PlayCircle, 
  Clock, 
  ArrowRight, 
  User, 
  Layers, 
  Sparkles, 
  FileText,
  CheckCircle2,
  Lock
} from "lucide-react";
import { api } from "@/lib/api";
import { StudentUser, BatchItem, StudentActivityItem } from "@/lib/types";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { BatchCardSkeleton } from "@/components/ui/Skeleton";

export default function StudentDashboardPage() {
  const router = useRouter();
  const [student, setStudent] = useState<StudentUser | null>(null);
  const [batches, setBatches] = useState<BatchItem[]>([]);
  const [activities, setActivities] = useState<StudentActivityItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const [studentData, batchesData, progressData] = await Promise.all([
          api.getStudentProfile(),
          api.getMyBatches(),
          api.getLearningProgress(),
        ]);
        setStudent(studentData);
        setBatches(batchesData || []);
        setActivities(progressData || []);
      } catch (err) {
        // Unauthenticated -> redirect to login
        router.push("/login?next=/student");
      } finally {
        setLoading(false);
      }
    }
    loadDashboard();
  }, [router]);

  if (loading) {
    return (
      <div className="space-y-8">
        <div className="h-44 cw-card-elevated cw-skeleton rounded-3xl" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <BatchCardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (!student) return null;

  return (
    <div className="space-y-12">
      <Breadcrumbs
        items={[
          { label: "Home", href: "/" },
          { label: "Student Dashboard" },
        ]}
      />

      {/* Dashboard Greeting Header */}
      <section className="relative overflow-hidden rounded-3xl cw-card-elevated p-8 sm:p-10 border border-cw-border">
        <div className="relative z-10 space-y-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-xs font-bold text-cw-primary">
            <Sparkles className="w-3.5 h-3.5 text-cw-primary" />
            <span>Active Student Portal</span>
          </div>

          <div className="space-y-1">
            <h1 className="text-2xl sm:text-4xl font-black text-white tracking-tight">
              Welcome back, <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-cyan-400">{student.name}</span>!
            </h1>
            <p className="text-xs sm:text-sm text-cw-muted">
              Resume your engineering studies, synchronized video lectures, and companion notes.
            </p>
          </div>
        </div>
      </section>

      {/* Continue Learning / Recent Activity */}
      {activities.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
              <PlayCircle className="w-5 h-5 text-cyan-400" />
              <span>Continue Learning</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {activities.slice(0, 3).map((act, idx) => (
              <Link
                key={idx}
                href={`/lectures/${act.lecture_id}`}
                className="cw-card p-5 flex flex-col justify-between space-y-3 group hover:border-cyan-500/40"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[11px] font-bold text-cw-primary px-2 py-0.5 rounded bg-cw-elevated border border-cw-border">
                      Lecture #{act.lecture_index}
                    </span>
                    {act.completed ? (
                      <span className="text-[10px] text-emerald-400 font-bold flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" /> Completed
                      </span>
                    ) : (
                      <span className="text-[10px] text-cw-muted font-mono">
                        {Math.floor(act.playback_seconds / 60)}m watched
                      </span>
                    )}
                  </div>
                  <h3 className="font-bold text-sm text-white group-hover:text-cw-primary transition-colors line-clamp-2">
                    {act.lecture_title}
                  </h3>
                  <p className="text-xs text-cw-muted truncate">
                    {act.batch_name}
                  </p>
                </div>

                <div className="pt-2 border-t border-cw-border/60 flex items-center justify-between text-xs text-cw-muted font-semibold">
                  <span>Resume Stream</span>
                  <ArrowRight className="w-3.5 h-3.5 text-cw-primary group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Enrolled Batches */}
      <section className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <BookOpen className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight">
                My Enrolled Batches
              </h2>
              <p className="text-xs text-cw-muted">Access your curriculum syllabus, chapters, and materials</p>
            </div>
          </div>

          <span className="text-xs text-cw-muted font-semibold px-2.5 py-1 rounded-full bg-cw-surface border border-cw-border">
            {batches.length} Batch{batches.length === 1 ? "" : "es"}
          </span>
        </div>

        {batches.length === 0 ? (
          <EmptyState
            title="No Enrolled Batches Yet"
            description="Start by browsing our open course catalog to enroll in active academic series."
            actionText="Explore Course Catalog"
            actionHref="/#courses"
          />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {batches.map((batch) => (
              <Link
                key={batch.id}
                href={`/batches/${batch.slug}`}
                className="cw-card overflow-hidden group flex flex-col h-full transition-all duration-300 hover:border-blue-500/40 hover:-translate-y-1 hover:shadow-xl"
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
                      <Badge variant="success">Access Active</Badge>
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
                    <span>Open Curriculum</span>
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
