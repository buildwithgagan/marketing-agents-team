"use client";

import { Button } from "@/components/ui/button";
import { PlusIcon, Trash2, MessageSquare, MoreHorizontal, Pencil, Copy, Share } from "lucide-react";
import { useEffect, useState, type FC, useRef } from "react";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";

export const CustomThreadList: FC<{ isOpen?: boolean }> = ({ isOpen = true }) => {
  const [threads, setThreads] = useState<any[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string>("");
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const loadThreads = () => {
    try {
      const saved = localStorage.getItem("assistant_threads");
      const current = localStorage.getItem("assistant_current_thread_id");
      if (saved) {
        setThreads(JSON.parse(saved));
      } else {
        setThreads([]);
      }
      if (current) setActiveThreadId(current);
    } catch (e) {
      console.error(e);
      setThreads([]);
    }
  };

  useEffect(() => {
    loadThreads();
    const handleUpdate = () => loadThreads();
    window.addEventListener("assistant-threads-updated", handleUpdate);
    window.addEventListener("assistant-change-thread", (e: Event) => {
       const ce = e as CustomEvent;
       if (ce.detail?.threadId) setActiveThreadId(ce.detail.threadId);
    });
    return () => {
       window.removeEventListener("assistant-threads-updated", handleUpdate);
    };
  }, []);

  useEffect(() => {
    if (editingThreadId && inputRef.current) {
      inputRef.current.focus();
    }
  }, [editingThreadId]);

  const handleSelect = (threadId: string) => {
    if (editingThreadId) return; 
    setActiveThreadId(threadId); 
    window.dispatchEvent(
      new CustomEvent("assistant-change-thread", { detail: { threadId } })
    );
  };

  const handleNew = () => {
    const newId = `thread_${Date.now()}`;
    handleSelect(newId);
  };

  // Open the custom delete dialog
  const requestDelete = (e: React.MouseEvent, threadId: string) => {
    e.stopPropagation();
    setDeletingThreadId(threadId);
  };

  const confirmDelete = () => {
    if (!deletingThreadId) return;
    
    const newThreads = threads.filter((t) => t.id !== deletingThreadId);
    localStorage.setItem("assistant_threads", JSON.stringify(newThreads));
    localStorage.removeItem(`assistant_messages_${deletingThreadId}`);
    setThreads(newThreads);
    
    if (activeThreadId === deletingThreadId) {
        if (newThreads.length > 0) {
          handleSelect(newThreads[0].id);
        } else {
          handleNew();
        }
    }
    window.dispatchEvent(new Event("assistant-threads-updated"));
    setDeletingThreadId(null);
  };

  const startEditing = (e: React.MouseEvent, thread: any) => {
    e.stopPropagation();
    setEditingThreadId(thread.id);
    setEditTitle(thread.title || "New Chat");
  };

  const saveTitle = () => {
    if (!editingThreadId) return;
    const newThreads = threads.map(t => {
      if (t.id === editingThreadId) {
        return { ...t, title: editTitle, titleEdited: true };
      }
      return t;
    });
    setThreads(newThreads);
    localStorage.setItem("assistant_threads", JSON.stringify(newThreads));
    setEditingThreadId(null);
    window.dispatchEvent(new Event("assistant-threads-updated"));
  };

  const handleCopy = (e: React.MouseEvent, threadId: string) => {
    e.stopPropagation();
    const threadToCopy = threads.find(t => t.id === threadId);
    if (!threadToCopy) return;

    const newId = `thread_${Date.now()}`;
    const newTitle = `Copy of ${threadToCopy.title || "New Chat"}`;
    
    // Copy messages
    try {
      const sourceMessages = localStorage.getItem(`assistant_messages_${threadId}`);
      if (sourceMessages) {
        localStorage.setItem(`assistant_messages_${newId}`, sourceMessages);
      }
    } catch (err) {
      console.error("Failed to copy messages", err);
    }

    // Add to threads list
    const newThread = { ...threadToCopy, id: newId, title: newTitle, updatedAt: Date.now() };
    const newThreads = [newThread, ...threads];
    
    setThreads(newThreads);
    localStorage.setItem("assistant_threads", JSON.stringify(newThreads));
    
    // Switch to new copy
    handleSelect(newId);
    window.dispatchEvent(new Event("assistant-threads-updated"));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      saveTitle();
    } else if (e.key === "Escape") {
      setEditingThreadId(null);
    }
  };

  return (
    <>
      <div className="flex flex-col gap-2 p-2">
        <Button
          variant="outline"
          className={cn(
            "justify-start gap-2 rounded-lg text-sm transition-all",
             isOpen ? "px-3 w-full" : "px-0 w-8 justify-center"
          )}
          onClick={handleNew}
          title="New Thread"
        >
          <PlusIcon className="size-4" />
          {isOpen && "New Thread"}
        </Button>

        <div className="flex flex-col gap-1 mt-2">
          {threads.length === 0 && isOpen && (
             <div className="text-xs text-muted-foreground px-3 py-2">No history</div>
          )}
          {threads.map((thread) => {
            const isActive = thread.id === activeThreadId;
            const isEditing = editingThreadId === thread.id;

            return (
            <div
              key={thread.id}
              onClick={() => handleSelect(thread.id)}
              className={cn(
                 "group flex items-center justify-between rounded-lg px-2 py-2 text-sm font-medium transition-colors cursor-pointer h-9",
                 isActive ? "bg-accent text-accent-foreground" : "hover:bg-muted",
                 !isOpen && "justify-center px-0"
              )}
              title={thread.title || "New Chat"}
            >
              <div className={cn("flex items-center gap-2 truncate", isOpen ? "flex-1" : "justify-center w-full")}>
                <MessageSquare className="size-4 opacity-70 flex-shrink-0" />
                {isOpen && (
                  isEditing ? (
                    <input
                      ref={inputRef}
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onBlur={saveTitle}
                      onKeyDown={handleKeyDown}
                      className="flex-1 bg-transparent outline-none min-w-0"
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <span className="truncate">{thread.title || "New Chat"}</span>
                  )
                )}
              </div>
              
              {isOpen && !isEditing && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button 
                      className="p-1 rounded-sm opacity-0 group-hover:opacity-100 hover:bg-background/50 transition-all focus:opacity-100 data-[state=open]:opacity-100"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreHorizontal className="size-4 text-muted-foreground" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-40">
                    <DropdownMenuItem onClick={(e) => startEditing(e, thread)}>
                      <Pencil className="mr-2 size-3.5" />
                      Rename
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={(e) => handleCopy(e, thread.id)}>
                      <Copy className="mr-2 size-3.5" />
                      Make a copy
                    </DropdownMenuItem>
                    <DropdownMenuItem 
                      onClick={(e) => requestDelete(e, thread.id)}
                      className="text-destructive focus:text-destructive"
                    >
                      <Trash2 className="mr-2 size-3.5" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          );
          })}
        </div>
      </div>

      <Dialog open={!!deletingThreadId} onOpenChange={(open) => !open && setDeletingThreadId(null)}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Delete Thread</DialogTitle>
            <DialogDescription>
              Are you sure?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex gap-2 sm:justify-end">
            <DialogClose asChild>
              <Button variant="outline" size="sm" onClick={() => setDeletingThreadId(null)}>
                Cancel
              </Button>
            </DialogClose>
            <Button variant="default" size="sm" onClick={confirmDelete} className="bg-primary text-primary-foreground hover:bg-primary/90">
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};
