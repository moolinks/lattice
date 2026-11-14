import CodeMirror from "@uiw/react-codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { EditorView, keymap } from "@codemirror/view";
import type { RefObject } from "react";

const editorTheme = EditorView.theme({
  "&": {
    backgroundColor: "#fbf8f0",
    color: "#1d1c18",
    fontSize: "14px",
    height: "100%",
  },
  ".cm-scroller": {
    fontFamily:
      '"SFMono-Regular", "Cascadia Code", "JetBrains Mono", "Noto Sans Mono CJK SC", monospace',
    lineHeight: "1.85",
    overflow: "auto",
  },
  ".cm-content": {
    padding: "16px 0 48px",
    caretColor: "#c84b31",
  },
  ".cm-line": { padding: "0 22px" },
  ".cm-gutters": {
    backgroundColor: "#f5f1e7",
    color: "#aaa394",
    border: "none",
    paddingLeft: "6px",
  },
  ".cm-activeLine": { backgroundColor: "rgba(200, 75, 49, 0.045)" },
  ".cm-activeLineGutter": { backgroundColor: "transparent", color: "#c84b31" },
  "&.cm-focused": { outline: "none" },
  ".cm-selectionBackground, ::selection": { backgroundColor: "rgba(36, 78, 74, 0.18)" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "#c84b31", borderLeftWidth: "1.5px" },
});

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  onSave?: () => void;
  height?: string;
  placeholder?: string;
  editorRef?: RefObject<EditorView | null>;
}

export function MarkdownEditor({
  value,
  onChange,
  onSave,
  height = "560px",
  placeholder = "开始写作…",
  editorRef,
}: MarkdownEditorProps) {
  return (
    <div className="md-editor" style={{ height }}>
      <CodeMirror
        value={value}
        height="100%"
        extensions={[
          markdown(),
          EditorView.lineWrapping,
          editorTheme,
          keymap.of([
            {
              key: "Mod-s",
              preventDefault: true,
              run: () => {
                onSave?.();
                return true;
              },
            },
          ]),
        ]}
        placeholder={placeholder}
        basicSetup={{
          lineNumbers: true,
          foldGutter: false,
          highlightActiveLine: true,
          highlightActiveLineGutter: true,
          bracketMatching: true,
          closeBrackets: true,
          autocompletion: false,
          searchKeymap: false,
        }}
        onChange={onChange}
        onCreateEditor={(view) => {
          if (editorRef) editorRef.current = view;
        }}
      />
      <div className="md-editor-status">
        <span>Markdown</span>
        <span>{value.length.toLocaleString()} 字符</span>
        <span>⌘S 保存</span>
      </div>
    </div>
  );
}
