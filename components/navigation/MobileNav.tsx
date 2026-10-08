"use client";

import Link from "next/link";
import { X, Search, Layers, BookOpen, Compass, ShieldCheck } from "lucide-react";
import { CourseWallahLogo } from "@/components/brand/CourseWallahLogo";

interface MobileNavProps {
  isOpen: boolean;
  onClose: () => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  onSearchSubmit: (e: React.FormEvent) => void;
}

export function MobileNav({
  isOpen,
  onClose,
  searchQuery,
  setSearchQuery,
  onSearchSubmit,
}: MobileNavProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden animate-fade-in">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/80 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Drawer Panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-xs bg-cw-bg-alt border-l border-cw-border p-6 flex flex-col justify-between shadow-2xl z-10 animate-slide-left">
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <CourseWallahLogo size="sm" />
            <button
              onClick={onClose}
              className="p-2 text-cw-muted hover:text-white rounded-xl hover:bg-cw-surface transition-colors"
              aria-label="Close navigation"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Search Form */}
          <form
            onSubmit={(e) => {
              onSearchSubmit(e);
              onClose();
            }}
            className="relative"
          >
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-cw-muted pointer-events-none" />
            <input
              type="text"
              placeholder="Search curriculum..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-cw-surface border border-cw-border rounded-xl text-sm text-cw-text placeholder-cw-muted focus:outline-none focus:border-cw-primary"
            />
          </form>

          {/* Student Links */}
          <nav className="space-y-2">
            <Link
              href="/"
              onClick={onClose}
              className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold text-cw-text hover:bg-cw-surface transition-colors"
            >
              <Layers className="w-4 h-4 text-cw-primary" />
              <span>Catalog Home</span>
            </Link>

            <Link
              href="/#courses"
              onClick={onClose}
              className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold text-cw-text hover:bg-cw-surface transition-colors"
            >
              <BookOpen className="w-4 h-4 text-cyan-400" />
              <span>Course Batches</span>
            </Link>

            <Link
              href="/search"
              onClick={onClose}
              className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold text-cw-text hover:bg-cw-surface transition-colors"
            >
              <Compass className="w-4 h-4 text-indigo-400" />
              <span>Explore Lectures</span>
            </Link>
          </nav>
        </div>

        {/* Footer Info */}
        <div className="pt-6 border-t border-cw-border text-xs text-cw-muted space-y-2">
          <div className="flex items-center gap-2 text-emerald-400 font-medium">
            <ShieldCheck className="w-4 h-4" />
            <span>Encrypted Streams & Study Notes</span>
          </div>
          <p className="text-[11px] text-cw-muted/70">
            Course Wallah Student Learning Portal
          </p>
        </div>
      </div>
    </div>
  );
}
