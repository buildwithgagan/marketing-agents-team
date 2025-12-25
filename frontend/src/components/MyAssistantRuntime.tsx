"use client";

import { AssistantRuntimeProvider, useLocalRuntime, type ChatModelAdapter } from "@assistant-ui/react";
import { useMemo, useEffect, useState } from "react";

export function MyAssistantRuntimeProvider({ 
  children,
  model = "gpt-4.1-mini",
  thinking = false,
  threadId
}: { 
  children: React.ReactNode;
  model?: string;
  thinking?: boolean;
  threadId?: string;
}) {
  const [storedMessages, setStoredMessages] = useState<any[] | null>(null);
  
  // Load messages on mount (or when threadId changes via key)
  useEffect(() => {
    const tid = threadId || "default-thread";
    const saved = localStorage.getItem(`assistant_messages_${tid}`);
    if (saved) {
       try {
         setStoredMessages(JSON.parse(saved));
       } catch (e) { 
         console.error(e); 
         setStoredMessages([]); 
       }
    } else {
       setStoredMessages([]);
    }
  }, [threadId]);

  if (storedMessages === null) {
      return null; 
  }

  return (
    <InnerRuntimeProvider 
      model={model} 
      thinking={thinking} 
      threadId={threadId || "default-thread"}
      initialMessages={storedMessages}
    >
      {children}
    </InnerRuntimeProvider>
  );
}

function InnerRuntimeProvider({
  children,
  model,
  thinking,
  threadId,
  initialMessages
}: {
  children: React.ReactNode;
  model: string;
  thinking: boolean;
  threadId: string;
  initialMessages: any[];
}) {
  const MyModelAdapter: ChatModelAdapter = useMemo(() => ({
    async *run({ messages, abortSignal }) {
      try {
        // Get mode from sessionStorage
        const mode = sessionStorage.getItem("assistant_mode") || null;
        
        const response = await fetch("http://localhost:8000/api/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            messages: messages.map(m => ({
              role: m.role,
              content: m.content.map(c => {
                if (c.type === "text") return c.text;
                return "";
              }).join("\n"),
            })),
            thread_id: threadId,
            model,
            thinking,
            mode, // Add mode to the request
          }),
          signal: abortSignal,
        });

        if (!response.ok || !response.body) {
          throw new Error("Failed to fetch from backend");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let accumulatedContent = "";
        let statusLine = ""; // Track current status separately
        let buffer = "";
        let pendingYield = false;
        let lastYieldTime = 0;
        const MIN_YIELD_INTERVAL = 16; // ~60fps for smooth streaming without browser hang

        // Helper to throttle yields
        const shouldYield = () => {
          const now = Date.now();
          if (now - lastYieldTime >= MIN_YIELD_INTERVAL) {
            lastYieldTime = now;
            return true;
          }
          pendingYield = true;
          return false;
        };

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            // Decode and process immediately for smooth streaming
            buffer += decoder.decode(value, { stream: true });
            
            // Split on newlines - each complete line is a JSON event
            const lines = buffer.split("\n");
            // Keep incomplete line in buffer
            buffer = lines.pop() || "";

            let contentUpdated = false;
            
            for (const line of lines) {
              if (!line.trim()) continue;
              try {
                const data = JSON.parse(line);
                
                if (data.type === "thought") {
                  if (!accumulatedContent.includes("> **Thinking**")) {
                    accumulatedContent += "\n\n> **Thinking**\n> ";
                  }
                  accumulatedContent += data.content.replaceAll("\n", "\n> ");
                  contentUpdated = true;
                } else if (data.type === "content") {
                  const content = data.content;
                  if (content) {
                    // Only filter if the ENTIRE content looks like JSON (not just a bracket in text)
                    const trimmed = content.trim();
                    const looksLikeJson = (trimmed.startsWith('{"') && trimmed.endsWith('}')) || 
                                          (trimmed.startsWith('[{') && trimmed.endsWith(']'));
                    if (!looksLikeJson) {
                      accumulatedContent += content;
                      contentUpdated = true;
                    }
                  }
                } else if (data.type === "status") {
                  // Show status as a temporary indicator, don't accumulate
                  statusLine = data.content;
                  // Always yield status updates immediately
                  yield {
                    content: [{ type: "text", text: accumulatedContent + `\n\n---\n*${statusLine}*` }],
                  };
                  lastYieldTime = Date.now();
                } else if (data.type === "tool_start") {
                  // Show tool activity as temporary status
                  const toolName = data.tool_name || data.tool || "tool";
                  statusLine = `🔍 Running ${toolName}...`;
                  yield {
                    content: [{ type: "text", text: accumulatedContent + `\n\n---\n*${statusLine}*` }],
                  };
                  lastYieldTime = Date.now();
                } else if (data.type === "plan_delta") {
                  // Brew mode incremental task plan streaming
                  if (!accumulatedContent.includes("### 🎯 Task Plan")) {
                    accumulatedContent += `\n\n### 🎯 Task Plan\n`;
                    if (data.reasoning) {
                      accumulatedContent += `\n> ${data.reasoning}\n`;
                    }
                  }
                  const emoji: Record<string, string> = {
                    research: "🔍",
                    content: "✍️",
                    analytics: "📊",
                    social: "📱",
                    general: "💬",
                  };
                  const worker = data.worker || "worker";
                  const task = data.task || "";
                  accumulatedContent += `\n- ${emoji[worker] || "📋"} **${worker}**: ${task}`;
                  // Yield immediately so the plan visibly grows line-by-line
                  yield {
                    content: [{ type: "text", text: accumulatedContent }],
                  };
                  lastYieldTime = Date.now();
                } else if (data.type === "plan") {
                  // Handle brew mode task plans
                  let planText = "";
                  if (Array.isArray(data.content)) {
                    planText = data.content.map((item: any) => {
                      // Brew mode format: { worker, task, priority }
                      if (item.worker && item.task) {
                        const emoji: Record<string, string> = {
                          research: "🔍",
                          content: "✍️",
                          analytics: "📊",
                          social: "📱"
                        };
                        return `- ${emoji[item.worker] || "📋"} **${item.worker}**: ${item.task}`;
                      }
                      // Legacy format
                      return `- ${item.task || item}`;
                    }).join("\n");
                  } else {
                    planText = String(data.content);
                  }
                  const reasoning = data.reasoning ? `\n> ${data.reasoning}\n` : "";
                  accumulatedContent += `\n\n### 🎯 Task Plan\n${reasoning}\n${planText}`;
                  // Always yield plan immediately
                  yield {
                    content: [{ type: "text", text: accumulatedContent }],
                  };
                  lastYieldTime = Date.now();
                } else if (data.type === "worker_start") {
                  // Brew mode worker start - show as status
                  const emoji: Record<string, string> = {
                    research: "🔍",
                    content: "✍️",
                    analytics: "📊",
                    social: "📱",
                    general: "💬",
                  };
                  const worker = data.worker || "worker";
                  statusLine = `${emoji[worker] || "⏳"} ${worker} working...`;
                  yield {
                    content: [{ type: "text", text: accumulatedContent + `\n\n---\n*${statusLine}*` }],
                  };
                  lastYieldTime = Date.now();
                } else if (data.type === "worker_complete") {
                  // Brew mode worker completion - show as status
                  const emoji: Record<string, string> = {
                    research: "🔍",
                    content: "✍️",
                    analytics: "📊",
                    social: "📱",
                    general: "💬",
                  };
                  statusLine = `${emoji[data.worker] || "✅"} ${data.worker} completed`;
                  yield {
                    content: [{ type: "text", text: accumulatedContent + `\n\n---\n*${statusLine}*` }],
                  };
                  lastYieldTime = Date.now();
                } else if (data.type === "tool_result") {
                  // Optionally show tool results briefly
                  // Skip for cleaner output
                }
              } catch (e) {
                console.error("Error parsing NDJSON chunk", e);
              }
            }

            // Throttled yield for content updates (prevents browser hang)
            if (contentUpdated && shouldYield()) {
              yield {
                content: [{ type: "text", text: accumulatedContent }],
              };
            }
          }
          
          // Final yield for any pending content
          if (pendingYield || accumulatedContent) {
            yield {
              content: [{ type: "text", text: accumulatedContent }],
            };
          }
        } finally {
          reader.releaseLock();
        }
      } catch (error: any) {
        if (error.name === 'AbortError') {
          return;
        }
        throw error;
      }
    },
  }), [threadId, model, thinking]);

  const runtime = useLocalRuntime(MyModelAdapter, {
    initialMessages,
  });

  // Sync state changes to local storage and update thread metadata
  useEffect(() => {
    return runtime.thread.subscribe(() => {
      const state = runtime.thread.getState();
      if (state.messages.length > 0) {
        localStorage.setItem(`assistant_messages_${threadId}`, JSON.stringify(state.messages));
        
        // Update thread list metadata
        const savedThreads = localStorage.getItem("assistant_threads") || "[]";
        let threadsContent = [];
        try {
           threadsContent = JSON.parse(savedThreads);
        } catch { threadsContent = []; }
        
        const firstUserMessage = state.messages.find(m => m.role === "user");
        const autoTitle = firstUserMessage?.content[0]?.type === "text" 
          ? firstUserMessage.content[0].text.slice(0, 30) 
          : "New Chat";
            
        const threadIndex = threadsContent.findIndex((t: any) => t.id === threadId);
        if (threadIndex > -1) {
          // Only update title if it hasn't been manually edited
          const existingThread = threadsContent[threadIndex];
          const newTitle = existingThread.titleEdited ? existingThread.title : autoTitle;
          threadsContent[threadIndex] = { ...existingThread, title: newTitle, updatedAt: Date.now() };
        } else {
          threadsContent.unshift({ id: threadId, title: autoTitle, updatedAt: Date.now() }); // Push to top
        }
        localStorage.setItem("assistant_threads", JSON.stringify(threadsContent));
        window.dispatchEvent(new Event("assistant-threads-updated"));
      }
    });
  }, [runtime, threadId]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
