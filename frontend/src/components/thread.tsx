import {
  ComposerAttachments,
  UserMessageAttachments,
} from "@/components/attachment";
import { MarkdownText } from "@/components/markdown-text";
import { PerplexityMessage } from "@/components/perplexity-message";
import { ToolFallback } from "@/components/tool-fallback";
import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ActionBarPrimitive,
  AssistantIf,
  useMessage,
  BranchPickerPrimitive,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CopyIcon,
  DownloadIcon,
  PencilIcon,
  RefreshCwIcon,
  SquareIcon,
  UserIcon,
  SparklesIcon,
  ChevronDownIcon,
  Search,
  Coffee,
} from "lucide-react";
import type { FC, MouseEvent } from "react";
import { type Mode } from "@/components/mode-selector";
import { useState, useEffect, useMemo } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export const Thread: FC = () => {
  return (
    <ThreadPrimitive.Root
      className="aui-root aui-thread-root @container flex h-full flex-col bg-background"
      style={{
        ["--thread-max-width" as string]: "44rem",
      }}
    >
      <ThreadPrimitive.Viewport
        turnAnchor="top"
        className="aui-thread-viewport relative flex flex-1 flex-col overflow-x-auto overflow-y-scroll scroll-smooth px-2 sm:px-4 pt-2 sm:pt-4"
      >
        <AssistantIf condition={({ thread }) => thread.isEmpty}>
          <ThreadWelcome />
        </AssistantIf>

        <ThreadPrimitive.Messages
          components={{
            UserMessage,
            EditComposer,
            AssistantMessage,
          }}
        />

        <ThreadPrimitive.ViewportFooter className="aui-thread-viewport-footer sticky bottom-0 mx-auto mt-auto flex w-full max-w-(--thread-max-width) flex-col gap-2 sm:gap-4 overflow-visible rounded-t-2xl sm:rounded-t-3xl bg-background pb-2 sm:pb-4 md:pb-6 px-2 sm:px-0">
          <ThreadScrollToBottom />
          <Composer />
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
};

const ThreadScrollToBottom: FC = () => {
  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <TooltipIconButton
        tooltip="Scroll to bottom"
        variant="outline"
        className="aui-thread-scroll-to-bottom absolute -top-12 z-10 self-center rounded-full p-4 disabled:invisible dark:bg-background dark:hover:bg-accent"
      >
        <ArrowDownIcon />
      </TooltipIconButton>
    </ThreadPrimitive.ScrollToBottom>
  );
};

const ThreadWelcome: FC = () => {
  return (
    <div className="aui-thread-welcome-root mx-auto my-auto flex w-full max-w-(--thread-max-width) grow flex-col">
      <div className="aui-thread-welcome-center flex w-full grow flex-col items-center justify-center">
        <div className="aui-thread-welcome-message flex size-full flex-col justify-center px-4">
          <h1 className="aui-thread-welcome-message-inner fade-in slide-in-from-bottom-1 animate-in font-semibold text-xl sm:text-2xl duration-200">
            Hello there!
          </h1>
          <p className="aui-thread-welcome-message-inner fade-in slide-in-from-bottom-1 animate-in text-muted-foreground text-base sm:text-xl delay-75 duration-200">
            How can I help you today?
          </p>
        </div>
      </div>
      <ThreadSuggestions />
    </div>
  );
};

const SUGGESTIONS = [
  {
    title: "What's the weather",
    label: "in San Francisco?",
    prompt: "What's the weather in San Francisco?",
  },
  {
    title: "Explain React hooks",
    label: "like useState and useEffect",
    prompt: "Explain React hooks like useState and useEffect",
  },
] as const;

const ThreadSuggestions: FC = () => {
  // Only show suggestions if mode is selected
  const [selectedMode, setSelectedMode] = useState<Mode>(() => {
    if (typeof window !== "undefined") {
      return (sessionStorage.getItem("assistant_mode") as Mode) || null;
    }
    return null;
  });

  useEffect(() => {
    const handleModeChange = () => {
      if (typeof window !== "undefined") {
        const mode = sessionStorage.getItem("assistant_mode") as Mode;
        setSelectedMode(mode);
      }
    };

    // Listen for mode changes via custom event
    window.addEventListener("assistant-mode-changed", handleModeChange);
    return () =>
      window.removeEventListener("assistant-mode-changed", handleModeChange);
  }, []);

  if (!selectedMode) {
    return null;
  }

  return (
    <div className="aui-thread-welcome-suggestions grid w-full grid-cols-1 sm:grid-cols-2 gap-2 pb-2 sm:pb-4">
      {SUGGESTIONS.map((suggestion, index) => (
        <div
          key={suggestion.prompt}
          className="aui-thread-welcome-suggestion-display fade-in slide-in-from-bottom-2 @md:nth-[n+3]:block nth-[n+3]:hidden animate-in fill-mode-both duration-200"
          style={{ animationDelay: `${100 + index * 50}ms` }}
        >
          <ThreadPrimitive.Suggestion prompt={suggestion.prompt} send asChild>
            <Button
              variant="ghost"
              className="aui-thread-welcome-suggestion h-auto w-full @md:flex-col flex-wrap items-start justify-start gap-1 rounded-2xl border px-4 py-3 text-left text-sm transition-colors hover:bg-muted"
              aria-label={suggestion.prompt}
            >
              <span className="aui-thread-welcome-suggestion-text-1 font-medium">
                {suggestion.title}
              </span>
              <span className="aui-thread-welcome-suggestion-text-2 text-muted-foreground">
                {suggestion.label}
              </span>
            </Button>
          </ThreadPrimitive.Suggestion>
        </div>
      ))}
    </div>
  );
};

const Composer: FC = () => {
  const [selectedMode, setSelectedMode] = useState<Mode>(() => {
    // Default to null (no mode selected) - Brew Mode
    if (typeof window !== "undefined") {
      return (sessionStorage.getItem("assistant_mode") as Mode) || null;
    }
    return null;
  });

  useEffect(() => {
    // Store mode in sessionStorage
    if (selectedMode) {
      sessionStorage.setItem("assistant_mode", selectedMode);
    } else {
      sessionStorage.removeItem("assistant_mode");
    }
    // Dispatch event for other components
    window.dispatchEvent(new Event("assistant-mode-changed"));
  }, [selectedMode]);

  const modes = [
    {
      id: "investigator" as const,
      label: "Investigator",
      description: "Deep research with human-in-the-loop",
      icon: Search,
    },
  ];

  const currentMode = modes.find((m) => m.id === selectedMode);
  // Default to Brew Mode icon (coffee cup or similar) when no mode selected
  const ModeIcon = currentMode?.icon || Coffee;
  const placeholder =
    selectedMode === "investigator"
      ? "Enter research topic..."
      : "Brew anything...";

  return (
    <ComposerPrimitive.Root className="aui-composer-root relative flex w-full flex-col">
      <ComposerPrimitive.AttachmentDropzone className="aui-composer-attachment-dropzone flex w-full flex-col rounded-xl sm:rounded-2xl border border-border bg-card dark:bg-card/50 shadow-sm dark:shadow-md px-0 pt-2 sm:pt-3 pb-2 sm:pb-3 outline-none transition-shadow has-[textarea:focus-visible]:border-ring has-[textarea:focus-visible]:ring-2 has-[textarea:focus-visible]:ring-ring/20 data-[dragging=true]:border-ring data-[dragging=true]:border-dashed data-[dragging=true]:bg-accent/50">
        <ComposerAttachments />
        <div className="px-2 sm:px-3.5 grid grid-cols-[auto_1fr_auto] items-center gap-x-1.5 sm:gap-x-2 gap-y-2">
          <div className="row-start-2 flex items-center">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className={cn(
                    "reset interactable select-none outline-none font-semibold duration-300 ease-out font-sans text-center items-center justify-center leading-loose whitespace-nowrap data-[state=open]:text-foreground data-[state=open]:bg-subtle text-muted-foreground h-8 text-sm cursor-pointer origin-center active:scale-[0.97] active:duration-150 active:ease-outExpo inline-flex hover:text-foreground hover:bg-subtle rounded-lg px-2 gap-1.5",
                    selectedMode === "investigator" &&
                      "text-primary bg-primary/10 hover:bg-primary/20"
                  )}
                >
                  {selectedMode === "investigator" ? (
                    <SparklesIcon className="size-4" />
                  ) : (
                    <Coffee className="size-4" />
                  )}
                  <span className="font-medium hidden sm:inline">
                    {selectedMode === "investigator" ? "Investigator" : "Brew"}
                  </span>
                  <ChevronDownIcon className="size-3.5 opacity-70" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" side="top" className="w-48">
                <DropdownMenuItem
                  onClick={() => setSelectedMode(null)}
                  className="flex items-center gap-2 cursor-pointer"
                >
                  <Coffee className="size-4 text-foreground" />
                  <div className="flex flex-col">
                    <span className="font-medium text-foreground">Brew</span>
                    <span className="text-xs text-muted-foreground">
                      Default mode
                    </span>
                  </div>
                </DropdownMenuItem>
                {modes.map((mode) => {
                  const Icon = mode.icon;
                  return (
                    <DropdownMenuItem
                      key={mode.id}
                      onClick={() => setSelectedMode(mode.id)}
                      className="flex items-center gap-2 cursor-pointer"
                    >
                      <Icon className="size-4 text-foreground" />
                      <div className="flex flex-col">
                        <span className="font-medium text-foreground">
                          {mode.label}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {mode.description}
                        </span>
                      </div>
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <ComposerPrimitive.Input
            placeholder={placeholder}
            className="aui-composer-input col-span-3 row-start-1 mb-1 max-h-32 min-h-12 sm:min-h-14 w-full resize-none bg-transparent px-3 sm:px-4 pt-2 pb-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-0"
            rows={1}
            autoFocus
            aria-label="Message input"
          />
          <div className="col-start-3 row-start-2 flex items-center justify-end">
            <ComposerAction />
          </div>
        </div>
      </ComposerPrimitive.AttachmentDropzone>
    </ComposerPrimitive.Root>
  );
};

const ComposerAction: FC = () => {
  return (
    <div className="aui-composer-action-wrapper relative flex items-center">
      <AssistantIf condition={({ thread }) => !thread.isRunning}>
        <ComposerPrimitive.Send asChild>
          <TooltipIconButton
            tooltip="Send message"
            side="bottom"
            type="submit"
            variant="default"
            size="icon"
            className="aui-composer-send size-8 rounded-lg"
            aria-label="Send message"
          >
            <ArrowUpIcon className="aui-composer-send-icon size-4" />
          </TooltipIconButton>
        </ComposerPrimitive.Send>
      </AssistantIf>

      <AssistantIf condition={({ thread }) => thread.isRunning}>
        <ComposerPrimitive.Cancel asChild>
          <Button
            type="button"
            variant="default"
            size="icon"
            className="aui-composer-cancel size-8 rounded-lg"
            aria-label="Stop generating"
          >
            <SquareIcon className="aui-composer-cancel-icon size-3 fill-current" />
          </Button>
        </ComposerPrimitive.Cancel>
      </AssistantIf>
    </div>
  );
};

const MessageError: FC = () => {
  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root className="aui-message-error-root mt-2 rounded-md border border-destructive bg-destructive/10 p-3 text-destructive text-sm dark:bg-destructive/5 dark:text-red-200">
        <ErrorPrimitive.Message className="aui-message-error-message line-clamp-2" />
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};

const AssistantMessage: FC = () => {
  const messageContent = useMessage((m: any) => m.content);
  const textContent = useMemo(() => {
    if (!messageContent) return "";
    return messageContent
      .map((part: any) => (part.type === "text" ? part.text : ""))
      .join("")
      .trim();
  }, [messageContent]);

  const isInvestigatorPlan =
    textContent.includes("Research Plan Generated") ||
    textContent.includes("Next Steps");

  return (
    <MessagePrimitive.Root
      className="aui-assistant-message-root fade-in slide-in-from-bottom-1 relative mx-auto w-full max-w-(--thread-max-width) animate-in py-3 sm:py-4 duration-150 flex gap-2 sm:gap-4"
      data-role="assistant"
    >
      <div className="shrink-0 size-8 rounded-full bg-primary/10 flex items-center justify-center text-primary mt-1">
        <SparklesIcon className="size-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="aui-assistant-message-content wrap-break-word text-foreground leading-relaxed">
          <MessagePrimitive.Parts
            components={{
              Text: PerplexityMessage,
              tools: { Fallback: ToolFallback },
            }}
          />
          {isInvestigatorPlan && <PlanActionButtons />}
          <MessageError />
        </div>

        <div className="aui-assistant-message-footer mt-2 flex">
          <BranchPicker />
          <AssistantActionBar />
        </div>
      </div>
    </MessagePrimitive.Root>
  );
};

const AssistantActionBar: FC = () => {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      autohideFloat="single-branch"
      className="aui-assistant-action-bar-root col-start-3 row-start-2 -ml-1 flex gap-1 text-muted-foreground data-floating:absolute data-floating:rounded-md data-floating:border data-floating:bg-background data-floating:p-1 data-floating:shadow-sm"
    >
      <ActionBarPrimitive.Copy asChild>
        <TooltipIconButton tooltip="Copy">
          <AssistantIf condition={({ message }) => message.isCopied}>
            <CheckIcon />
          </AssistantIf>
          <AssistantIf condition={({ message }) => !message.isCopied}>
            <CopyIcon />
          </AssistantIf>
        </TooltipIconButton>
      </ActionBarPrimitive.Copy>
      <ActionBarPrimitive.ExportMarkdown asChild>
        <TooltipIconButton tooltip="Export as Markdown">
          <DownloadIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.ExportMarkdown>
      <ActionBarPrimitive.Reload asChild>
        <TooltipIconButton tooltip="Refresh">
          <RefreshCwIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.Reload>
    </ActionBarPrimitive.Root>
  );
};

const UserMessage: FC = () => {
  return (
    <MessagePrimitive.Root
      className="aui-user-message-root fade-in slide-in-from-bottom-1 mx-auto grid w-full max-w-(--thread-max-width) animate-in auto-rows-auto grid-cols-[minmax(72px,1fr)_auto] content-start gap-2 sm:gap-4 px-2 sm:px-4 py-3 sm:py-4 duration-150 [&:where(>*)]:col-start-2"
      data-role="user"
    >
      <div className="shrink-0 size-8 rounded-full bg-muted flex items-center justify-center text-muted-foreground mt-1 order-last">
        <UserIcon className="size-4" />
      </div>
      <div className="flex-1 min-w-0">
        <UserMessageAttachments />

        <div className="aui-user-message-content-wrapper relative col-start-2 min-w-0 flex flex-col items-end">
          <div className="aui-user-message-content wrap-break-word rounded-xl sm:rounded-2xl bg-muted px-3 sm:px-4 py-2 sm:py-2.5 text-foreground text-sm sm:text-base">
            <MessagePrimitive.Parts />
          </div>
          <div className="aui-user-action-bar-wrapper absolute top-1/2 left-0 -translate-x-full -translate-y-1/2 pr-2">
            <UserActionBar />
          </div>
        </div>

        <BranchPicker className="aui-user-branch-picker col-span-full col-start-1 row-start-3 -mr-1 justify-end mt-2" />
      </div>
    </MessagePrimitive.Root>
  );
};

const UserActionBar: FC = () => {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="aui-user-action-bar-root flex flex-col items-end"
    >
      <ActionBarPrimitive.Edit asChild>
        <TooltipIconButton tooltip="Edit" className="aui-user-action-edit p-4">
          <PencilIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.Edit>
    </ActionBarPrimitive.Root>
  );
};

const PlanActionButtons: FC = () => {
  const handleApprove = (e: MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    if (typeof window !== "undefined") {
      (window as any).__investigator_intent = "approve";
      // Find the composer input and set its value, then trigger send
      const composerInput = document.querySelector(
        ".aui-composer-input"
      ) as HTMLTextAreaElement;
      if (composerInput) {
        composerInput.value = "approve";
        composerInput.dispatchEvent(new Event("input", { bubbles: true }));
        // Trigger send button click
        const sendButton = document.querySelector(
          ".aui-composer-send"
        ) as HTMLButtonElement;
        if (sendButton && !sendButton.disabled) {
          sendButton.click();
        }
      }
    }
  };

  const handleFeedback = (e: MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    if (typeof window !== "undefined") {
      (window as any).__investigator_intent = "feedback";
      // Find the composer input and set its value, then trigger send
      const composerInput = document.querySelector(
        ".aui-composer-input"
      ) as HTMLTextAreaElement;
      if (composerInput) {
        composerInput.value = "Here is my feedback on the plan: ";
        composerInput.dispatchEvent(new Event("input", { bubbles: true }));
        // Focus the input so user can add their feedback
        composerInput.focus();
        composerInput.setSelectionRange(
          composerInput.value.length,
          composerInput.value.length
        );
      }
    }
  };

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      <Button size="sm" className="rounded-full" onClick={handleApprove}>
        ✅ Approve & start
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="rounded-full"
        onClick={handleFeedback}
      >
        📝 Add feedback
      </Button>
    </div>
  );
};

const EditComposer: FC = () => {
  return (
    <MessagePrimitive.Root className="aui-edit-composer-wrapper mx-auto flex w-full max-w-(--thread-max-width) flex-col px-2 py-3">
      <ComposerPrimitive.Root className="aui-edit-composer-root ml-auto flex w-full max-w-[85%] flex-col rounded-2xl bg-muted">
        <ComposerPrimitive.Input
          className="aui-edit-composer-input min-h-14 w-full resize-none bg-transparent p-4 text-foreground text-sm outline-none"
          autoFocus
        />
        <div className="aui-edit-composer-footer mx-3 mb-3 flex items-center gap-2 self-end">
          <ComposerPrimitive.Cancel asChild>
            <Button variant="ghost" size="sm">
              Cancel
            </Button>
          </ComposerPrimitive.Cancel>
          <ComposerPrimitive.Send asChild>
            <Button size="sm">Update</Button>
          </ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    </MessagePrimitive.Root>
  );
};

const BranchPicker: FC<BranchPickerPrimitive.Root.Props> = ({
  className,
  ...rest
}) => {
  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch
      className={cn(
        "aui-branch-picker-root mr-2 -ml-2 inline-flex items-center text-muted-foreground text-xs",
        className
      )}
      {...rest}
    >
      <BranchPickerPrimitive.Previous asChild>
        <TooltipIconButton tooltip="Previous">
          <ChevronLeftIcon />
        </TooltipIconButton>
      </BranchPickerPrimitive.Previous>
      <span className="aui-branch-picker-state font-medium">
        <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
      </span>
      <BranchPickerPrimitive.Next asChild>
        <TooltipIconButton tooltip="Next">
          <ChevronRightIcon />
        </TooltipIconButton>
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
};
