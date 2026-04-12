import { useEffect, useState, useRef } from "react";
import { X, Plus, Send, MessageSquare } from "lucide-react";
import { api } from "../../lib/api";
import type { Thread, Message } from "../../lib/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Spinner } from "../ui/spinner";

interface Props {
  analysisId: string;
  onClose: () => void;
}

export function ThreadDrawer({ analysisId, onClose }: Props) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThread, setActiveThread] = useState<Thread | null>(null);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
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
  }, [activeThread?.messages]);

  const handleCreateThread = async () => {
    const thread = await api.post<Thread>(
      `/analyses/${analysisId}/threads`,
      { title: "New Thread" },
    );
    setThreads((prev) => [thread, ...prev]);
    loadThread(thread.id);
  };

  const handleSend = async () => {
    if (!message.trim() || !activeThread || sending) return;
    setSending(true);
    const content = message;
    setMessage("");

    // Optimistic update
    const tempMsg: Message = {
      id: crypto.randomUUID(),
      thread_id: activeThread.id,
      role: "user",
      content,
      metadata: null,
      created_at: new Date().toISOString(),
    };
    setActiveThread((prev) =>
      prev ? { ...prev, messages: [...prev.messages, tempMsg] } : prev,
    );

    try {
      const result = await api.post<{
        user_message: Message;
        assistant_message: Message;
      }>(`/threads/${activeThread.id}/messages`, { content });

      // Replace optimistic with real + add assistant
      setActiveThread((prev) => {
        if (!prev) return prev;
        const msgs = prev.messages.filter((m) => m.id !== tempMsg.id);
        return {
          ...prev,
          messages: [...msgs, result.user_message, result.assistant_message],
        };
      });
    } catch {
      // Remove optimistic message on error
      setActiveThread((prev) =>
        prev
          ? { ...prev, messages: prev.messages.filter((m) => m.id !== tempMsg.id) }
          : prev,
      );
      setMessage(content); // Restore for retry
    } finally {
      setSending(false);
    }
  };

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
        ) : activeThread.messages.length === 0 ? (
          <p className="text-center text-muted-foreground text-sm py-8">
            Ask the agent about simulations, data, or results.
          </p>
        ) : (
          activeThread.messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-foreground"
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
            </div>
          ))
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
