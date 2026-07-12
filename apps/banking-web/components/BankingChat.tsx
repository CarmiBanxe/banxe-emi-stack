"use client";

// SANDBOX: Chat interface wired to /api/chat streaming endpoint (LangGraph sandbox).
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { Thread } from "@assistant-ui/react";
import { useVercelUseChatRuntime } from "@assistant-ui/react-ai-sdk";
import { useChat } from "ai/react";

function BankingChatInner() {
  const chat = useChat({
    api: "/api/chat",
  });

  const runtime = useVercelUseChatRuntime(chat);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <Thread />
    </AssistantRuntimeProvider>
  );
}

export function BankingChat() {
  return (
    <div className="flex h-full flex-col">
      <BankingChatInner />
    </div>
  );
}
