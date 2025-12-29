// Simplified Composer without mode selector
import { ComposerPrimitive } from "@assistant-ui/react";
import { Coffee } from "lucide-react";
import { ComposerAttachments } from "@/components/attachment";
import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { SendHorizonalIcon, CircleStopIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FC } from "react";

export const SimpleComposer: FC = () => {
  const placeholder = "Brew anything... (Type 'investigate: topic' for research)";

  return (
    <ComposerPrimitive.Root className="aui-composer-root relative flex w-full flex-col">
      <ComposerPrimitive.AttachmentDropzone className="aui-composer-attachment-dropzone flex w-full flex-col rounded-xl sm:rounded-2xl border border-border bg-card dark:bg-card/50 shadow-sm dark:shadow-md px-0 pt-2 sm:pt-3 pb-2 sm:pb-3 outline-none transition-shadow has-[textarea:focus-visible]:border-ring has-[textarea:focus-visible]:ring-2 has-[textarea:focus-visible]:ring-ring/20 data-[dragging=true]:border-ring data-[dragging=true]:border-dashed data-[dragging=true]:bg-accent/50">
        <ComposerAttachments />
        <div className="px-2 sm:px-3.5 grid grid-cols-[auto_1fr_auto] items-center gap-x-1.5 sm:gap-x-2 gap-y-2">
          <div className="row-start-2 flex items-center">
            {/* Simple mode badge - no dropdown needed */}
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted/50 text-xs">
              <Coffee className="size-3.5" />
              <span className="hidden sm:inline font-medium">Brew</span>
            </div>
          </div>
          <ComposerPrimitive.Input
            placeholder={placeholder}
            className="aui-composer-input col-span-3 row-start-1 mb-1 max-h-32 min-h-12 sm:min-h-14 w-full resize-none bg-transparent px-3 sm:px-4 pt-2 pb-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-0"
            rows={1}
            autoFocus
            aria-label="Message input"
          />
          <ComposerPrimitive.Send asChild>
            <TooltipIconButton
              tooltip="Send"
              variant="default"
              className="aui-composer-send my-2.5 size-8 p-2 transition-opacity"
            >
              <SendHorizonalIcon />
            </TooltipIconButton>
          </ComposerPrimitive.Send>
          <ThreadPrimitive.If running={false}>
            <ComposerPrimitive.Cancel asChild>
              <TooltipIconButton
                tooltip="Cancel"
                variant="default"
                className="aui-composer-cancel my-2.5 size-8 p-2 transition-opacity"
              >
                <CircleStopIcon />
              </TooltipIconButton>
            </ComposerPrimitive.Cancel>
          </ThreadPrimitive.If>
        </div>
      </ComposerPrimitive.AttachmentDropzone>
    </ComposerPrimitive.Root>
  );
};

