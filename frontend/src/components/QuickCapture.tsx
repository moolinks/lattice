import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CornerDownLeft, Inbox } from "lucide-react";
import { post } from "@/lib/api";
import { toast } from "@/lib/toast";
import { Modal } from "./Modal";

export function QuickCapture({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [content, setContent] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!open) return;
    setContent("");
    window.setTimeout(() => ref.current?.focus(), 30);
  }, [open]);

  const mutation = useMutation({
    mutationFn: (text: string) => post("/inbox", { content: text }),
    onSuccess: () => {
      toast("已收进 Inbox，稍后再整理。");
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["inbox"] });
      onClose();
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  function submit() {
    if (!content.trim()) return;
    mutation.mutate(content.trim());
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={
        <span className="modal-title-with-icon">
          <Inbox size={18} /> 快速记录
        </span>
      }
      subtitle="先捕获，不整理。Cmd / Ctrl + Enter 保存。"
      width="md"
    >
      <textarea
        ref={ref}
        className="quick-capture-textarea"
        placeholder="一个念头、一条审稿人质疑、一个可能成立的机制…"
        value={content}
        onChange={(event) => setContent(event.target.value)}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
            event.preventDefault();
            submit();
          }
        }}
        rows={7}
      />
      <div className="quick-capture-actions">
        <span className="small muted">进入今日页的 Inbox，不打断当前工作。</span>
        <button className="btn btn-primary" onClick={submit} disabled={!content.trim() || mutation.isPending}>
          <CornerDownLeft size={15} />
          {mutation.isPending ? "保存中…" : "收进 Inbox"}
        </button>
      </div>
    </Modal>
  );
}
