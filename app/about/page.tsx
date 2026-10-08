import { Sparkles, BookOpen, ShieldCheck, Zap, Heart, GraduationCap, ArrowRight } from "lucide-react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { CourseWallahLogo } from "@/components/brand/CourseWallahLogo";

export const metadata = {
  title: "About Us — Course Wallah",
  description: "Learn about Course Wallah's mission to make high-quality engineering education accessible to every student across India.",
};

export default function AboutPage() {
  return (
    <div className="space-y-12 max-w-4xl mx-auto">
      <Breadcrumbs
        items={[
          { label: "Home", href: "/" },
          { label: "About Course Wallah" },
        ]}
      />

      {/* Hero */}
      <section className="text-center space-y-4 py-6">
        <div className="flex justify-center">
          <CourseWallahLogo size="lg" withTagline={true} />
        </div>
        <h1 className="text-3xl sm:text-5xl font-black text-white tracking-tight leading-tight">
          Empowering India&apos;s Engineering Students
        </h1>
        <p className="text-sm sm:text-lg text-cw-muted max-w-2xl mx-auto leading-relaxed">
          Course Wallah was founded to bring structured academic curriculum, high-definition lecture streams, and verified handwritten study notes directly to students.
        </p>
      </section>

      {/* Values Grid */}
      <section className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div className="cw-card p-6 space-y-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-cw-primary">
            <GraduationCap className="w-5 h-5" />
          </div>
          <h3 className="font-bold text-base text-white">Structured Curriculum</h3>
          <p className="text-xs sm:text-sm text-cw-muted leading-relaxed">
            Every subject is broken down into clear unit modules, chapter topics, and sequential video lessons so students can learn at their own pace.
          </p>
        </div>

        <div className="cw-card p-6 space-y-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
            <Zap className="w-5 h-5" />
          </div>
          <h3 className="font-bold text-base text-white">High-Speed Streaming</h3>
          <p className="text-xs sm:text-sm text-cw-muted leading-relaxed">
            Optimized video playback delivers 1080p and 720p streams with adaptive bitrate delivery, ensuring zero buffering even on slower mobile networks.
          </p>
        </div>

        <div className="cw-card p-6 space-y-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <BookOpen className="w-5 h-5" />
          </div>
          <h3 className="font-bold text-base text-white">Verified Study Notes</h3>
          <p className="text-xs sm:text-sm text-cw-muted leading-relaxed">
            Companion lecture notes and formula reference sheets are synchronized directly with video timestamps for rapid revision.
          </p>
        </div>

        <div className="cw-card p-6 space-y-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
            <Sparkles className="w-5 h-5" />
          </div>
          <h3 className="font-bold text-base text-white">AI-Powered Assistance</h3>
          <p className="text-xs sm:text-sm text-cw-muted leading-relaxed">
            Our student AI assistant helps learners find course topics, navigate curriculum chapters, and clarify lecture concepts instantly.
          </p>
        </div>
      </section>

      {/* Call to Action */}
      <section className="cw-card-elevated rounded-3xl p-8 sm:p-12 text-center space-y-4 border border-cw-border">
        <h2 className="text-xl sm:text-2xl font-bold text-white">
          Ready to Start Learning?
        </h2>
        <p className="text-xs sm:text-sm text-cw-muted max-w-lg mx-auto">
          Explore our open course catalog, enroll in engineering batches, and start streaming lectures today.
        </p>
        <div className="pt-2">
          <Link
            href="/#courses"
            className="inline-flex items-center gap-2 px-6 py-3 bg-cw-primary hover:bg-cw-primary-hover text-white font-bold text-sm rounded-xl shadow-lg shadow-blue-500/20 transition-all hover:scale-105"
          >
            <span>Browse Courses</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
