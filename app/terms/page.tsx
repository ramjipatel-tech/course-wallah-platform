import { BookOpen, AlertCircle, CheckCircle2 } from "lucide-react";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";

export const metadata = {
  title: "Terms of Service — Course Wallah",
  description: "Course Wallah student learning portal terms of service and usage guidelines.",
};

export default function TermsPage() {
  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <Breadcrumbs
        items={[
          { label: "Home", href: "/" },
          { label: "Terms of Service" },
        ]}
      />

      <div className="space-y-3">
        <h1 className="text-2xl sm:text-4xl font-black text-white tracking-tight">
          Terms of Service
        </h1>
        <p className="text-xs sm:text-sm text-cw-muted">
          Last Updated: {new Date().toLocaleDateString("en-US", { month: "long", year: "numeric" })}
        </p>
      </div>

      <div className="cw-card-elevated rounded-3xl p-6 sm:p-10 border border-cw-border space-y-8 text-xs sm:text-sm text-cw-text leading-relaxed">
        <section className="space-y-2">
          <h2 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-cw-primary" />
            <span>1. Student Account & Permitted Use</span>
          </h2>
          <p className="text-cw-muted">
            Course Wallah provides educational course materials for personal academic study and test preparation. Your account is for individual personal use and may not be shared, sold, or transferred to third parties.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            <span>2. Intellectual Property & Study Materials</span>
          </h2>
          <p className="text-cw-muted">
            All lecture videos, animated watermark protected streams, and downloadable companion study notes are the exclusive intellectual property of Course Wallah and its academic creators. Unauthorized scraping, recording, redistribution, or commercial resale of course materials is strictly prohibited.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-amber-400" />
            <span>3. Academic Integrity</span>
          </h2>
          <p className="text-cw-muted">
            Students are expected to uphold high academic standards. Accounts found violating platform security policies or attempting unauthorized mass extraction of course content may have their access suspended.
          </p>
        </section>
      </div>
    </div>
  );
}
