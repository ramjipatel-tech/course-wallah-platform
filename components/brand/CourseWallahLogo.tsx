"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { GraduationCap } from "lucide-react";

interface CourseWallahLogoProps {
  size?: "sm" | "md" | "lg";
  withText?: boolean;
  withTagline?: boolean;
  className?: string;
  href?: string;
}

export function CourseWallahLogo({
  size = "md",
  withText = true,
  withTagline = false,
  className = "",
  href = "/",
}: CourseWallahLogoProps) {
  const [imageError, setImageError] = useState(false);

  const sizeClasses = {
    sm: { img: "w-7 h-7", text: "text-base", sub: "text-[9px]" },
    md: { img: "w-9 h-9", text: "text-lg", sub: "text-[10px]" },
    lg: { img: "w-14 h-14", text: "text-2xl", sub: "text-xs" },
  };

  const selectedSize = sizeClasses[size];

  const content = (
    <div className={`flex items-center gap-3 group ${className}`}>
      {/* Official Course Wallah Logo Image */}
      <div className={`relative ${selectedSize.img} rounded-xl overflow-hidden flex items-center justify-center flex-shrink-0 transition-transform duration-300 group-hover:scale-105 shadow-md shadow-blue-500/10`}>
        {!imageError ? (
          <img
            src="/logo.png"
            alt="Course Wallah Official Logo"
            className="w-full h-full object-contain"
            onError={() => setImageError(true)}
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-500 flex items-center justify-center text-white font-black">
            <GraduationCap className="w-5 h-5 text-white" />
          </div>
        )}
      </div>

      {/* Brand Typography */}
      {withText && (
        <div className="flex flex-col">
          <div className={`font-black tracking-tight ${selectedSize.text} leading-tight text-white flex items-center gap-1.5`}>
            <span>COURSE</span>
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-cyan-400 to-indigo-300">
              WALLAH
            </span>
          </div>
          {withTagline && (
            <span className={`font-semibold tracking-wider text-cw-muted uppercase ${selectedSize.sub}`}>
              Dynamic Student Platform
            </span>
          )}
        </div>
      )}
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="inline-flex focus:outline-none focus:ring-2 focus:ring-cw-primary/50 rounded-xl">
        {content}
      </Link>
    );
  }

  return content;
}
