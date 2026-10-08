"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { AppItem, BatchItem } from "@/lib/types";
import { HeroSection } from "@/components/home/HeroSection";
import { AppGrid } from "@/components/home/AppGrid";
import { BatchSection } from "@/components/home/BatchSection";
import { 
  Sparkles, 
  Cpu, 
  Code2, 
  Binary, 
  GraduationCap, 
  Laptop, 
  CheckCircle2, 
  ShieldCheck, 
  Zap, 
  BookOpen,
  Bot
} from "lucide-react";

export default function HomePage() {
  const router = useRouter();
  const [apps, setApps] = useState<AppItem[]>([]);
  const [batches, setBatches] = useState<BatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    async function loadData() {
      try {
        const [appsData, batchesData] = await Promise.allSettled([
          api.getApps(),
          api.search(""),
        ]);

        if (appsData.status === "fulfilled") {
          setApps(appsData.value || []);
        }
        if (batchesData.status === "fulfilled") {
          setBatches(batchesData.value.batches || []);
        }
      } catch (err) {
        console.error("Failed to load catalog data:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  const filteredApps = apps.filter((a) =>
    a.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-16">
      {/* Dynamic Hero Section */}
      <HeroSection
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        onSearchSubmit={handleSearchSubmit}
        appCount={apps.length}
        batchCount={batches.length}
      />

      {/* Popular Learning Categories */}
      <section className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              Explore Learning Tracks
            </h2>
            <p className="text-xs text-cw-muted">
              Structured courses designed for students, engineers, and competitive aspirants
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          {[
            {
              title: "AI & Technology",
              icon: Cpu,
              desc: "Modern AI, Machine Learning & Cloud",
              color: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
            },
            {
              title: "Engineering",
              icon: Binary,
              desc: "Electronics, Core Branches & Systems",
              color: "text-blue-400 bg-blue-500/10 border-blue-500/20",
            },
            {
              title: "Programming",
              icon: Code2,
              desc: "Data Structures, Python & Fullstack",
              color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
            },
            {
              title: "Digital Skills",
              icon: Laptop,
              desc: "Practical Tools, Design & Web Tech",
              color: "text-amber-400 bg-amber-500/10 border-amber-500/20",
            },
            {
              title: "Exam Preparation",
              icon: GraduationCap,
              desc: "Targeted Lectures, Tests & Revision",
              color: "text-purple-400 bg-purple-500/10 border-purple-500/20",
            },
          ].map((cat, idx) => (
            <div
              key={idx}
              className="cw-card p-5 rounded-2xl flex flex-col justify-between hover:border-cw-primary/40 transition-all group"
            >
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${cat.color} mb-3 group-hover:scale-110 transition-transform`}>
                <cat.icon className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white group-hover:text-cw-primary transition-colors">
                  {cat.title}
                </h3>
                <p className="text-[11px] text-cw-muted mt-1 leading-relaxed">
                  {cat.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Educational Apps Catalog */}
      <AppGrid apps={filteredApps} loading={loading} />

      {/* Featured Curriculum Batches */}
      <BatchSection batches={batches} loading={loading} />

      {/* Why Course Wallah Section */}
      <section className="cw-card-elevated rounded-3xl p-8 sm:p-12 border border-cw-border space-y-8">
        <div className="max-w-2xl space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cw-primary/10 border border-cw-primary/20 text-xs font-bold text-cw-primary">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Why Students Choose Course Wallah</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
            Built for Serious Learning
          </h2>
          <p className="text-xs sm:text-sm text-cw-muted leading-relaxed">
            Every lecture, video chapter, and companion note is organized for seamless study with zero distractions.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="p-5 rounded-2xl bg-cw-surface border border-cw-border space-y-2">
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
              <Zap className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-white">Instant Resumption</h3>
            <p className="text-xs text-cw-muted leading-relaxed">
              Never lose your spot. Automatically tracks your learning position across all enrolled batches.
            </p>
          </div>

          <div className="p-5 rounded-2xl bg-cw-surface border border-cw-border space-y-2">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <BookOpen className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-white">Synchronized Notes</h3>
            <p className="text-xs text-cw-muted leading-relaxed">
              High-definition study notes paired with each lecture for rapid revision and deep understanding.
            </p>
          </div>

          <div className="p-5 rounded-2xl bg-cw-surface border border-cw-border space-y-2">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-white">Distraction Free</h3>
            <p className="text-xs text-cw-muted leading-relaxed">
              No ads, no clickbait recommendations. Just your structured curriculum and study materials.
            </p>
          </div>

          <div className="p-5 rounded-2xl bg-cw-surface border border-cw-border space-y-2">
            <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
              <Bot className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-bold text-white">Voice AI Assistant</h3>
            <p className="text-xs text-cw-muted leading-relaxed">
              Ask questions by voice or text to navigate batches, locate lectures, and query curriculum instantly.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
