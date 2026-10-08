interface BadgeProps {
  children: React.ReactNode;
  variant?: "primary" | "success" | "warning" | "accent" | "neutral";
  className?: string;
}

export function Badge({
  children,
  variant = "primary",
  className = "",
}: BadgeProps) {
  const variantStyles = {
    primary: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    success: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    warning: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    accent: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
    neutral: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold border ${variantStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
