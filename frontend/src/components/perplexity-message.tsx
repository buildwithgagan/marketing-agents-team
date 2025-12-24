"use client";

import { useMessage } from "@assistant-ui/react";
import { MarkdownText } from "@/components/markdown-text";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Card } from "@/components/ui/card";
import { LinkIcon, ImageIcon, CheckCircle2, ListTodo } from "lucide-react";
import { useMemo } from "react";

export const PerplexityMessage = () => {
  const content = useMessage((s: any) => s.content);

  const textContent = useMemo(() => {
    if (!content) return "";
    return content.map((part: any) => (part.type === "text" ? part.text : "")).join("");
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

  // Extract links: [text](url) - excluding images
  const sources = useMemo(() => {
    const linkRegex = /(?<!\!)\[(.*?)\]\((.*?)\)/g;
    const matches = [];
    let match;
    const seen = new Set();
    while ((match = linkRegex.exec(textContent)) !== null) {
      const url = match[2];
      if (!seen.has(url)) {
        matches.push({ text: match[1], url: match[2] });
        seen.add(url);
      }
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
               <div key={idx} className="relative aspect-video h-32 flex-shrink-0 snap-start overflow-hidden rounded-xl border bg-muted/50 transition-all hover:scale-[1.02] hover:shadow-md cursor-pointer group">
                  <picture>
                     <img 
                       src={img.src} 
                       alt={img.alt} 
                       className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-110" 
                       onError={(e) => (e.currentTarget.style.display = 'none')}
                     />
                  </picture>
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
               </div>
             ))}
           </div>
        </div>
      )}

      {/* Sources Section */}
      {sources.length > 0 && (
        <div className="flex flex-col gap-3 animate-in fade-in slide-in-from-bottom-3 duration-500 delay-100">
           <div className="flex items-center gap-2 text-primary font-semibold text-sm">
             <LinkIcon className="size-4" />
             <span>Sources</span>
           </div>
           <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
             {sources.slice(0, 4).map((source, idx) => (
               <a 
                 key={idx} 
                 href={source.url} 
                 target="_blank" 
                 rel="noopener noreferrer"
                 className="flex flex-col justify-between p-3 h-20 rounded-xl border bg-card hover:bg-accent/50 transition-all hover:border-primary/30 hover:shadow-sm text-xs group decoration-0 no-underline"
               >
                 <span className="font-medium line-clamp-2 leading-snug group-hover:text-primary transition-colors">
                   {source.text || new URL(source.url).hostname}
                 </span>
                 <div className="flex items-center gap-1 text-muted-foreground pt-1">
                   <img 
                     src={`https://www.google.com/s2/favicons?domain=${new URL(source.url).hostname}`} 
                     alt="favicon" 
                     className="w-3 h-3 opacity-70" 
                   />
                   <span className="truncate opacity-70 group-hover:opacity-100 transition-opacity">
                     {new URL(source.url).hostname.replace('www.', '')}
                   </span>
                 </div>
               </a>
             ))}
             {sources.length > 4 && (
                <div className="flex items-center justify-center p-3 h-20 rounded-xl border border-dashed bg-muted/30 text-xs font-medium text-muted-foreground">
                  +{sources.length - 4} more
                </div>
             )}
           </div>
        </div>
      )}

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
         {(images.length > 0 || sources.length > 0) && (
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
