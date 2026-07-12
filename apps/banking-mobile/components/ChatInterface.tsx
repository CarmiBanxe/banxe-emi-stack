"use client";
// SANDBOX: Chat interface for banking-mobile.
// Streams from EXPO_PUBLIC_BANKING_BACKEND_URL (default: localhost:4000).
// No real banking data — sandbox system prompt enforced server-side.
import { useCallback, useRef, useState } from "react";
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const BACKEND_URL =
  process.env.EXPO_PUBLIC_BANKING_BACKEND_URL ?? "http://localhost:4000/v1/chat/completions";
const MODEL = process.env.EXPO_PUBLIC_BANKING_MODEL ?? "banxe-general";

const SYSTEM_MESSAGE = {
  role: "system" as const,
  content:
    "You are the Banxe Banking AI in SANDBOX MODE. All data is synthetic. " +
    "No real customers, accounts, or transactions. Remind users of sandbox mode when discussing balances.",
};

let _msgCounter = 0;
function nextId(): string {
  _msgCounter += 1;
  return String(_msgCounter);
}

export function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const listRef = useRef<FlatList<Message>>(null);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = { id: nextId(), role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: MODEL,
          stream: false,
          messages: [
            SYSTEM_MESSAGE,
            ...messages.map((m) => ({ role: m.role, content: m.content })),
            { role: "user", content: text },
          ],
        }),
      });

      const data = await response.json();
      const assistantContent: string = data?.choices?.[0]?.message?.content ?? "(no response)";
      const assistantMsg: Message = { id: nextId(), role: "assistant", content: assistantContent };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "assistant", content: "⚠ Sandbox backend unreachable. Check EXPO_PUBLIC_BANKING_BACKEND_URL." },
      ]);
    } finally {
      setLoading(false);
      listRef.current?.scrollToEnd({ animated: true });
    }
  }, [input, loading, messages]);

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} className="flex-1">
      <View className="bg-amber-50 border-b border-amber-200 px-4 py-2">
        <Text className="text-amber-800 text-xs font-semibold text-center">
          ⚠ SANDBOX — LangGraph backend · banxe-general · synthetic data only
        </Text>
      </View>
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m) => m.id}
        contentContainerStyle={{ padding: 16 }}
        renderItem={({ item }) => (
          <View className={`mb-3 ${item.role === "user" ? "items-end" : "items-start"}`}>
            <View
              className={`max-w-xs rounded-2xl px-4 py-3 ${
                item.role === "user" ? "bg-banxe-primary" : "bg-slate-100"
              }`}
            >
              <Text className={item.role === "user" ? "text-white" : "text-slate-900"}>{item.content}</Text>
            </View>
          </View>
        )}
        ListEmptyComponent={
          <Text className="text-center text-slate-400 mt-8">Ask about your accounts (sandbox data only)</Text>
        }
      />
      <View className="flex-row items-end px-4 py-3 border-t border-slate-200 bg-white gap-3">
        <TextInput
          className="flex-1 border border-slate-300 rounded-xl px-4 py-3 text-slate-900 bg-white max-h-28"
          placeholder="Ask the Banking AI..."
          value={input}
          onChangeText={setInput}
          multiline
          returnKeyType="send"
          onSubmitEditing={sendMessage}
        />
        <TouchableOpacity
          className={`rounded-xl px-4 py-3 ${loading || !input.trim() ? "bg-slate-300" : "bg-banxe-primary"}`}
          onPress={sendMessage}
          disabled={loading || !input.trim()}
          accessibilityRole="button"
        >
          <Text className="text-white font-semibold">{loading ? "..." : "Send"}</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}
