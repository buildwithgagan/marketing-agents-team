"use client";

import { cn } from "@/lib/utils";

interface MarketingLogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
}

export function MarketingLogo({ className, size = "md" }: MarketingLogoProps) {
  const sizeClasses = {
    sm: "w-6 h-6",
    md: "w-8 h-8",
    lg: "w-12 h-12",
  };

  return (
    <div className={cn("flex items-center justify-center", className)}>
      <svg
        viewBox="0 0 64 64"
        className={cn(sizeClasses[size])}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient
            id="brewXGradient"
            x1="0%"
            y1="0%"
            x2="100%"
            y2="100%"
          >
            <stop offset="0%" stopColor="currentColor" stopOpacity="1" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.85" />
          </linearGradient>
        </defs>

        {/* Coffee cup body */}
        <path
          d="M18 20 L18 48 L42 48 L42 20 L18 20 Z"
          fill="url(#brewXGradient)"
          className="text-primary"
          stroke="currentColor"
          strokeWidth="1.5"
        />

        {/* Cup handle */}
        <path
          d="M42 28 Q48 28 48 36 Q48 44 42 44"
          stroke="currentColor"
          strokeWidth="2.5"
          fill="none"
          strokeLinecap="round"
          className="text-primary"
        />

        {/* Coffee surface */}
        <ellipse
          cx="30"
          cy="20"
          rx="12"
          ry="3"
          fill="currentColor"
          className="text-primary opacity-60"
        />

        {/* Steam lines forming X pattern */}
        <path
          d="M24 12 L28 8"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          className="text-primary opacity-80"
        />
        <path
          d="M28 8 L24 4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          className="text-primary opacity-80"
        />
        <path
          d="M36 12 L32 8"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          className="text-primary opacity-80"
        />
        <path
          d="M32 8 L36 4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          className="text-primary opacity-80"
        />

        {/* X accent in the cup */}
        <path
          d="M26 32 L34 40 M34 32 L26 40"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          className="text-primary opacity-40"
        />
      </svg>
    </div>
  );
}
