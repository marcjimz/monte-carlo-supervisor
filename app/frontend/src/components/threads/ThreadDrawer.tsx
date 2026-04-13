import { useEffect, useState, useRef, useCallback } from "react";
import { X, Plus, Send, MessageSquare, Pencil, Bot, Play } from "lucide-react";
import { api } from "../../lib/api";
import { useUser } from "../../lib/user-context";
import { getInitials } from "../../lib/utils";
import type { Thread, Message, SimulationTriggeredEvent } from "../../lib/types";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Input } from "../ui/input";
import { Spinner } from "../ui/spinner";
import { MarkdownContent } from "../ui/markdown";

const SIM_TYPE_LABELS: Record<string, string> = {
  cost_comparison: "Cost Comparison",
  system_cost_roi: "System Cost ROI",
  patient_volume: "Patient Volume",
  revenue_projection: "Revenue Projection",
};

const THINKING_MESSAGES = [
  "Agent thinking...",
  "Consulting the data...",
  "Querying the warehouse...",
  "Orchestrating agents...",
  "Analyzing patterns...",
  "Crunching numbers...",
  "Connecting the dots...",
  "Routing to the right agent...",
  "Searching for insights...",
  "Running the numbers...",
];

interface Props {
  analysisId: string;
  onClose: () => void;
}

export function ThreadDrawer({ analysisId, onClose }: Props) {
  const { user } = useUser();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThread, setActiveThread] = useState<Thread | null>(null);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [thinkingMsg, setThinkingMsg] = useState("");
  const [triggeredSims, setTriggeredSims] = useState<SimulationTriggeredEvent[]>([]);
  const [loading, setLoading] = useState(true);

  // Thread title editing
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const messagesEnd = useRef<HTMLDivElement>(null);

  const fetchThreads = () => {
    api
      .get<{ threads: Thread[] }>(`/analyses/${analysisId}/threads`)
      .then((data) => {
        setThreads(data.threads);
        if (data.threads.length > 0 && !activeThread) {
          loadThread(data.threads[0]!.id);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  const loadThread = (threadId: string) => {
    api
      .get<Thread>(`/threads/${threadId}`)
      .then(setActiveThread)
      .catch(console.error);
  };

  useEffect(fetchThreads, [analysisId]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeThread?.messages, streamingContent]);

  // Rotate thinking messages while waiting for first token
  useEffect(() => {
    if (!sending || streamingContent) return;
    setThinkingMsg(
      THINKING_MESSAGES[Math.floor(Math.random() * THINKING_MESSAGES.length)]!,
    );
    const interval = setInterval(() => {
      setThinkingMsg(
        THINKING_MESSAGES[Math.floor(Math.random() * THINKING_MESSAGES.length)]!,
      );
    }, 3000);
    return () => clearInterval(interval);
  }, [sending, streamingContent]);

  const handleCreateThread = async () => {
    const thread = await api.post<Thread>(
      `/analyses/${analysisId}/threads`,
      { title: "New Thread" },
    );
    setThreads((prev) => [thread, ...prev]);
    loadThread(thread.id);
  };

  const handleSaveTitle = async (threadId: string) => {
    if (!editTitle.trim()) {
      setEditingThreadId(null);
      return;
    }
    await api.patch(`/threads/${threadId}`, { title: editTitle.trim() });
    setThreads((prev) =>
      prev.map((t) =>
        t.id === threadId ? { ...t, title: editTitle.trim() } : t,
      ),
    );
    if (activeThread?.id === threadId) {
      setActiveThread((prev) =>
        prev ? { ...prev, title: editTitle.trim() } : prev,
      );
    }
    setEditingThreadId(null);
  };

  const handleSend = useCallback(async () => {
    if (!message.trim() || !activeThread || sending) return;
    setSending(true);
    setStreamingContent("");
    setTriggeredSims([]);
    const content = message;
    setMessage("");

    // Optimistic user message
    const tempUserMsg: Message = {
      id: crypto.randomUUID(),
      thread_id: activeThread.id,
      role: "user",
      content,
      metadata: null,
      created_at: new Date().toISOString(),
    };
    setActiveThread((prev) =>
      prev ? { ...prev, messages: [...prev.messages, tempUserMsg] } : prev,
    );

    try {
      const resp = await fetch(`/api/threads/${activeThread.id}/messages/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`Stream failed: ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulated = "";
      let finalMessage: Message | null = null;
      let realUserMsg: Message | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop()!;

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "user_message") {
              realUserMsg = data.message;
            } else if (data.type === "delta") {
              accumulated += data.content;
              setStreamingContent(accumulated);
            } else if (data.type === "simulation_triggered") {
              setTriggeredSims((prev) => [...prev, data.simulation]);
            } else if (data.type === "done") {
              finalMessage = data.message;
            }
          } catch {
            // skip malformed lines
          }
        }
      }

      // Replace optimistic messages with real ones
      setActiveThread((prev) => {
        if (!prev) return prev;
        const msgs = prev.messages.filter((m) => m.id !== tempUserMsg.id);
        if (realUserMsg) msgs.push(realUserMsg);
        else msgs.push(tempUserMsg); // keep optimistic if no real one
        if (finalMessage) msgs.push(finalMessage);
        return { ...prev, messages: msgs };
      });
    } catch (err) {
      console.error("Stream error:", err);
      // Remove optimistic message on error
      setActiveThread((prev) =>
        prev
          ? {
              ...prev,
              messages: prev.messages.filter((m) => m.id !== tempUserMsg.id),
            }
          : prev,
      );
      setMessage(content);
    } finally {
      setSending(false);
      setStreamingContent("");
    }
  }, [message, activeThread, sending]);

  const initials = user?.email ? getInitials(user.email) : "U";

  return (
    <div className="fixed right-0 top-0 h-full w-96 border-l border-border bg-card shadow-lg z-30 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          <span className="font-semibold text-sm">Agent Chat</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" onClick={handleCreateThread}>
            <Plus className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Active thread title */}
      {activeThread && (
        <div className="flex items-center gap-2 border-b border-border px-4 py-2">
          {editingThreadId === activeThread.id ? (
            <Input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSaveTitle(activeThread.id);
                if (e.key === "Escape") setEditingThreadId(null);
              }}
              onBlur={() => handleSaveTitle(activeThread.id)}
              className="h-7 text-sm"
              autoFocus
            />
          ) : (
            <>
              <span className="text-sm font-medium truncate flex-1">
                {activeThread.title}
              </span>
              <button
                onClick={() => {
                  setEditingThreadId(activeThread.id);
                  setEditTitle(activeThread.title);
                }}
                className="text-muted-foreground hover:text-foreground shrink-0"
              >
                <Pencil className="h-3 w-3" />
              </button>
            </>
          )}
        </div>
      )}

      {/* Thread list (collapsed) */}
      {threads.length > 1 && (
        <div className="flex gap-1 overflow-x-auto border-b border-border px-3 py-2">
          {threads.map((t) => (
            <button
              key={t.id}
              onClick={() => loadThread(t.id)}
              className={`shrink-0 rounded-full px-3 py-1 text-xs transition-colors ${
                activeThread?.id === t.id
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              {t.title}
            </button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {loading ? (
          <div className="flex justify-center py-8">
            <Spinner className="h-5 w-5" />
          </div>
        ) : !activeThread ? (
          <div className="text-center text-muted-foreground py-8">
            <p className="text-sm mb-3">No threads yet.</p>
            <Button variant="outline" size="sm" onClick={handleCreateThread}>
              Start a conversation
            </Button>
          </div>
        ) : activeThread.messages.length === 0 && !sending ? (
          <p className="text-center text-muted-foreground text-sm py-8">
            Ask the agent about simulations, data, or results.
          </p>
        ) : (
          <>
            {activeThread.messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-2 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {/* Assistant avatar (left) */}
                {msg.role === "assistant" && (
                  <div className="shrink-0 w-7 h-7 rounded-full bg-accent flex items-center justify-center mt-0.5">
                    <Bot className="h-3.5 w-3.5 text-accent-foreground" />
                  </div>
                )}

                <div
                  className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-foreground"
                  }`}
                >
                  {msg.role === "assistant" ? (
                    <MarkdownContent content={msg.content} />
                  ) : (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  )}
                </div>

                {/* User avatar (right) */}
                {msg.role === "user" && (
                  <div className="shrink-0 w-7 h-7 rounded-full bg-primary flex items-center justify-center mt-0.5">
                    <span className="text-[10px] font-bold text-primary-foreground">
                      {initials}
                    </span>
                  </div>
                )}
              </div>
            ))}

            {/* Streaming assistant message */}
            {sending && (
              <div className="flex gap-2 justify-start">
                <div className="shrink-0 w-7 h-7 rounded-full bg-accent flex items-center justify-center mt-0.5">
                  <Bot className="h-3.5 w-3.5 text-accent-foreground" />
                </div>
                <div className="max-w-[75%] rounded-lg px-3 py-2 text-sm bg-muted text-foreground">
                  {streamingContent ? (
                    <MarkdownContent content={streamingContent} />
                  ) : (
                    <p className="text-muted-foreground italic flex items-center gap-2">
                      <Spinner className="h-3 w-3" />
                      {thinkingMsg}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Simulation triggered notifications */}
            {triggeredSims.map((sim) => (
              <div
                key={sim.run_id}
                className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-xs"
              >
                <Play className="h-3.5 w-3.5 text-primary shrink-0" />
                <span className="font-medium">Simulation triggered</span>
                <span className="text-muted-foreground">
                  {SIM_TYPE_LABELS[sim.simulation_type] ?? sim.simulation_type}
                </span>
                <Badge variant="outline" className="ml-auto text-[10px] px-1.5 py-0">
                  {sim.status}
                </Badge>
              </div>
            ))}
          </>
        )}
        <div ref={messagesEnd} />
      </div>

      {/* Input */}
      {activeThread && (
        <div className="border-t border-border p-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex gap-2"
          >
            <Input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Ask the agent..."
              disabled={sending}
              className="flex-1"
            />
            <Button type="submit" size="icon" disabled={sending || !message.trim()}>
              {sending ? <Spinner /> : <Send className="h-4 w-4" />}
            </Button>
          </form>
        </div>
      )}
    </div>
  );
}
