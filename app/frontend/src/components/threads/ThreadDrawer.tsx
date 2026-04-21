import { useEffect, useState, useRef, useCallback } from "react";
import { X, Plus, Send, MessageSquare, Pencil, Bot, Play, Grid3X3 } from "lucide-react";
import { api } from "../../lib/api";
import { useUser } from "../../lib/user-context";
import { getInitials } from "../../lib/utils";
import type { Thread, Message, SimulationTriggeredEvent, MatrixCreatedEvent } from "../../lib/types";
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
  width: number;
  onWidthChange: (w: number) => void;
  onMatrixCreated?: () => void;
}

const MIN_WIDTH = 384;   // w-96
const MAX_WIDTH = 1200;

export function ThreadDrawer({ analysisId, onClose, width, onWidthChange, onMatrixCreated }: Props) {
  const { user } = useUser();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThread, setActiveThread] = useState<Thread | null>(null);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [thinkingMsg, setThinkingMsg] = useState("");
  const [triggeredSims, setTriggeredSims] = useState<SimulationTriggeredEvent[]>([]);
  const [createdMatrices, setCreatedMatrices] = useState<MatrixCreatedEvent[]>([]);
  const [loading, setLoading] = useState(true);

  // Thread title editing
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const messagesEnd = useRef<HTMLDivElement>(null);

  // Poll triggered simulations for status updates
  useEffect(() => {
    const incomplete = triggeredSims.filter(
      (s) => s.status !== "COMPLETED" && s.status !== "FAILED",
    );
    if (incomplete.length === 0) return;

    const interval = setInterval(async () => {
      for (const sim of incomplete) {
        try {
          // Try by run_id first, fall back to params_hash (placeholder may be cleaned up)
          let updated: { status: string } | null = null;
          try {
            updated = await api.get<{ status: string }>(`/simulations/${sim.run_id}`);
          } catch {
            // Placeholder deleted by sync — look up real run by params_hash
            if (sim.params_hash) {
              try {
                updated = await api.get<{ status: string }>(`/simulations/by-hash/${sim.params_hash}`);
              } catch {
                // not synced yet
              }
            }
          }
          if (updated && updated.status !== sim.status) {
            setTriggeredSims((prev) =>
              prev.map((s) =>
                s.run_id === sim.run_id ? { ...s, status: updated!.status } : s,
              ),
            );
          }
        } catch {
          // ignore
        }
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [triggeredSims]);

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
    setCreatedMatrices([]);
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

    let accumulated = "";
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
      let finalMessage: Message | null = null;
      let realUserMsg: Message | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop()!;

        for (const line of lines) {
          // Skip SSE comments (heartbeat keep-alives)
          if (line.startsWith(":")) continue;
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
            } else if (data.type === "matrix_created") {
              setCreatedMatrices((prev) => [...prev, data.matrix]);
              onMatrixCreated?.();
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
      // If we already received content, keep it as the assistant message
      // rather than discarding everything
      setActiveThread((prev) => {
        if (!prev) return prev;
        const msgs = prev.messages.filter((m) => m.id !== tempUserMsg.id);
        msgs.push(tempUserMsg); // keep the user message
        if (accumulated) {
          msgs.push({
            id: crypto.randomUUID(),
            thread_id: activeThread.id,
            role: "assistant" as const,
            content: accumulated,
            metadata: null,
            created_at: new Date().toISOString(),
          });
        }
        return { ...prev, messages: msgs };
      });
      // Only restore text to input if nothing was received
      if (!accumulated) {
        setMessage(content);
      }
    } finally {
      setSending(false);
      setStreamingContent("");
    }
  }, [message, activeThread, sending]);

  const initials = user?.email ? getInitials(user.email) : "U";

  // Drag-to-resize
  const dragging = useRef(false);
  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      dragging.current = true;
      const startX = e.clientX;
      const startW = width;

      const onMove = (ev: PointerEvent) => {
        if (!dragging.current) return;
        const delta = startX - ev.clientX;
        const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startW + delta));
        onWidthChange(next);
      };
      const onUp = () => {
        dragging.current = false;
        document.removeEventListener("pointermove", onMove);
        document.removeEventListener("pointerup", onUp);
      };
      document.addEventListener("pointermove", onMove);
      document.addEventListener("pointerup", onUp);
    },
    [width, onWidthChange],
  );

  return (
    <div
      className="fixed right-0 top-0 h-full border-l border-border bg-card shadow-lg z-30 flex flex-col"
      style={{ width }}
    >
      {/* Resize handle */}
      <div
        onPointerDown={handlePointerDown}
        className="absolute left-0 top-0 h-full w-1.5 cursor-col-resize hover:bg-primary/20 active:bg-primary/30 transition-colors z-10"
      />

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
                <Badge
                  variant={sim.status === "COMPLETED" ? "success" : sim.status === "FAILED" ? "destructive" : "outline"}
                  className="ml-auto text-[10px] px-1.5 py-0"
                >
                  {sim.status === "COMPLETED" ? "Completed" : sim.status === "FAILED" ? "Failed" : sim.status}
                </Badge>
              </div>
            ))}

            {/* Matrix created notifications */}
            {createdMatrices.map((matrix) => (
              <div
                key={matrix.id}
                className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-xs"
              >
                <Grid3X3 className="h-3.5 w-3.5 text-primary shrink-0" />
                <span className="font-medium">Matrix created</span>
                <span className="text-muted-foreground">
                  {SIM_TYPE_LABELS[matrix.simulation_type] ?? matrix.simulation_type}
                </span>
                <span className="text-muted-foreground">
                  {matrix.rows}x{matrix.cols} ({matrix.total_cells} cells)
                </span>
                <Badge variant="outline" className="ml-auto text-[10px] px-1.5 py-0">
                  Ready to run
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
