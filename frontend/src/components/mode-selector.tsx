"use client";

import { Globe, Telescope, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { useState } from "react";

export type Mode = "search" | "research" | null;

interface ModeSelectorProps {
  onModeSelect: (mode: Mode) => void;
  selectedMode: Mode;
}

export function ModeSelector({
  onModeSelect,
  selectedMode,
}: ModeSelectorProps) {
  const modes = [
    {
      id: "search" as const,
      label: "Search",
      description: "Fast answers to everyday questions",
      icon: Globe,
    },
    {
      id: "research" as const,
      label: "Research",
      description: "Deep research on any topic",
      icon: Telescope,
    },
  ];

  return (
    <div className="flex flex-col gap-3 px-4 pb-4">
      <div className="flex items-center gap-2">
        {modes.map((mode) => {
          const Icon = mode.icon;
          const isSelected = selectedMode === mode.id;

          return (
            <button
              key={mode.id}
              type="button"
              onClick={() => onModeSelect(mode.id)}
              className={cn(
                "border border-border bg-muted/50 hover:bg-muted transition duration-300 ease-out select-none items-center relative group/button font-semibold justify-center text-center items-center rounded-lg cursor-pointer active:scale-[0.97] active:duration-150 active:ease-outExpo origin-center whitespace-nowrap inline-flex text-sm h-8 px-2.5 text-foreground",
                isSelected && "bg-accent border-accent-foreground/20",
                "focus:outline-none outline-none outline-transparent"
              )}
            >
              <Icon className="size-4 mr-1.5" />
              <span>{mode.label}</span>
            </button>
          );
        })}
      </div>
      {selectedMode && (
        <div className="text-xs text-muted-foreground px-1">
          {modes.find((m) => m.id === selectedMode)?.description}
        </div>
      )}
    </div>
  );
}
