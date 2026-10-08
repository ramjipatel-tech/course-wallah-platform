"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { 
  User, 
  Mail, 
  Lock, 
  ShieldCheck, 
  LogOut, 
  Calendar, 
  BookOpen, 
  AlertCircle, 
  CheckCircle2, 
  KeyRound 
} from "lucide-react";
import { api } from "@/lib/api";
import { StudentUser } from "@/lib/types";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { Badge } from "@/components/ui/Badge";

export default function ProfilePage() {
  const router = useRouter();
  const [student, setStudent] = useState<StudentUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Change password state
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwdLoading, setPwdLoading] = useState(false);
  const [pwdError, setPwdError] = useState<string | null>(null);
  const [pwdSuccess, setPwdSuccess] = useState<string | null>(null);

  useEffect(() => {
    async function loadProfile() {
      try {
        const data = await api.getStudentProfile();
        setStudent(data);
      } catch (err) {
        router.push("/login?next=/profile");
      } finally {
        setLoading(false);
      }
    }
    loadProfile();
  }, [router]);

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwdError(null);
    setPwdSuccess(null);

    if (newPassword !== confirmPassword) {
      setPwdError("New passwords do not match.");
      return;
    }

    setPwdLoading(true);
    try {
      await api.changePassword({ old_password: oldPassword, new_password: newPassword });
      setPwdSuccess("Password updated successfully.");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      setPwdError(err.message || "Failed to update password.");
    } finally {
      setPwdLoading(false);
    }
  };

  const handleLogout = async () => {
    await api.studentLogout();
    router.push("/");
    router.refresh();
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-44 cw-card-elevated cw-skeleton rounded-3xl" />
      </div>
    );
  }

  if (!student) return null;

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/student" },
          { label: "My Profile" },
        ]}
      />

      {/* Profile Overview Card */}
      <div className="cw-card-elevated rounded-3xl p-6 sm:p-10 border border-cw-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
        <div className="flex items-center gap-5">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600 to-cyan-500 flex items-center justify-center text-white font-black text-2xl shadow-lg flex-shrink-0">
            {student.name.charAt(0).toUpperCase()}
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-black text-white">
                {student.name}
              </h1>
              <Badge variant="success">Verified Student</Badge>
            </div>
            <p className="text-xs sm:text-sm text-cw-muted flex items-center gap-1.5">
              <Mail className="w-3.5 h-3.5" />
              <span>{student.email}</span>
            </p>
          </div>
        </div>

        <button
          onClick={handleLogout}
          className="flex items-center gap-2 px-4 py-2 bg-cw-surface hover:bg-rose-500/10 text-rose-400 hover:text-rose-300 border border-cw-border hover:border-rose-500/30 text-xs font-bold rounded-xl transition-all"
        >
          <LogOut className="w-4 h-4" />
          <span>Sign Out</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Account Details */}
        <div className="cw-card rounded-2xl p-6 border border-cw-border space-y-4">
          <h2 className="font-bold text-base text-white flex items-center gap-2">
            <User className="w-4 h-4 text-cw-primary" />
            <span>Academic Profile</span>
          </h2>

          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between p-3 rounded-xl bg-cw-surface border border-cw-border">
              <span className="text-cw-muted">Enrolled Batches</span>
              <span className="font-bold text-white font-mono">{student.enrolled_batches_count || 0}</span>
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl bg-cw-surface border border-cw-border">
              <span className="text-cw-muted">Account Status</span>
              <span className="text-emerald-400 font-bold uppercase">{student.status || "ACTIVE"}</span>
            </div>

            {student.created_at && (
              <div className="flex items-center justify-between p-3 rounded-xl bg-cw-surface border border-cw-border">
                <span className="text-cw-muted">Member Since</span>
                <span className="text-white font-medium">{new Date(student.created_at).toLocaleDateString()}</span>
              </div>
            )}
          </div>
        </div>

        {/* Password Security */}
        <div className="cw-card rounded-2xl p-6 border border-cw-border space-y-4">
          <h2 className="font-bold text-base text-white flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-cyan-400" />
            <span>Account Security</span>
          </h2>

          {pwdError && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/25 rounded-xl text-xs text-rose-300 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{pwdError}</span>
            </div>
          )}

          {pwdSuccess && (
            <div className="p-3 bg-emerald-500/10 border border-emerald-500/25 rounded-xl text-xs text-emerald-300 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
              <span>{pwdSuccess}</span>
            </div>
          )}

          <form onSubmit={handlePasswordChange} className="space-y-3">
            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-cw-text">Current Password</label>
              <input
                type="password"
                required
                placeholder="••••••••"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                className="w-full px-3 py-2 bg-cw-surface border border-cw-border rounded-xl text-xs text-white focus:outline-none focus:border-cw-primary"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-cw-text">New Password</label>
              <input
                type="password"
                required
                placeholder="At least 6 characters"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-3 py-2 bg-cw-surface border border-cw-border rounded-xl text-xs text-white focus:outline-none focus:border-cw-primary"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-cw-text">Confirm New Password</label>
              <input
                type="password"
                required
                placeholder="Re-enter new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-3 py-2 bg-cw-surface border border-cw-border rounded-xl text-xs text-white focus:outline-none focus:border-cw-primary"
              />
            </div>

            <button
              type="submit"
              disabled={pwdLoading}
              className="w-full py-2.5 bg-cw-primary hover:bg-cw-primary-hover text-white text-xs font-bold rounded-xl transition-all disabled:opacity-40"
            >
              {pwdLoading ? "Updating..." : "Update Password"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
