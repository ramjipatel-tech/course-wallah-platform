import { ShieldCheck, Lock, Eye, FileText } from "lucide-react";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";

export const metadata = {
  title: "Privacy Policy — Course Wallah",
  description: "Course Wallah student data privacy policy and protection standards.",
};

export default function PrivacyPage() {
  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <Breadcrumbs
        items={[
          { label: "Home", href: "/" },
          { label: "Privacy Policy" },
        ]}
      />

      <div className="space-y-3">
        <h1 className="text-2xl sm:text-4xl font-black text-white tracking-tight">
          Privacy Policy
        </h1>
        <p className="text-xs sm:text-sm text-cw-muted">
          Last Updated: {new Date().toLocaleDateString("en-US", { month: "long", year: "numeric" })}
        </p>
      </div>

      <div className="cw-card-elevated rounded-3xl p-6 sm:p-10 border border-cw-border space-y-8 text-xs sm:text-sm text-cw-text leading-relaxed">
        <section className="space-y-2">
          <h2 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <span>1. Information We Collect</span>
          </h2>
          <p className="text-cw-muted">
            Course Wallah collects basic student profile details (such as full name and email address) when you register for an account. We also record course enrollment history and lecture completion progress to allow you to resume studying seamlessly across devices.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
            <Lock className="w-5 h-5 text-cyan-400" />
            <span>2. How We Protect Your Data</span>
          </h2>
          <p className="text-cw-muted">
            All passwords are encrypted with strong salted cryptographic hashing algorithms. We do not store plaintext passwords. Video lecture access and PDF note reading sessions are secured through authenticated short-lived sessions to safeguard copyrighted learning materials.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
            <Eye className="w-5 h-5 text-cw-primary" />
            <span>3. Cookies & Session Storage</span>
          </h2>
          <p className="text-cw-muted">
            We use essential HttpOnly session cookies to keep you signed in securely. We do not sell your personal information or share student data with third-party advertising networks.
          </p>
        </section>
      </div>
    </div>
  );
}
