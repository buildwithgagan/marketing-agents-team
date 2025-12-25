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
                
                if (data.type === "thought") {
                  if (!accumulatedContent.includes("> **Thinking**")) {
                    accumulatedContent += "\n\n> **Thinking**\n> ";
                  }
                  accumulatedContent += data.content.replaceAll("\n", "\n> ");
                  yield {
                    content: [{ type: "text", text: accumulatedContent }],
                  };
                } else if (data.type === "content") {
                  accumulatedContent += data.content;
                  yield {
                    content: [{ type: "text", text: accumulatedContent }],
                  };
                } else if (data.type === "status") {
                  accumulatedContent += `\n\n> **Status:** ${data.content}`;
                  yield {
                    content: [{ type: "text", text: accumulatedContent }],
                  };
                } else if (data.type === "tool_start") {
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
