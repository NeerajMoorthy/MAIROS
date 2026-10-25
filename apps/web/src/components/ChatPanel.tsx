"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, ChevronDown, FileText, Loader2, Network, Send, User } from "lucide-react";

import { SystemNotice } from "@/components/SystemNotice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useHealth } from "@/lib/useHealth";
import { api, type RetrievalResult } from "@/lib/api";
import { describeError } from "@/lib/errorMessage";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: RetrievalResult[];
  error?: boolean;
}

/**
 * Tab (b): grounded Q&A.
 *
 * Every assistant message renders its retrieved passages underneath, so the
 * inline `[document, p. N]` markers in the answer can be checked against the
 * text they came from.
 */
export function ChatPanel({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);
  const { health, offline } = useHealth();

  function toggleExpanded(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const question = input.trim();
    if (!question || pending) return;

    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: "user", content: question },
    ]);
    setInput("");
    setPending(true);

    try {
      const response = await api.query(projectId, question);
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: response.answer || "No answer was generated.",
          sources: response.results,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          role: "assistant",
          content: describeError(err, "Something went wrong while answering."),
          error: true,
        },
      ]);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto w-full max-w-3xl space-y-6 px-6 py-6">
          {!offline && health && !health.llm.live && (
            <SystemNotice variant="offline" />
          )}

          {messages.length === 0 && (
            <div className="py-20 text-center">
              <Bot className="mx-auto mb-4 h-10 w-10 text-muted-foreground/40" />
              <h3 className="font-medium">Ask a question about this project</h3>
              <p className="mx-auto mt-1.5 max-w-md text-sm text-muted-foreground">
                Answers are generated only from the passages retrieved out of your
                indexed documents, with the source and page shown for every claim.
              </p>
            </div>
          )}

          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-3 ${
                message.role === "user" ? "flex-row-reverse" : ""
              }`}
            >
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border ${
                  message.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                }`}
              >
                {message.role === "user" ? (
                  <User className="h-4 w-4" />
                ) : (
                  <Bot className="h-4 w-4" />
                )}
              </div>

              <div
                className={`min-w-0 max-w-[85%] space-y-3 ${
                  message.role === "user" ? "items-end text-right" : ""
                }`}
              >
                <div
                  className={`inline-block whitespace-pre-wrap rounded-xl px-4 py-2.5 text-sm ${
                    message.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : message.error
                        ? "border border-destructive/40 bg-destructive/10"
                        : "border bg-card"
                  }`}
                >
                  {message.content}
                </div>

                {message.sources && message.sources.length > 0 && (
                  <div className="space-y-2 text-left">
                    <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      Sources ({message.sources.length})
                    </p>
                    {message.sources.map((source, index) => {
                      const key = `${message.id}-${source.chunk_id}`;
                      const isOpen = expanded.has(key);
                      return (
                        <Card key={source.chunk_id} className="border-l-[3px] border-l-primary/60 bg-muted/40">
                          <CardContent className="flex gap-2.5 p-3">
                            <span className="mt-0.5 shrink-0 font-mono text-[10px] font-semibold text-primary">
                              [{index + 1}]
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                                <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                                <span className="truncate text-xs font-medium">
                                  {source.document_name}
                                </span>
                                {source.page != null && (
                                  <Badge variant="outline" className="text-[10px]">
                                    p. {source.page}
                                  </Badge>
                                )}
                                <Badge variant="secondary" className="text-[10px]">
                                  score {source.score.toFixed(2)}
                                </Badge>
                                {source.graph_hit && (
                                  <Badge variant="secondary" className="text-[10px]">
                                    <Network className="h-2.5 w-2.5" /> graph
                                  </Badge>
                                )}
                              </div>
                              <p className={isOpen ? "text-xs text-muted-foreground" : "line-clamp-3 text-xs text-muted-foreground"}>
                                {source.text}
                              </p>
                              {source.text.length > 160 && (
                                <button
                                  type="button"
                                  onClick={() => toggleExpanded(key)}
                                  aria-expanded={isOpen}
                                  className="focus-ring mt-1 inline-flex items-center gap-0.5 text-[10px] font-medium text-primary hover:underline"
                                >
                                  <ChevronDown className={`h-3 w-3 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                                  {isOpen ? "Show less" : "Show full passage"}
                                </button>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ))}

          {pending && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border bg-muted">
                <Bot className="h-4 w-4" />
              </div>
              <div className="flex items-center gap-2 rounded-xl border bg-card px-4 py-2.5 text-sm text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Retrieving passages and generating…
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="shrink-0 border-t bg-background p-4">
        <form onSubmit={handleSubmit} className="mx-auto flex w-full max-w-3xl gap-2">
          <Input
            aria-label="Ask a question about your documents"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask a question grounded in your documents…"
            disabled={pending}
            className="h-10"
          />
          <Button
            type="submit"
            size="icon"
            aria-label="Send question"
            className="h-10 w-10"
            disabled={pending || !input.trim()}
          >
            <Send />
          </Button>
        </form>
      </div>
    </div>
  );
}
