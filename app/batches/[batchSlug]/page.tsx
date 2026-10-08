"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { 
  BookOpen, 
  Folder, 
  ChevronDown, 
  ChevronRight, 
  Layers, 
  Sparkles,
  Layers2,
  CheckCircle2,
  LogIn
} from "lucide-react";
import { api, getStudentToken } from "@/lib/api";
import { BatchItem, SubjectItem, FolderItem, LectureItem, StudentUser } from "@/lib/types";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { LectureCard } from "@/components/lectures/LectureCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { PDFViewer } from "@/components/media/PDFViewer";
import { Badge } from "@/components/ui/Badge";

export default function BatchExplorerPage() {
  const params = useParams();
  const router = useRouter();
  const batchSlug = params.batchSlug as string;

  const [batch, setBatch] = useState<BatchItem | null>(null);
  const [student, setStudent] = useState<StudentUser | null>(null);
  const [isEnrolled, setIsEnrolled] = useState(false);
  const [enrolling, setEnrolling] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({});

  // PDF modal state
  const [activePdfLectureId, setActivePdfLectureId] = useState<string | null>(null);
  const [activePdfTitle, setActivePdfTitle] = useState<string>("");

  useEffect(() => {
    async function loadBatch() {
      try {
        const [batchData, studentData] = await Promise.allSettled([
          api.getBatchHierarchy(batchSlug),
          api.getStudentProfile(),
        ]);

        if (batchData.status === "fulfilled") {
          const data = batchData.value;
          setBatch(data);
          if (data.subjects && data.subjects.length > 0) {
            setSelectedSubjectId(data.subjects[0].id);
            const initialExpanded: Record<string, boolean> = {};
            data.subjects[0].folders.forEach((f) => {
              initialExpanded[f.id] = true;
            });
            setExpandedFolders(initialExpanded);
          }
        }

        if (studentData.status === "fulfilled") {
          const s = studentData.value;
          setStudent(s);
          if (batchData.status === "fulfilled" && s.enrolled_batch_ids) {
            setIsEnrolled(s.enrolled_batch_ids.includes(batchData.value.id));
          }
        }
      } catch (err) {
        console.error("Failed to load batch hierarchy:", err);
      } finally {
        setLoading(false);
      }
    }
    if (batchSlug) {
      loadBatch();
    }
  }, [batchSlug]);

  const handleEnroll = async () => {
    if (!student) {
      router.push(`/login?next=/batches/${batchSlug}`);
      return;
    }
    if (!batch) return;
    setEnrolling(true);
    try {
      await api.enrollInBatch(batch.slug);
      setIsEnrolled(true);
    } catch (err) {
      console.error("Enrollment error:", err);
    } finally {
      setEnrolling(false);
    }
  };

  const toggleFolder = (folderId: string) => {
    setExpandedFolders((prev) => ({
      ...prev,
      [folderId]: !prev[folderId],
    }));
  };

  const handleOpenPdf = (lectureId: string, pdfTitle: string) => {
    setActivePdfLectureId(lectureId);
    setActivePdfTitle(pdfTitle);
  };

  const currentSubject = batch?.subjects?.find((s) => s.id === selectedSubjectId);

  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { label: batch?.app?.name || "Courses", href: batch?.app?.slug ? `/apps/${batch.app.slug}` : "/" },
          { label: batch ? batch.name : batchSlug },
        ]}
      />

      {loading ? (
        <div className="h-44 cw-card-elevated cw-skeleton rounded-3xl" />
      ) : batch ? (
        <div className="cw-card-elevated rounded-3xl p-6 sm:p-8 border border-cw-border flex flex-col md:flex-row gap-6 items-start">
          {batch.thumbnail_url && (
            <div className="w-full md:w-56 h-36 rounded-2xl overflow-hidden bg-cw-elevated border border-cw-border flex-shrink-0">
              <img src={batch.thumbnail_url} alt={batch.name} className="w-full h-full object-cover" />
            </div>
          )}
          <div className="space-y-3 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              {batch.category && (
                <Badge variant="primary">{batch.category}</Badge>
              )}
              {isEnrolled ? (
                <Badge variant="success">Enrolled</Badge>
              ) : (
                <Badge variant="accent">Open Enrollment</Badge>
              )}
            </div>

            <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
              {batch.name}
            </h1>

            <div className="flex items-center gap-4 text-xs text-cw-muted">
              {batch.branch && <span>Branch: {batch.branch}</span>}
              {batch.semester && <span>Semester: {batch.semester}</span>}
              <span>{batch.subjects?.length || 0} Subject{(batch.subjects?.length || 0) === 1 ? "" : "s"}</span>
            </div>
          </div>

          <div className="flex items-center gap-2 self-start md:self-center">
            {isEnrolled ? (
              <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-bold px-3 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
                <CheckCircle2 className="w-4 h-4" />
                <span>Full Access Active</span>
              </span>
            ) : student ? (
              <button
                onClick={handleEnroll}
                disabled={enrolling}
                className="px-4 py-2 bg-cw-primary hover:bg-cw-primary-hover text-white text-xs font-bold rounded-xl shadow-md transition-all"
              >
                {enrolling ? "Enrolling..." : "Enroll in Batch"}
              </button>
            ) : (
              <Link
                href={`/login?next=/batches/${batchSlug}`}
                className="flex items-center gap-1.5 px-4 py-2 bg-cw-primary hover:bg-cw-primary-hover text-white text-xs font-bold rounded-xl shadow-md transition-all"
              >
                <LogIn className="w-4 h-4" />
                <span>Sign In to Save Progress</span>
              </Link>
            )}
          </div>
        </div>
      ) : (
        <EmptyState
          title="Batch Not Found"
          description="The requested batch hierarchy could not be loaded."
          actionText="Back to Catalog"
          actionHref="/"
        />
      )}

      {/* Subject Tabs & Curriculum Explorer */}
      {batch && batch.subjects && batch.subjects.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8 items-start">
          {/* Subject Navigation Sidebar */}
          <div className="cw-card rounded-2xl p-3 border border-cw-border space-y-1 lg:sticky lg:top-24">
            <div className="px-3 py-2 text-xs font-bold text-cw-muted uppercase tracking-wider flex items-center justify-between">
              <span>Subjects</span>
              <Layers2 className="w-3.5 h-3.5 text-cw-primary" />
            </div>
            {batch.subjects.map((subj) => {
              const isSelected = subj.id === selectedSubjectId;
              const totalLectures = subj.folders.reduce((acc, f) => acc + f.lectures.length, 0);

              return (
                <button
                  key={subj.id}
                  onClick={() => {
                    setSelectedSubjectId(subj.id);
                    const exp: Record<string, boolean> = {};
                    subj.folders.forEach((f) => {
                      exp[f.id] = true;
                    });
                    setExpandedFolders(exp);
                  }}
                  className={`w-full text-left px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all flex items-center justify-between gap-2 ${
                    isSelected
                      ? "bg-cw-primary text-white shadow-md shadow-blue-500/25"
                      : "text-cw-text-secondary hover:text-white hover:bg-cw-surface"
                  }`}
                >
                  <span className="truncate">{subj.name}</span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-bold ${
                      isSelected ? "bg-white/20 text-white" : "bg-cw-elevated text-cw-muted"
                    }`}
                  >
                    {totalLectures}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Units & Lectures Explorer */}
          <div className="lg:col-span-3 space-y-6">
            {currentSubject ? (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-bold text-white">
                    {currentSubject.name} Curriculum
                  </h2>
                  <span className="text-xs text-cw-muted font-semibold">
                    {currentSubject.folders.length} Unit{currentSubject.folders.length === 1 ? "" : "s"}
                  </span>
                </div>

                {currentSubject.folders.length === 0 ? (
                  <EmptyState
                    title="No Units Ingested Yet"
                    description="This subject does not contain any chapters or lecture units yet."
                  />
                ) : (
                  <div className="space-y-4">
                    {currentSubject.folders.map((folder) => {
                      const isExpanded = expandedFolders[folder.id] ?? true;
                      return (
                        <div
                          key={folder.id}
                          className="cw-card rounded-2xl border border-cw-border overflow-hidden transition-all"
                        >
                          {/* Folder / Unit Header */}
                          <button
                            onClick={() => toggleFolder(folder.id)}
                            className="w-full px-5 py-4 bg-cw-elevated/40 hover:bg-cw-elevated/70 flex items-center justify-between gap-4 text-left transition-colors"
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-cw-primary flex-shrink-0">
                                <Folder className="w-4 h-4" />
                              </div>
                              <div className="min-w-0">
                                <h3 className="font-bold text-sm sm:text-base text-white truncate">
                                  {folder.name}
                                </h3>
                                <span className="text-xs text-cw-muted">
                                  {folder.lectures.length} Lecture{folder.lectures.length === 1 ? "" : "s"}
                                </span>
                              </div>
                            </div>

                            <div className="p-1 rounded-lg text-cw-muted hover:text-white">
                              {isExpanded ? (
                                <ChevronDown className="w-4 h-4" />
                              ) : (
                                <ChevronRight className="w-4 h-4" />
                              )}
                            </div>
                          </button>

                          {/* Lectures List */}
                          {isExpanded && (
                            <div className="p-4 space-y-3 bg-cw-bg/50 border-t border-cw-border/60">
                              {folder.lectures.length === 0 ? (
                                <p className="text-xs text-cw-muted italic py-2 text-center">
                                  No lectures in this chapter yet.
                                </p>
                              ) : (
                                folder.lectures.map((lec) => (
                                  <LectureCard
                                    key={lec.id}
                                    lecture={lec}
                                    onOpenPdf={handleOpenPdf}
                                  />
                                ))
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <EmptyState
                title="Select a Subject"
                description="Choose a subject from the left panel to browse chapters and lectures."
              />
            )}
          </div>
        </div>
      ) : (
        !loading && (
          <EmptyState
            title="Curriculum Tree Empty"
            description="No subjects or units have been indexed for this batch yet."
          />
        )
      )}

      {/* PDF Viewer Modal with Long-Lived Auto-Renewal */}
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
