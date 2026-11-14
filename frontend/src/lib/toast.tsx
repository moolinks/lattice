import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

type Tone = "success" | "error" | "info";
interface ToastItem {
  id: number;
  message: string;
  tone: Tone;
}

type Listener = (item: ToastItem) => void;
const listeners = new Set<Listener>();
let nextId = 1;

export function toast(message: string, tone: Tone = "success") {
  const item = { id: nextId++, message, tone };
  listeners.forEach((listener) => listener(item));
}

export function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    const listener: Listener = (item) => {
      setItems((current) => [...current, item].slice(-4));
      window.setTimeout(() => {
        setItems((current) => current.filter((entry) => entry.id !== item.id));
      }, 4800);
    };
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  return (
    <div className="toast-stack" aria-live="polite">
      {items.map((item) => (
        <div className={`toast toast-${item.tone}`} key={item.id}>
          {item.tone === "success" && <CheckCircle2 size={16} />}
          {item.tone === "error" && <AlertCircle size={16} />}
          {item.tone === "info" && <Info size={16} />}
          <span>{item.message}</span>
          <button
            className="icon-button"
            aria-label="关闭"
            onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
