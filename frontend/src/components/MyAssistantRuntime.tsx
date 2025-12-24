"use client";

import { AssistantRuntimeProvider, useLocalRuntime, type ChatModelAdapter } from "@assistant-ui/react";
import { useMemo, useEffect, useState, useCallback } from "react";

export function MyAssistantRuntimeProvider({ 
  children,
  model = "gpt-4.1",
  thinking = false
}: { 
  children: React.ReactNode;
  model?: string;
  thinking?: boolean;
}) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [currentThreadId, setCurrentThreadId] = useState<string>("default-thread");

  const loadThreads = useCallback(() => {
    const savedId = localStorage.getItem("assistant_current_thread_id");
    if (savedId) {
      setCurrentThreadId(savedId);
    }
  }, []);

  useEffect(() => {
    loadThreads();
    setIsLoaded(true);
  }, [loadThreads]);

  const MyModelAdapter: ChatModelAdapter = useMemo(() => ({
    async *run({ messages, abortSignal }) {
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
          thread_id: currentThreadId,
          model,
          thinking,
        }),
        signal: abortSignal,
      });

      if (!response.ok || !response.body) {
        throw new Error("Failed to fetch from backend");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulatedContent = "";
      let buffer = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const data = JSON.parse(line);
              
              if (data.type === "content") {
                accumulatedContent += data.content;
                yield {
                  content: [{ type: "text", text: accumulatedContent }],
                };
              } else if (data.type === "status") {
                // Persistent status
                accumulatedContent += `\n\n> **Status:** ${data.content}`;
                yield {
                  content: [{ type: "text", text: accumulatedContent }],
                };
              } else if (data.type === "tool_start") {
                // Persistent tool start
                accumulatedContent += `\n\n> 🔍 **Running ${data.tool_name || data.tool || "tool"}**...`;
                yield {
                  content: [{ type: "text", text: accumulatedContent }],
                };
              } else if (data.type === "plan") {
                const planText = Array.isArray(data.content) 
                  ? data.content.map((todo: any) => `- ${todo.task || todo}`).join("\n")
                  : String(data.content);
                accumulatedContent += `\n\n### Execution Plan:\n${planText}`;
                yield {
                  content: [{ type: "text", text: accumulatedContent }],
                };
              }
            } catch (e) {
              console.error("Error parsing NDJSON chunk", e);
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    },
  }), [currentThreadId, model, thinking]);

  const initialMessages = useMemo(() => {
    if (!isLoaded) return [];
    const saved = localStorage.getItem(`assistant_messages_${currentThreadId}`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) {
        console.error("Failed to parse saved messages", e);
      }
    }
    return [];
  }, [currentThreadId, isLoaded]);

  const runtime = useLocalRuntime(MyModelAdapter, {
    initialMessages,
  });

  // Sync state changes to local storage
  useEffect(() => {
    if (!isLoaded) return;
    
    return runtime.thread.subscribe(() => {
      const state = runtime.thread.getState();
      if (state.messages.length > 0) {
        localStorage.setItem(`assistant_messages_${currentThreadId}`, JSON.stringify(state.messages));
        
        // Update thread list metadata
        const savedThreads = localStorage.getItem("assistant_threads") || "[]";
        let threadsContent = JSON.parse(savedThreads);
        
        const firstUserMessage = state.messages.find(m => m.role === "user");
        const title = firstUserMessage?.content[0]?.type === "text" 
          ? firstUserMessage.content[0].text.slice(0, 30) 
          : "New Chat";
            
        const threadIndex = threadsContent.findIndex((t: any) => t.id === currentThreadId);
        if (threadIndex > -1) {
          threadsContent[threadIndex] = { ...threadsContent[threadIndex], title, updatedAt: Date.now() };
        } else {
          threadsContent.push({ id: currentThreadId, title, updatedAt: Date.now() });
        }
        localStorage.setItem("assistant_threads", JSON.stringify(threadsContent));
        window.dispatchEvent(new Event("assistant-threads-updated"));
      }
    });
  }, [runtime, isLoaded, currentThreadId]);

  if (!isLoaded) return null;

  return (
    <AssistantRuntimeProvider runtime={runtime} key={currentThreadId}>
      {children}
    </AssistantRuntimeProvider>
  );
}
