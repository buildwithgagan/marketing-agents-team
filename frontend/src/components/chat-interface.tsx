"use client";

import { useState, useRef, useEffect } from "react";
import { Send, User, Bot, Loader2, Sparkles, Plus, MessageSquare, History, Trash2, ChevronLeft, ChevronRight, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant" | "tool";
  content: string;
}

interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
}

export function ChatInterface() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [currentStatus, setCurrentStatus] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load sessions from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem("deepagent_sessions");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setSessions(parsed);
        if (parsed.length > 0) {
          setCurrentSessionId(parsed[0].id);
        }
      } catch (e) {
        console.error("Failed to parse sessions", e);
      }
    }
  }, []);

  // Save sessions to localStorage when they change
  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem("deepagent_sessions", JSON.stringify(sessions));
    }
  }, [sessions]);

  const currentSession = sessions.find(s => s.id === currentSessionId);
  const messages = currentSession?.messages || [];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentStatus]);

  const createNewChat = () => {
    const newId = Math.random().toString(36).substring(7);
    const newSession: ChatSession = {
      id: newId,
      title: "New Chat",
      messages: [],
      updatedAt: Date.now()
    };
    setSessions(prev => [newSession, ...prev]);
    setCurrentSessionId(newId);
  };

  const deleteSession = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSessions(prev => prev.filter(s => s.id !== id));
    if (currentSessionId === id) {
      setCurrentSessionId(null);
    }
    toast.success("Chat deleted");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    let sessionId = currentSessionId;
    if (!sessionId) {
      const newId = Math.random().toString(36).substring(7);
      const newSession: ChatSession = {
        id: newId,
        title: input.slice(0, 30) + (input.length > 30 ? "..." : ""),
        messages: [],
        updatedAt: Date.now()
      };
      setSessions(prev => [newSession, ...prev]);
      setCurrentSessionId(newId);
      sessionId = newId;
    }

    const userMessage: Message = { role: "user", content: input };
    
    setSessions(prev => prev.map(s => 
      s.id === sessionId 
        ? { ...s, messages: [...s.messages, userMessage], updatedAt: Date.now(), title: s.messages.length === 0 ? input.slice(0, 30) : s.title }
        : s
    ));

    setInput("");
    setIsLoading(true);
    setCurrentStatus("Initializing...");

    // Add placeholder for assistant
    setSessions(prev => prev.map(s => 
      s.id === sessionId 
        ? { ...s, messages: [...s.messages, { role: "assistant", content: "" }] }
        : s
    ));

    try {
      const response = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          messages: [...messages, userMessage],
          thread_id: sessionId 
        }),
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let done = false;
      let streamedContent = "";
      let buffer = "";

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const event = JSON.parse(line);
            if (event.type === "status") {
              setCurrentStatus(event.content);
              if (event.content.startsWith("Running tool")) {
                toast.info(event.content, { duration: 2000 });
              }
            } else if (event.type === "content") {
              streamedContent += event.content;
              setSessions(prev => prev.map(s => {
                if (s.id !== sessionId) return s;
                const newMsgs = [...s.messages];
                const last = newMsgs[newMsgs.length - 1];
                if (last && last.role === "assistant") {
                  last.content = streamedContent;
                }
                return { ...s, messages: newMsgs };
              }));
            } else if (event.type === "tool_result") {
              // Add a separate message for tool result to make it visible
              const toolMessage: Message = { role: "tool", content: event.content };
              setSessions(prev => prev.map(s => {
                if (s.id !== sessionId) return s;
                // Insert tool message before the current empty assistant message or as a new message
                const newMsgs = [...s.messages];
                const last = newMsgs[newMsgs.length - 1];
                if (last && last.role === "assistant" && !last.content) {
                  // Replace empty placeholder or shift it
                  newMsgs.splice(newMsgs.length - 1, 0, toolMessage);
                } else {
                  newMsgs.push(toolMessage);
                }
                return { ...s, messages: newMsgs };
              }));
            } else if (event.type === "error") {
              toast.error(event.content);
            }
          } catch (e) {
            console.error("Error parsing JSON line:", e, line);
          }
        }
      }
    } catch (error) {
      console.error("Error streaming chat:", error);
      toast.error("Failed to connect to backend");
    } finally {
      setIsLoading(false);
      setCurrentStatus(null);
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#020617] text-white overflow-hidden font-sans">
      {/* Sidebar */}
      <motion.aside 
        initial={false}
        animate={{ width: sidebarOpen ? 300 : 0, opacity: sidebarOpen ? 1 : 0 }}
        className="h-full bg-slate-900/50 border-r border-slate-800/50 flex flex-col relative"
      >
        <div className="p-4 flex flex-col h-full gap-4">
          <Button 
            onClick={createNewChat}
            className="w-full justify-start gap-2 bg-blue-600/10 border border-blue-600/20 text-blue-400 hover:bg-blue-600/20 py-6 rounded-2xl transition-all"
            variant="ghost"
          >
            <Plus className="w-5 h-5" />
            <span className="font-bold">New Mission</span>
          </Button>

          <ScrollArea className="flex-1 -mx-2 px-2">
            <div className="space-y-2 mt-4">
              <h3 className="px-2 text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] mb-4">Past Operations</h3>
              <AnimatePresence>
                {sessions.map((session) => (
                  <motion.div
                    key={session.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    onClick={() => setCurrentSessionId(session.id)}
                    className={cn(
                      "group flex items-center justify-between p-3.5 rounded-2xl cursor-pointer transition-all border",
                      currentSessionId === session.id 
                        ? "bg-slate-800 border-slate-700 shadow-lg shadow-black/20" 
                        : "bg-transparent border-transparent hover:bg-slate-800/40 hover:border-slate-800"
                    )}
                  >
                    <div className="flex items-center gap-3 overflow-hidden min-w-0">
                      <MessageSquare className={cn("w-4 h-4 flex-shrink-0", currentSessionId === session.id ? "text-blue-500" : "text-slate-500")} />
                      <span className="text-sm font-medium truncate text-slate-300 group-hover:text-white transition-colors">
                        {session.title}
                      </span>
                    </div>
                    <button 
                      onClick={(e) => deleteSession(session.id, e)}
                      className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-500/10 hover:text-red-500 rounded-lg transition-all"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </ScrollArea>

          <div className="pt-4 border-t border-slate-800/50 flex flex-col gap-2">
             <div className="p-4 bg-slate-800/30 rounded-2xl border border-slate-800 flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center font-bold text-white shadow-lg">
                  S
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold truncate">Solstice-1 User</p>
                  <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Local Instance</p>
                </div>
             </div>
          </div>
        </div>
      </motion.aside>

      {/* Main Container */}
      <main className="flex-1 flex flex-col min-w-0 h-full bg-[#020617] overflow-hidden">
        {/* Header */}
        <header className="flex-shrink-0 flex items-center justify-between p-4 md:p-6 bg-[#020617]/80 backdrop-blur-md z-30 border-b border-white/5">
          <div className="flex items-center gap-4">
            <Button 
                variant="ghost" 
                size="icon" 
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="text-slate-400 hover:text-white hover:bg-white/5"
            >
              {sidebarOpen ? <ChevronLeft /> : <ChevronRight />}
            </Button>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-600 rounded-xl shadow-lg shadow-blue-500/20">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold tracking-tight text-white leading-none">DeepAgent</h1>
                <p className="text-[10px] text-blue-400/80 font-bold uppercase tracking-[0.2em] mt-1">{currentSessionId ? "Operation: " + currentSession?.title.slice(0, 15) : "Standby Mode"}</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {currentStatus && (
              <motion.div 
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                className="hidden lg:flex items-center gap-2 px-3 py-1 bg-blue-500/10 border border-blue-500/20 rounded-full text-[10px] font-bold text-blue-400 shadow-sm uppercase tracking-wider"
              >
                <Loader2 className="w-3 h-3 animate-spin" />
                {currentStatus}
              </motion.div>
            )}
            <div className="flex items-center gap-2 text-[10px] font-bold text-slate-400 bg-slate-800/50 px-3 py-1.5 rounded-full border border-slate-700 tracking-widest uppercase">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              Online
            </div>
          </div>
        </header>

        {/* Message Area */}
        <div className="flex-1 min-h-0 relative">
          <ScrollArea className="h-full w-full" type="auto">
            <div className="max-w-4xl mx-auto py-10 px-4 md:px-6 space-y-10">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center min-h-[60vh] text-center space-y-12">
                  <motion.div 
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="p-10 bg-blue-600/5 rounded-[3rem] border border-blue-600/10 relative group"
                  >
                    <Bot className="w-20 h-20 text-blue-500 brightness-125" />
                    <div className="absolute top-4 right-4 bg-green-500 w-6 h-6 rounded-full border-4 border-[#020617] animate-pulse" />
                  </motion.div>
                  <div className="space-y-4">
                    <h2 className="text-4xl md:text-6xl font-black tracking-tighter text-white uppercase italic">Neural<br/><span className="text-blue-500">Processing.</span></h2>
                    <p className="text-slate-400 max-w-lg text-lg leading-relaxed font-medium">
                      The premier intelligence layer for the modern world.
                    </p>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-2xl">
                    {[
                      { text: "Detailed analysis of EV market", icon: Sparkles },
                      { text: "Research current AI trends", icon: History },
                      { text: "Crawl documentation for python", icon: Terminal },
                      { text: "Help me write a deep agent", icon: User }
                    ].map((suggestion) => (
                      <Button 
                        key={suggestion.text}
                        variant="ghost" 
                        onClick={() => setInput(suggestion.text)}
                        className="h-auto py-5 px-6 bg-slate-900 border border-slate-800 hover:bg-slate-800 hover:border-blue-500/50 transition-all rounded-[1.5rem] group justify-start"
                      >
                        <suggestion.icon className="w-5 h-5 mr-3 text-blue-500 group-hover:scale-110 transition-transform" />
                        <span className="font-bold text-slate-300 group-hover:text-white">{suggestion.text}</span>
                      </Button>
                    ))}
                  </div>
                </div>
              )}

              <AnimatePresence mode="popLayout" initial={false}>
                {messages.map((message, index) => (
                  <motion.div
                    key={index}
                    layout
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={cn(
                      "flex gap-4 md:gap-6 w-full",
                      message.role === "user" ? "flex-row-reverse" : "flex-row"
                    )}
                  >
                    <div className={cn(
                      "w-10 h-10 md:w-12 md:h-12 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-2xl border",
                      message.role === "user" ? "bg-blue-600 border-blue-500 text-white" : 
                      message.role === "tool" ? "bg-slate-800 border-slate-700 text-blue-400" :
                      "bg-slate-800 border-slate-700 text-slate-400"
                    )}>
                      {message.role === "user" ? <User className="w-5 h-5 md:w-6 md:h-6" /> : 
                       message.role === "tool" ? <Terminal className="w-5 h-5 md:w-6 md:h-6" /> :
                       <Bot className="w-5 h-5 md:w-6 md:h-6" />}
                    </div>
                    
                    <div className={cn(
                      "max-w-[90%] md:max-w-[80%] rounded-[1.5rem] md:rounded-[2rem] px-6 py-4 md:px-8 md:py-6 shadow-2xl relative overflow-hidden",
                      message.role === "user" 
                        ? "bg-blue-600/90 text-white rounded-tr-none ring-1 ring-blue-500" 
                        : message.role === "tool"
                        ? "bg-[#0a0f1e] border-2 border-slate-800/50 rounded-tl-none font-mono"
                        : "bg-slate-900/50 border border-slate-800/50 backdrop-blur-md rounded-tl-none text-slate-200"
                    )}>
                      {message.role === "tool" && (
                        <div className="flex items-center gap-2 mb-3 text-[10px] uppercase tracking-[0.3em] font-black text-blue-500/80">
                          <Terminal className="w-3 h-3" />
                          Tool Response Data
                        </div>
                      )}
                      
                      <div className={cn(
                        "text-[15px] md:text-base leading-[1.7] break-words",
                        message.role === "assistant" || message.role === "tool" ? "prose prose-invert prose-blue max-w-none prose-pre:bg-black/50 prose-pre:border prose-pre:border-white/5" : "font-semibold"
                      )}>
                        {message.content ? (
                          (() => {
                            const content = typeof message.content === 'string' 
                              ? message.content 
                              : JSON.stringify(message.content, null, 2);
                            
                            return message.role === "tool" && content.length > 500 ? (
                              <details className="cursor-pointer group">
                                <summary className="hover:text-white transition-colors py-2 font-bold text-slate-400 uppercase tracking-widest text-[11px] list-none flex items-center gap-2">
                                  <ChevronRight className="w-3 h-3 group-open:rotate-90 transition-transform" />
                                  Expand Analysis Data ({Math.round(content.length / 1024)} KB)
                                </summary>
                                <div className="mt-4 overflow-x-auto">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                    {content}
                                  </ReactMarkdown>
                                </div>
                              </details>
                            ) : (
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {content}
                              </ReactMarkdown>
                            );
                          })()
                        ) : (isLoading && index === messages.length - 1 && (
                          <div className="flex flex-col gap-6 py-2">
                            <div className="flex items-center gap-4 text-blue-400">
                              <span className="font-black italic uppercase tracking-[0.2em] text-[10px]">{currentStatus || "Synthesizing..."}</span>
                              <div className="flex gap-1.5">
                                <motion.div animate={{ scale: [1, 1.3, 1], opacity: [0.5, 1, 0.5] }} transition={{ repeat: Infinity, duration: 0.8 }} className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
                                <motion.div animate={{ scale: [1, 1.3, 1], opacity: [0.5, 1, 0.5] }} transition={{ repeat: Infinity, duration: 0.8, delay: 0.2 }} className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
                                <motion.div animate={{ scale: [1, 1.3, 1], opacity: [0.5, 1, 0.5] }} transition={{ repeat: Infinity, duration: 0.8, delay: 0.4 }} className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
                              </div>
                            </div>
                            <div className="h-1 w-full max-w-[240px] bg-slate-800 rounded-full overflow-hidden">
                              <motion.div 
                                className="h-full bg-gradient-to-r from-blue-600 to-indigo-600"
                                initial={{ width: "0%" }}
                                animate={{ width: "100%" }}
                                transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>

                      {message.role === "tool" && message.content && message.content.length > 500 && (
                        <div className="mt-4 p-4 bg-black/40 rounded-xl border border-white/5 text-[11px] text-slate-500 font-bold uppercase tracking-widest text-center">
                          Analysis Complete ({Math.round(message.content.length / 1024)} KB)
                        </div>
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
              <div ref={messagesEndRef} className="h-10" />
            </div>
          </ScrollArea>
        </div>

        {/* Input Area */}
        <div className="flex-shrink-0 p-6 md:p-8 bg-gradient-to-t from-[#020617] via-[#020617] to-transparent">
          <div className="max-w-4xl mx-auto flex flex-col gap-4">
              <form 
                onSubmit={handleSubmit}
                className="relative flex items-end gap-2"
              >
                  <div className="relative flex-1 group">
                    <div className="absolute -inset-1 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-[2rem] blur opacity-10 group-focus-within:opacity-30 transition duration-500"></div>
                    <Input
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      placeholder={isLoading ? "Neural network active..." : "Initiate objective..."}
                      className="w-full pr-16 py-8 bg-slate-900/95 border-2 border-white/5 focus-visible:ring-0 focus-visible:border-blue-500/30 h-16 text-lg rounded-[2rem] shadow-2xl placeholder:text-slate-700 text-white transition-all caret-blue-500 relative"
                      disabled={isLoading}
                    />
                    <Button 
                      type="submit" 
                      size="icon" 
                      disabled={isLoading || !input.trim()}
                      className="absolute right-3 top-3 h-10 w-10 rounded-2xl bg-blue-600 hover:bg-blue-500 hover:scale-105 active:scale-95 transition-all shadow-xl disabled:bg-slate-800/50 disabled:text-slate-700"
                    >
                      {isLoading ? (
                        <Loader2 className="h-5 w-5 animate-spin" />
                      ) : (
                        <Send className="h-5 w-5" />
                      )}
                    </Button>
                  </div>
              </form>
              
              <div className="flex flex-wrap justify-center gap-6 text-[9px] font-black text-slate-600 uppercase tracking-[0.3em]">
                <div className="flex items-center gap-2 px-3 py-1 bg-white/5 rounded-full border border-white/5">
                  <Terminal className="w-3 h-3 text-blue-500" />
                  Quantum Protocol
                </div>
                <div className="flex items-center gap-2 px-3 py-1 bg-white/5 rounded-full border border-white/5">
                  <Sparkles className="w-3 h-3 text-blue-500" />
                  Neural Research
                </div>
                <div className="flex items-center gap-2 px-3 py-1 bg-white/5 rounded-full border border-white/5">
                   <History className="w-3 h-3 text-blue-500" />
                   Synaptic Memory
                </div>
              </div>
          </div>
        </div>
      </main>
    </div>
  );
}
