"use client";

import { Thread } from "@/components/thread";
import { CustomThreadList } from "@/components/thread-list";
import { MyAssistantRuntimeProvider } from "@/components/MyAssistantRuntime";
import { cn } from "@/lib/utils";
import { useState, useEffect, useCallback, useRef } from "react";
import { PanelLeftOpen, Moon, Sun, Plus, MessageSquare, ChevronDown, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "next-themes";

const MODEL_OPTIONS = [
  {
    label: "Thinking Models (Reasoning)",
    options: [
      { id: "gpt-5.2-chat-latest", name: "GPT-5.2 Chat (Full)" },
      { id: "gpt-5.1-chat-latest", name: "GPT-5.1 Chat (Adaptive)" },
      { id: "o3-mini", name: "o3-mini (Reasoning)" },
      { id: "o1", name: "o1 (Reasoning)" },
      { id: "gpt-5-mini", name: "GPT-5 Mini" },
      { id: "gpt-5-nano", name: "GPT-5 Nano (Ultra-Fast)" },
    ],
  },
  {
    label: "Classic Models",
    options: [
      { id: "gpt-4.1", name: "GPT-4.1 (Standard)" },
      { id: "gpt-4.1-mini", name: "GPT-4.1 Mini" },
    ],
  },
];

export default function Home() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [threads, setThreads] = useState<any[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string>("default-thread");
  const [selectedModel, setSelectedModel] = useState("gpt-4.1");
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Load threads
  const loadThreads = useCallback(() => {
    const savedThreads = localStorage.getItem("assistant_threads");
    if (savedThreads) {
       try {
         setThreads(JSON.parse(savedThreads));
       } catch (e) {
         console.error("Failed to parse threads", e);
       }
    }
    const savedId = localStorage.getItem("assistant_current_thread_id");
    if (savedId) {
      setCurrentThreadId(savedId);
    }
  }, []);

  // Avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
    loadThreads();

    const handleUpdate = () => loadThreads();
    window.addEventListener("assistant-threads-updated", handleUpdate);
    return () => window.removeEventListener("assistant-threads-updated", handleUpdate);
  }, [loadThreads]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsModelDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleNewThread = () => {
    const newId = Math.random().toString(36).substring(7);
    localStorage.setItem("assistant_current_thread_id", newId);
    setCurrentThreadId(newId);
    const updatedThreads = [{ id: newId, title: "New Chat", updatedAt: Date.now() }, ...threads];
    setThreads(updatedThreads);
    localStorage.setItem("assistant_threads", JSON.stringify(updatedThreads));
  };

  const handleSwitchThread = (id: string) => {
    localStorage.setItem("assistant_current_thread_id", id);
    setCurrentThreadId(id);
  };

  useEffect(() => {
    const handleThreadChange = (e: Event) => {
      const customEvent = e as CustomEvent;
      if (customEvent.detail && customEvent.detail.threadId) {
        setCurrentThreadId(customEvent.detail.threadId);
        localStorage.setItem("assistant_current_thread_id", customEvent.detail.threadId);
      }
    };

    window.addEventListener("assistant-change-thread", handleThreadChange);
    return () => window.removeEventListener("assistant-change-thread", handleThreadChange);
  }, []);

  const currentModelName = MODEL_OPTIONS.flatMap(g => g.options).find(o => o.id === selectedModel)?.name || selectedModel;

  return (
    <MyAssistantRuntimeProvider key={`${currentThreadId}-${selectedModel}-${thinkingEnabled}`} model={selectedModel} thinking={thinkingEnabled} threadId={currentThreadId}>
      <main className="flex h-screen w-screen bg-background overflow-hidden text-foreground">
        {/* Sidebar */}
        <aside 
          className={cn(
            "border-r bg-muted/30 transition-all duration-300 ease-in-out flex flex-col relative group",
            sidebarOpen ? "w-64" : "w-16"
          )}
        >
          <div className={cn("p-4 flex items-center border-b flex-shrink-0 h-14", sidebarOpen ? "justify-between" : "justify-center")}>
            {sidebarOpen && <h1 className="font-bold text-sm tracking-tight text-primary">DeepAgent</h1>}
            <Button variant="ghost" size="icon" onClick={handleNewThread} className="h-8 w-8 hover:bg-background/80">
               <Plus className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto w-full">
            <CustomThreadList isOpen={sidebarOpen} />
          </div>
        </aside>

        {/* Main Content */}
        <div className="flex-1 flex flex-col relative overflow-hidden bg-background">
          <header className="h-14 border-b flex items-center px-4 gap-4 flex-shrink-0 bg-background/80 backdrop-blur-md z-10">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
            >
              <PanelLeftOpen className={cn("h-4 w-4 transition-transform", sidebarOpen && "rotate-180")} />
            </Button>
            
            <div className="flex items-center gap-2">
               <div className="flex items-center bg-secondary/30 rounded-lg p-0.5 border relative" ref={dropdownRef}>
                  <button
                    onClick={() => setIsModelDropdownOpen(!isModelDropdownOpen)}
                    className="flex items-center gap-2 px-3 py-1 text-[11px] font-bold hover:bg-secondary/50 rounded-md transition-colors"
                  >
                    <span>{currentModelName}</span>
                    <ChevronDown className={cn("size-3 transition-transform", isModelDropdownOpen && "rotate-180")} />
                  </button>

                  {isModelDropdownOpen && (
                    <div className="absolute top-full left-0 mt-1 w-64 bg-popover border border-border rounded-xl shadow-2xl z-50 py-2 animate-in fade-in slide-in-from-top-1">
                      {MODEL_OPTIONS.map((group) => (
                        <div key={group.label} className="mb-2 last:mb-0">
                          <div className="px-3 py-1 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{group.label}</div>
                          {group.options.map((opt) => (
                            <button
                              key={opt.id}
                              onClick={() => {
                                setSelectedModel(opt.id);
                                setIsModelDropdownOpen(false);
                              }}
                              className={cn(
                                "w-full text-left px-3 py-2 text-xs flex items-center justify-between transition-colors",
                                selectedModel === opt.id ? "bg-primary/10 text-primary" : "hover:bg-muted"
                              )}
                            >
                              <span className="font-medium">{opt.name}</span>
                              {selectedModel === opt.id && <Check className="size-3" />}
                            </button>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {(selectedModel.startsWith("gpt-5") || selectedModel.startsWith("o1") || selectedModel.startsWith("o3")) && (
                    <>
                      <div className="w-[1px] h-3 bg-border mx-1" />
                      <label className="flex items-center gap-1.5 px-2 cursor-pointer group">
                        <input 
                          type="checkbox" 
                          checked={thinkingEnabled} 
                          onChange={(e) => setThinkingEnabled(e.target.checked)}
                          className="size-3 rounded border-muted-foreground/30 accent-primary"
                        />
                        <span className="text-[10px] font-semibold text-muted-foreground group-hover:text-foreground transition-colors uppercase tracking-tight">Thinking</span>
                      </label>
                    </>
                  )}
               </div>
            </div>

            <div className="flex-1" />
            
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => {
                  if (!(document as any).startViewTransition) {
                    setTheme(theme === "dark" ? "light" : "dark");
                    return;
                  }
                  (document as any).startViewTransition(() => {
                    setTheme(theme === "dark" ? "light" : "dark");
                  });
                }}
                className="h-8 w-8 text-muted-foreground hover:text-foreground relative overflow-hidden"
              >
                {mounted && (
                  <>
                    <Sun className="h-4 w-4 absolute transition-all scale-100 rotate-0 dark:scale-0 dark:rotate-90" />
                    <Moon className="h-4 w-4 absolute transition-all scale-0 rotate-90 dark:scale-100 dark:rotate-0" />
                  </>
                )}
              </Button>
            </div>
          </header>

          <div className="flex-1 relative overflow-hidden bg-background">
             <Thread />
          </div>
        </div>
      </main>
    </MyAssistantRuntimeProvider>
  );
}
