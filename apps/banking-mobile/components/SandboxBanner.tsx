// SANDBOX: Visible warning on every screen — no live banking data.
import { Text, View } from "react-native";

export function SandboxBanner() {
  return (
    <View className="w-full bg-sandbox-bg border-b border-sandbox-border px-3 py-1.5">
      <Text className="text-sandbox-text text-xs font-semibold text-center">
        ⚠ SANDBOX MODE — Synthetic data only. No real banking. Backend: LangGraph sandbox.
      </Text>
    </View>
  );
}
