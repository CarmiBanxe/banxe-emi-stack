// SANDBOX: Profile tab — mock user, no real PII. SCA mock trigger available here.
import { useState } from "react";
import { Text, TouchableOpacity, View } from "react-native";

import { SandboxMockSCA } from "@/components/SandboxMockSCA";

export default function ProfileTab() {
  const [showSCA, setShowSCA] = useState(false);
  const [scaResult, setScaResult] = useState<string | null>(null);

  function handleSCAResult(success: boolean) {
    setShowSCA(false);
    setScaResult(success ? "SCA MOCK: Passed ✓" : "SCA MOCK: Cancelled");
  }

  return (
    <View className="flex-1 bg-slate-50 px-4 pt-8">
      <View className="items-center mb-8">
        <View className="w-20 h-20 rounded-full bg-banxe-primary items-center justify-center mb-3">
          <Text className="text-white text-3xl font-bold">T</Text>
        </View>
        <Text className="text-xl font-bold text-slate-900">Test User (Sandbox)</Text>
        <Text className="text-sm text-amber-700 mt-1">⚠ SANDBOX — no real customer data</Text>
        <Text className="text-xs text-slate-500">test-user@sandbox.banxe.com</Text>
      </View>

      {scaResult && (
        <View className="bg-green-50 border border-green-200 rounded-xl px-4 py-3 mb-4">
          <Text className="text-green-800 text-sm font-semibold">{scaResult}</Text>
        </View>
      )}

      <TouchableOpacity
        className="bg-banxe-primary rounded-xl px-4 py-4 mb-3"
        onPress={() => setShowSCA(true)}
        accessibilityRole="button"
      >
        <Text className="text-white font-semibold text-center">Test SCA (Mock Face ID)</Text>
        <Text className="text-blue-200 text-xs text-center mt-1">SANDBOX — no real biometric</Text>
      </TouchableOpacity>

      <SandboxMockSCA visible={showSCA} onResult={handleSCAResult} />
    </View>
  );
}
