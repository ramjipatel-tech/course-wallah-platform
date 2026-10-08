"use client";

import { motion } from "framer-motion";
import { Search, Sparkles, CheckCircle2, ShieldCheck, Flame, Play, BookOpen, Layers, Zap } from "lucide-react";
import { CourseWallahLogo } from "@/components/brand/CourseWallahLogo";

interface HeroSectionProps {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  onSearchSubmit: (e: React.FormEvent) => void;
  appCount: number;
  batchCount: number;
}

export function HeroSection({
  searchQuery,
  setSearchQuery,
  onSearchSubmit,
  appCount,
  batchCount,
}: HeroSectionProps) {
  const containerVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.6,
        staggerChildren: 0.15,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 15 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.5 } },
  };

  return (
    <motion.section 
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      className="relative overflow-hidden rounded-3xl cw-card-elevated p-8 sm:p-12 lg:p-16 border border-cw-border/80 shadow-2xl"
    >
      {/* Animated Glowing Background Ambient Orbs */}
      <motion.div 
        animate={{ 
          scale: [1, 1.15, 1],
          opacity: [0.15, 0.25, 0.15],
          x: [0, 15, 0],
          y: [0, -10, 0]
        }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
        className="absolute top-0 right-0 -mt-24 -mr-24 w-[420px] h-[420px] rounded-full bg-gradient-to-br from-blue-600/30 to-cyan-500/20 blur-3xl pointer-events-none" 
      />
      
      <motion.div 
        animate={{ 
          scale: [1, 1.2, 1],
          opacity: [0.1, 0.2, 0.1],
          x: [0, -15, 0],
          y: [0, 15, 0]
        }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
        className="absolute bottom-0 left-0 -mb-24 -ml-24 w-[380px] h-[380px] rounded-full bg-gradient-to-tr from-indigo-600/25 to-blue-500/15 blur-3xl pointer-events-none" 
      />

      <div className="relative z-10 max-w-3xl space-y-8">
        {/* Animated Brand Pill */}
        <motion.div variants={itemVariants} className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/25 text-xs font-bold text-cw-primary backdrop-blur-sm shadow-inner">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
          </span>
          <Sparkles className="w-3.5 h-3.5 text-cw-primary" />
          <span>India&apos;s High-Speed Engineering Learning Portal</span>
        </motion.div>

        {/* Hero Title with Dynamic Gradient */}
        <motion.div variants={itemVariants} className="space-y-3">
          <h1 className="text-3xl sm:text-5xl lg:text-6xl font-black text-white tracking-tight leading-tight">
            Learn with{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-cyan-400 to-indigo-300 drop-shadow-sm">
              Course Wallah
            </span>
          </h1>
          <p className="text-sm sm:text-lg text-cw-muted leading-relaxed max-w-2xl font-normal">
            Stream high-definition lectures with moving dynamic watermarks, instant lecture chapter navigation, and encrypted PDF study notes.
          </p>
        </motion.div>

        {/* Hero Search Box with Micro-Interactions */}
        <motion.form variants={itemVariants} onSubmit={onSearchSubmit} className="max-w-xl">
          <div className="relative flex items-center group">
            <Search className="w-5 h-5 absolute left-4 text-cw-muted group-focus-within:text-cw-primary transition-colors pointer-events-none" />
            <input
              type="text"
              placeholder="Search batches, subjects, chapters or notes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-28 py-3.5 bg-cw-surface/90 border border-cw-border rounded-2xl text-sm sm:text-base text-white placeholder-cw-muted focus:outline-none focus:border-cw-primary focus:ring-2 focus:ring-cw-primary/25 shadow-xl transition-all"
            />
            <motion.button
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              type="submit"
              className="absolute right-2 px-5 py-2 bg-cw-primary hover:bg-cw-primary-hover text-white text-xs sm:text-sm font-bold rounded-xl shadow-md shadow-blue-500/20 transition-all"
            >
              Search
            </motion.button>
          </div>
        </motion.form>

        {/* Live Feature Highlights & Ambient Topic Tickers */}
        <motion.div variants={itemVariants} className="space-y-4 pt-2">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs sm:text-sm text-cw-text-secondary">
            <div className="flex items-center gap-2.5 p-2.5 rounded-xl bg-cw-surface/50 border border-cw-border/60 backdrop-blur-sm">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span className="font-medium">1080p HD Streaming</span>
            </div>
            <div className="flex items-center gap-2.5 p-2.5 rounded-xl bg-cw-surface/50 border border-cw-border/60 backdrop-blur-sm">
              <ShieldCheck className="w-4 h-4 text-cyan-400 flex-shrink-0" />
              <span className="font-medium">Encrypted Study Notes</span>
            </div>
            <div className="flex items-center gap-2.5 p-2.5 rounded-xl bg-cw-surface/50 border border-cw-border/60 backdrop-blur-sm col-span-2 sm:col-span-1">
              <Zap className="w-4 h-4 text-amber-400 flex-shrink-0" />
              <span className="font-medium">High-Speed Playback</span>
            </div>
          </div>

          {/* Ambient Educational Keywords Ticker */}
          <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-1 text-[11px] text-cw-muted">
            <span className="font-bold text-cw-primary uppercase tracking-wider text-[10px] flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> Popular:
            </span>
            {[
              "AI & ML",
              "Engineering",
              "Programming",
              "Data Structures",
              "Digital Electronics",
              "Cloud Computing",
              "Web Development",
              "Python",
              "Computer Science"
            ].map((topic, idx) => (
              <span
                key={idx}
                className="px-2.5 py-0.5 rounded-lg bg-cw-elevated border border-cw-border text-cw-text whitespace-nowrap hover:border-cw-primary/50 transition-colors"
              >
                {topic}
              </span>
            ))}
          </div>
        </motion.div>
      </div>
    </motion.section>
  );
}
