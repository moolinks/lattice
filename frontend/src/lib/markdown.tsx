import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { Link } from "react-router-dom";

function preprocess(text: string): string {
  return text
    .replace(/\[\[((?:P|I|E|D)\d{4})\]\]/g, (_match, id: string) => {
      const prefix = id[0];
      const href =
        prefix === "P"
          ? `/papers/${id}`
          : prefix === "E"
            ? `/experiments/${id}`
            : prefix === "D"
              ? `/drafts/${id}`
              : `/ideas?focus=${id}`;
      return `[${id}](${href})`;
    })
    .replace(/\{\{run:([A-Za-z0-9-]+)(?:\/([^}]+))?\}\}/g, (_match, runId: string, file?: string) => {
      return `\n\n> **实验图表** · \`${runId}\`${file ? ` / ${file}` : ""}  \n> 图表在导出 PDF 时自动嵌入；编辑预览中以占位符显示。\n\n`;
    });
}

interface MarkdownProps {
  children: string;
  className?: string;
  compact?: boolean;
}

export function Markdown({ children, className = "", compact = false }: MarkdownProps) {
  return (
    <div className={`markdown ${compact ? "markdown-compact" : ""} ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ href, children: linkChildren }) => {
            if (href?.startsWith("/")) {
              return <Link to={href}>{linkChildren}</Link>;
            }
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {linkChildren}
              </a>
            );
          },
          img: ({ src, alt }) => {
            if (!src) return null;
            const resolved = src.startsWith("http") || src.startsWith("/") ? src : undefined;
            if (!resolved) {
              return <span className="image-placeholder">〔图表：{alt || src}〕</span>;
            }
            return <img src={resolved} alt={alt || ""} loading="lazy" />;
          },
          table: ({ children: tableChildren }) => (
            <div className="table-wrap">
              <table>{tableChildren}</table>
            </div>
          ),
          input: ({ checked }) => (
            <span className={`task-box ${checked ? "checked" : ""}`}>{checked ? "✓" : ""}</span>
          ),
        }}
      >
        {preprocess(children || "")}
      </ReactMarkdown>
    </div>
  );
}

export function InlineMarkdown({ children }: { children: ReactNode }) {
  return <span className="inline-markdown">{children}</span>;
}
