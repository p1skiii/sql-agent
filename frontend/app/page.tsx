"use client";

import { useEffect, useRef, useState } from "react";

function Bubble({ role, content }: { role: "user" | "assistant"; content: string }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-4 py-3 text-sm shadow-sm ${
          isUser ? "bg-primary text-primary-foreground" : "bg-card text-foreground"
        }`}
      >
        {content}
      </div>
    </div>
  );
}

export default function Page() {
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const question = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setInput("");
    setError(null);
    setLoading(true);
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || resp.statusText);
      }
      const data = await resp.json();
      const summary = data.summary ?? data.reason ?? "No response";
      setMessages((prev) => [...prev, { role: "assistant", content: summary }]);
    } catch (err: any) {
      setError(err?.message || "Request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col px-4 py-10">
      <header className="mb-6 flex items-baseline justify-between border-b border-white/5 pb-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">SQL Agent Chat</h1>
          <p className="text-sm text-muted">Ask in English; responses come from your local SQL Agent backend.</p>
        </div>
        <div className="rounded-full border border-white/10 bg-card px-3 py-1 text-xs text-muted">
          localhost:8000/run
        </div>
      </header>

      <div
        ref={listRef}
        className="scroll-area flex-1 space-y-3 overflow-y-auto rounded-xl border border-white/10 bg-gradient-to-br from-card/90 to-card/60 p-4 shadow-lg"
      >
        {messages.length === 0 && !loading && (
          <p className="text-sm text-muted">Start by asking “List the names of all students”.</p>
        )}
        {messages.map((m, idx) => (
          <Bubble key={idx} role={m.role} content={m.content} />
        ))}
        {loading && <div className="text-sm text-muted">Thinking…</div>}
      </div>

      <div className="mt-4 flex gap-3">
        <input
          className="flex-1 rounded-lg border border-white/10 bg-card px-4 py-3 text-sm text-foreground placeholder:text-muted focus:border-primary focus:outline-none"
          placeholder="Type your question and press Enter"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button
          onClick={send}
          disabled={loading}
          className="rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-white shadow hover:opacity-90 disabled:opacity-50"
        >
          Send
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
    </main>
  );
}
