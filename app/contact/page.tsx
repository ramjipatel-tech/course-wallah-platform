"use client";

import { useState } from "react";
import { Mail, MessageSquare, Send, CheckCircle2, AlertCircle, Sparkles, HelpCircle } from "lucide-react";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { api } from "@/lib/api";

export default function ContactPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      const res = await api.submitContact({ name, email, subject, message });
      setSuccess(res.message || "Thank you! Your message has been sent successfully.");
      setName("");
      setEmail("");
      setSubject("");
      setMessage("");
    } catch (err: any) {
      setError(err.message || "Failed to submit message. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-10 max-w-3xl mx-auto">
      <Breadcrumbs
        items={[
          { label: "Home", href: "/" },
          { label: "Contact Support" },
        ]}
      />

      <div className="text-center space-y-3">
        <h1 className="text-2xl sm:text-4xl font-black text-white tracking-tight">
          Get in Touch with Course Wallah
        </h1>
        <p className="text-xs sm:text-sm text-cw-muted max-w-lg mx-auto">
          Have questions about your courses, lecture access, or academic notes? Send us a message and our academic support team will respond promptly.
        </p>
      </div>

      <div className="cw-card-elevated rounded-3xl p-6 sm:p-10 border border-cw-border/80 shadow-xl space-y-6">
        {error && (
          <div className="p-3.5 bg-rose-500/10 border border-rose-500/25 rounded-2xl flex items-center gap-2.5 text-xs text-rose-300">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/25 rounded-2xl flex items-center gap-2.5 text-xs text-emerald-300">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <span>{success}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-cw-text">Your Full Name</label>
              <input
                type="text"
                required
                placeholder="Rohit Verma"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-2.5 bg-cw-surface border border-cw-border rounded-xl text-sm text-white placeholder-cw-muted focus:outline-none focus:border-cw-primary focus:ring-2 focus:ring-cw-primary/20 transition-all"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-cw-text">Email Address</label>
              <input
                type="email"
                required
                placeholder="student@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-2.5 bg-cw-surface border border-cw-border rounded-xl text-sm text-white placeholder-cw-muted focus:outline-none focus:border-cw-primary focus:ring-2 focus:ring-cw-primary/20 transition-all"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-cw-text">Subject / Topic</label>
            <input
              type="text"
              required
              placeholder="e.g. Question regarding Digital Electronics batch"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full px-4 py-2.5 bg-cw-surface border border-cw-border rounded-xl text-sm text-white placeholder-cw-muted focus:outline-none focus:border-cw-primary focus:ring-2 focus:ring-cw-primary/20 transition-all"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-cw-text">Message / Query</label>
            <textarea
              required
              rows={5}
              placeholder="Describe your question or issue in detail..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              className="w-full px-4 py-2.5 bg-cw-surface border border-cw-border rounded-xl text-sm text-white placeholder-cw-muted focus:outline-none focus:border-cw-primary focus:ring-2 focus:ring-cw-primary/20 transition-all"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-cw-primary hover:bg-cw-primary-hover text-white font-bold text-sm rounded-xl shadow-lg shadow-blue-500/20 flex items-center justify-center gap-2 disabled:opacity-40 transition-all hover:scale-[1.01] active:scale-[0.99] mt-2"
          >
            <span>{loading ? "Sending Message..." : "Submit Inquiry"}</span>
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
