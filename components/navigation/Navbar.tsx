"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Search, Layers, BookOpen, Menu, X, User, LogIn, LayoutDashboard, Sparkles } from "lucide-react";
import { CourseWallahLogo } from "@/components/brand/CourseWallahLogo";
import { MobileNav } from "./MobileNav";
import { api, getStudentToken } from "@/lib/api";
import { StudentUser } from "@/lib/types";

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [student, setStudent] = useState<StudentUser | null>(null);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    const token = getStudentToken();
    if (token) {
      api.getStudentProfile()
        .then((data) => setStudent(data))
        .catch(() => setStudent(null));
    } else {
      setStudent(null);
    }
  }, [pathname]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  return (
    <header
      className={`sticky top-0 z-50 w-full transition-all duration-300 ${
        scrolled
          ? "cw-glass-nav py-3 shadow-lg shadow-black/20"
          : "bg-cw-bg/60 backdrop-blur-md border-b border-cw-border/50 py-4"
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-4">
        {/* Brand Logo */}
        <CourseWallahLogo size="md" withTagline={true} />

        {/* Global Search Bar */}
        <form onSubmit={handleSearchSubmit} className="hidden md:flex items-center flex-1 max-w-md mx-6 relative">
          <Search className="w-4 h-4 absolute left-3.5 text-cw-muted pointer-events-none" />
          <input
            type="text"
            placeholder="Search batches, subjects, notes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-cw-surface/80 border border-cw-border rounded-xl text-sm text-cw-text placeholder-cw-muted focus:outline-none focus:border-cw-primary focus:ring-2 focus:ring-cw-primary/20 transition-all"
          />
        </form>

        {/* Navigation Links & Student Auth Gate */}
        <nav className="hidden md:flex items-center gap-3">
          <Link
            href="/"
            className={`flex items-center gap-2 px-3.5 py-2 text-sm font-semibold rounded-xl transition-all ${
              pathname === "/"
                ? "bg-cw-primary-soft text-cw-primary border border-blue-500/20"
                : "text-cw-text-secondary hover:text-white hover:bg-cw-surface"
            }`}
          >
            <Layers className="w-4 h-4" />
            <span>Home</span>
          </Link>

          <Link
            href="/#courses"
            className="flex items-center gap-2 px-3.5 py-2 text-sm font-semibold text-cw-text-secondary hover:text-white hover:bg-cw-surface rounded-xl transition-all"
          >
            <BookOpen className="w-4 h-4 text-cyan-400" />
            <span>Courses</span>
          </Link>

          {/* Student Authenticated vs Guest Actions */}
          {student ? (
            <div className="flex items-center gap-2 pl-2 border-l border-cw-border/80">
              <Link
                href="/student"
                className={`flex items-center gap-2 px-3.5 py-2 text-sm font-semibold rounded-xl transition-all ${
                  pathname === "/student"
                    ? "bg-cw-primary text-white shadow-md shadow-blue-500/20"
                    : "text-white bg-cw-surface hover:bg-cw-elevated border border-cw-border"
                }`}
              >
                <LayoutDashboard className="w-4 h-4 text-cyan-400" />
                <span>My Batches</span>
              </Link>

              <Link
                href="/profile"
                className="w-9 h-9 rounded-xl bg-gradient-to-tr from-blue-600 to-cyan-500 flex items-center justify-center text-white font-bold text-xs shadow-sm hover:scale-105 transition-transform"
                title={`${student.name} (${student.email})`}
              >
                {student.name.charAt(0).toUpperCase()}
              </Link>
            </div>
          ) : (
            <div className="flex items-center gap-2 pl-2 border-l border-cw-border/80">
              <Link
                href="/login"
                className="flex items-center gap-1.5 px-3.5 py-2 text-sm font-semibold text-cw-text hover:text-white hover:bg-cw-surface rounded-xl transition-all"
              >
                <LogIn className="w-4 h-4 text-cw-muted" />
                <span>Sign In</span>
              </Link>

              <Link
                href="/register"
                className="flex items-center gap-1.5 px-4 py-2 bg-cw-primary hover:bg-cw-primary-hover text-white text-sm font-bold rounded-xl shadow-md shadow-blue-500/20 transition-all hover:scale-105"
              >
                <span>Register</span>
              </Link>
            </div>
          )}
        </nav>

        {/* Mobile Hamburger Button */}
        <button
          onClick={() => setMobileMenuOpen(true)}
          className="md:hidden p-2 text-cw-muted hover:text-white hover:bg-cw-surface rounded-xl transition-colors"
          aria-label="Open mobile navigation"
        >
          <Menu className="w-6 h-6" />
        </button>
      </div>

      {/* Mobile Drawer */}
      <MobileNav
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        onSearchSubmit={handleSearchSubmit}
      />
    </header>
  );
}
