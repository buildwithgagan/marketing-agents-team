"use client";

import { useMessage } from "@assistant-ui/react";
import { MarkdownText } from "@/components/markdown-text";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Card } from "@/components/ui/card";
import { LinkIcon, ImageIcon, CheckCircle2, ListTodo } from "lucide-react";
import { useMemo } from "react";

/**
 * Safely extract hostname from a URL string.
 * Handles various URL formats and edge cases.
 */
function getHostname(url: string): string {
  if (!url || typeof url !== "string") {
    return "unknown";
  }

  try {
    // If URL doesn't have a protocol, add https://
    let urlToParse = url.trim();
    if (!urlToParse.match(/^https?:\/\//i)) {
      urlToParse = `https://${urlToParse}`;
    }

    const urlObj = new URL(urlToParse);
    return urlObj.hostname.replace(/^www\./i, "");
  } catch (e) {
    // If URL parsing fails, try to extract hostname manually
    // Remove protocol if present
    let hostname = url.replace(/^https?:\/\//i, "");
    // Remove path and query
    hostname = hostname.split("/")[0].split("?")[0].split("#")[0];
    // Remove www. prefix
    hostname = hostname.replace(/^www\./i, "");
    return hostname || "unknown";
  }
}

export const PerplexityMessage = () => {
  const content = useMessage((s: any) => s.content);

  const textContent = useMemo(() => {
    if (!content) return "";
    return content
      .map((part: any) => (part.type === "text" ? part.text : ""))
      .join("");
  }, [content]);

  // Extract images: ![alt](url)
  const images = useMemo(() => {
    const imgRegex = /!\[(.*?)\]\((.*?)\)/g;
    const matches = [];
    let match;
    while ((match = imgRegex.exec(textContent)) !== null) {
      matches.push({ alt: match[1], src: match[2] });
    }
    return matches;
  }, [textContent]);

  // Extract links: [text](url) - only valid HTTP/HTTPS URLs
  const sources = useMemo(() => {
    const linkRegex = /(?<!\!)\[(.*?)\]\((https?:\/\/[^\s\)]+)\)/g;
    const matches = [];
    let match;
    const seen = new Set();
    while ((match = linkRegex.exec(textContent)) !== null) {
      const url = match[2];
      // Skip if already seen or if URL looks invalid
      if (seen.has(url)) continue;
      // Must have a valid domain (at least x.y format)
      const hostname = getHostname(url);
      if (!hostname || hostname === "unknown" || !hostname.includes("."))
        continue;

      matches.push({ text: match[1], url: match[2] });
      seen.add(url);
    }
    return matches;
  }, [textContent]);

  // Check if this is a Plan/Todo message
  const isPlan = textContent.includes("### Execution Plan:");

  if (!textContent) return null;

  return (
    <div className="flex flex-col gap-6 w-full max-w-full overflow-hidden">
      {/* Images Section */}
      {images.length > 0 && (
        <div className="flex flex-col gap-3 animate-in fade-in slide-in-from-bottom-2 duration-500">
          <div className="flex items-center gap-2 text-primary font-semibold text-sm">
            <ImageIcon className="size-4" />
            <span>Images</span>
          </div>
          <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thumb-muted scrollbar-track-transparent scrollbar-thin snap-x">
            {images.map((img, idx) => (
              <div
                key={idx}
                className="relative aspect-video h-32 flex-shrink-0 snap-start overflow-hidden rounded-xl border bg-muted/50 transition-all hover:scale-[1.02] hover:shadow-md cursor-pointer group"
              >
                <picture>
                  <img
                    src={img.src}
                    alt={img.alt}
                    className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-110"
                    onError={(e) => (e.currentTarget.style.display = "none")}
                  />
                </picture>
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sources Section - REMOVED: Sources are already included in the answer at the bottom */}

      {/* Plan Section Override */}
      {isPlan && (
        <div className="flex flex-col gap-3 animate-in fade-in slide-in-from-bottom-4 duration-500 delay-150">
          <div className="flex items-center gap-2 text-primary font-semibold text-sm">
            <ListTodo className="size-4" />
            <span>Plan</span>
          </div>
        </div>
      )}

      {/* Answer / Text Section */}
      <div className="flex flex-col gap-3 animate-in fade-in slide-in-from-bottom-5 duration-500 delay-200">
        {images.length > 0 && (
          <div className="flex items-center gap-2 text-primary font-semibold text-sm mb-1">
            <CheckCircle2 className="size-4" />
            <span>Answer</span>
          </div>
        )}
        <div className="prose dark:prose-invert max-w-none text-foreground/90 leading-7 text-[15px]">
          <MarkdownText />
        </div>
      </div>
    </div>
  );
};
