"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ModelConfig {
  parameters_human: string;
  vocab_size: number;
  model: {
    n_layers: number;
    n_heads: number;
    d_model: number;
    ctx_len: number;
  };
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [tokensPerSecond, setTokensPerSecond] = useState(0);
  const [temperature, setTemperature] = useState(0.7);
  const [showSettings, setShowSettings] = useState(false);
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/config`)
      .then((r) => r.json())
      .then(setModelConfig)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || isGenerating) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsGenerating(true);
    setTokensPerSecond(0);

    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMessage,
          temperature,
          top_k: 50,
          top_p: 0.9,
          max_tokens: 256,
        }),
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) return;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split("\n").filter((l) => l.startsWith("data: "));

        for (const line of lines) {
          const json = JSON.parse(line.slice(6));

          if (json.done) break;

          if (json.token) {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                last.content += json.token;
              }
              return updated;
            });
          }

          if (json.tokens_per_second) {
            setTokensPerSecond(json.tokens_per_second);
          }
        }
      }
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last.role === "assistant" && !last.content) {
          last.content = "Error: Could not connect to MineGPT server.";
        }
        return updated;
      });
    }

    setIsGenerating(false);
  }, [input, isGenerating, temperature]);

  return (
    <div className="flex flex-col h-screen bg-[var(--background)]">
      {/* Header - Minecraft-style border */}
      <header className="border-b-2 border-[#4ade80]/30 px-6 py-3 flex items-center justify-between bg-[var(--card)]">
        <div className="flex items-center gap-3">
          {/* Pixelated logo block */}
          <div
            className="w-9 h-9 bg-[#4ade80] flex items-center justify-center text-black font-bold text-base"
            style={{ imageRendering: "pixelated", boxShadow: "3px 3px 0 #2a8a4e" }}
          >
            M
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-wider text-[var(--primary)]">
              MineGPT
            </h1>
            <p className="text-xs text-[var(--muted-foreground)]">
              {modelConfig
                ? `${modelConfig.parameters_human} params | ${modelConfig.model.n_layers}L ${modelConfig.model.n_heads}H | vocab ${modelConfig.vocab_size}`
                : "Minecraft AI Encyclopedia"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {isGenerating && (
            <span className="text-xs text-[var(--primary)] font-mono">
              {tokensPerSecond} tok/s
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowSettings(!showSettings)}
            className="text-xs border-[var(--border)]"
          >
            Settings
          </Button>
        </div>
      </header>

      {/* Settings Panel */}
      {showSettings && (
        <Card className="mx-6 mt-3 p-4 border-[var(--border)] bg-[var(--card)]">
          <div className="flex items-center gap-4">
            <label className="text-sm text-[var(--muted-foreground)] min-w-[120px]">
              Temperature: {temperature.toFixed(1)}
            </label>
            <Slider
              value={[temperature]}
              onValueChange={([v]) => setTemperature(v)}
              min={0}
              max={2}
              step={0.1}
              className="flex-1"
            />
          </div>
        </Card>
      )}

      {/* Messages */}
      <ScrollArea className="flex-1 px-6" ref={scrollRef}>
        <div className="max-w-3xl mx-auto py-6 space-y-4">
          {messages.length === 0 && (
            <div className="text-center py-20">
              {/* Minecraft grass block style */}
              <div className="w-20 h-20 mx-auto mb-6 relative">
                <div
                  className="w-full h-1/3 bg-[#4ade80]"
                  style={{ boxShadow: "inset 0 -2px 0 #2a8a4e" }}
                />
                <div className="w-full h-2/3 bg-[#8B6914]" />
                <div className="absolute inset-0 flex items-center justify-center text-white font-bold text-3xl drop-shadow-lg">
                  ?
                </div>
              </div>
              <h2 className="text-2xl font-bold tracking-wider text-[var(--primary)] mb-2">
                MineGPT
              </h2>
              <p className="text-[var(--muted-foreground)] text-sm max-w-md mx-auto mb-8">
                Ask me anything about Minecraft. Crafting recipes, mob behavior,
                biomes, redstone circuits, survival strategies, and more.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {[
                  "How do I craft a diamond sword?",
                  "What is Redstone?",
                  "Tell me about the Warden",
                  "How to find Netherite?",
                ].map((suggestion) => (
                  <Button
                    key={suggestion}
                    variant="outline"
                    size="sm"
                    className="text-xs border-[var(--border)] hover:border-[var(--primary)] hover:text-[var(--primary)] transition-colors"
                    onClick={() => setInput(suggestion)}
                  >
                    {suggestion}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                    : "bg-[var(--secondary)] text-[var(--secondary-foreground)] border border-[var(--border)]"
                }`}
                style={{
                  // Minecraft-style sharp corners
                  borderRadius: "2px",
                  boxShadow:
                    msg.role === "user"
                      ? "2px 2px 0 #2a8a4e"
                      : "2px 2px 0 rgba(0,0,0,0.3)",
                }}
              >
                {msg.role === "assistant" && (
                  <span className="text-[var(--primary)] text-xs font-bold block mb-1 tracking-wider">
                    MineGPT
                  </span>
                )}
                <span className="whitespace-pre-wrap">{msg.content}</span>
                {msg.role === "assistant" &&
                  isGenerating &&
                  i === messages.length - 1 && (
                    <span className="inline-block w-2 h-4 bg-[var(--primary)] ml-0.5 animate-pulse" />
                  )}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>

      {/* Input bar - Minecraft crafting table style */}
      <div className="border-t-2 border-[#4ade80]/30 px-6 py-4 bg-[var(--card)]">
        <div className="max-w-3xl mx-auto flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
            placeholder="Ask about Minecraft..."
            disabled={isGenerating}
            className="flex-1 bg-[var(--input)] border-[var(--border)] placeholder:text-[var(--muted-foreground)] font-mono"
          />
          <Button
            onClick={sendMessage}
            disabled={!input.trim() || isGenerating}
            className="bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90 px-6 font-bold tracking-wider"
            style={{ boxShadow: "2px 2px 0 #2a8a4e" }}
          >
            {isGenerating ? "..." : "Send"}
          </Button>
        </div>
      </div>
    </div>
  );
}
