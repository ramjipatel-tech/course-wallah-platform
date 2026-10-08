import Link from "next/link";
import { ShieldCheck, Heart, Sparkles, BookOpen, Layers, Mail, HelpCircle, FileText } from "lucide-react";
import { CourseWallahLogo } from "@/components/brand/CourseWallahLogo";

export function Footer() {
  return (
    <footer className="border-t border-cw-border bg-cw-bg-alt/80 mt-28">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-10">
          {/* Brand Col */}
          <div className="md:col-span-2 space-y-4">
            <CourseWallahLogo size="md" withTagline={true} />
            <p className="text-xs sm:text-sm text-cw-muted leading-relaxed max-w-md">
              India&apos;s high-speed engineering education platform providing interactive video lecture streams, synchronized chapter modules, and verified handwritten notes.
            </p>
            <div className="flex items-center gap-2 text-xs text-emerald-400 font-medium">
              <ShieldCheck className="w-4 h-4" />
              <span>Verified Academic Curriculum & Encrypted Notes Access</span>
            </div>
          </div>

          {/* Curriculum */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-cw-text">
              Curriculum
            </h4>
            <ul className="space-y-2 text-xs text-cw-muted">
              <li>
                <Link href="/" className="hover:text-white transition-colors">
                  Educational Apps
                </Link>
              </li>
              <li>
                <Link href="/#courses" className="hover:text-white transition-colors">
                  All Batches
                </Link>
              </li>
              <li>
                <Link href="/search" className="hover:text-white transition-colors">
                  Course Search
                </Link>
              </li>
              <li>
                <Link href="/student" className="hover:text-white transition-colors">
                  My Dashboard
                </Link>
              </li>
            </ul>
          </div>

          {/* Platform & Support */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-cw-text">
              Support & Legal
            </h4>
            <ul className="space-y-2 text-xs text-cw-muted">
              <li>
                <Link href="/about" className="hover:text-white transition-colors">
                  About Course Wallah
                </Link>
              </li>
              <li>
                <Link href="/contact" className="hover:text-white transition-colors">
                  Contact Support
                </Link>
              </li>
              <li>
                <Link href="/privacy" className="hover:text-white transition-colors">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link href="/terms" className="hover:text-white transition-colors">
                  Terms of Service
                </Link>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="pt-8 border-t border-cw-border/60 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-cw-muted">
          <div>
            &copy; {new Date().getFullYear()} Course Wallah Platform. All rights reserved.
          </div>
          <div className="flex items-center gap-1">
            <span>Built with passion for engineering students across India</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
