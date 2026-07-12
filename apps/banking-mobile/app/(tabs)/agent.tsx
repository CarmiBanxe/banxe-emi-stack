// SANDBOX: AI Agent tab — shortcut to the chat modal.
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Text, TouchableOpacity, View } from "react-native";

export default function AgentTab() {
  const router = useRouter();

  return (
    <View className="flex-1 items-center justify-center bg-slate-50 px-6">
      <Ionicons name="chatbox-ellipses-outline" size={64} color="#1e40af" />
      <Text className="text-xl font-bold text-slate-900 mt-4 text-center">Banking AI Agent</Text>
      <Text className="text-sm text-slate-500 mt-2 text-center">
        Ask about your accounts, transactions, or FX rates.{"\n"}
        <Text className="text-amber-700 font-semibold">SANDBOX: all data is synthetic.</Text>
      </Text>
      <TouchableOpacity
        className="mt-8 bg-banxe-primary px-8 py-4 rounded-2xl"
        onPress={() => router.push("/chat")}
        accessibilityRole="button"
        accessibilityLabel="Open AI Agent chat"
      >
        <Text className="text-white font-semibold text-base">Open Chat</Text>
      </TouchableOpacity>
    </View>
  );
}
