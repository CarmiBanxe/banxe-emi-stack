// SANDBOX MOCK SCA: Simulates Face ID / Touch ID prompt.
// THIS IS NOT REAL BIOMETRIC AUTHENTICATION.
// In production: replace with expo-local-authentication.authenticateAsync()
// behind a proper HITL gate (I-27).
import { Modal, Text, TouchableOpacity, View } from "react-native";

interface SandboxMockSCAProps {
  visible: boolean;
  onResult: (success: boolean) => void;
}

export function SandboxMockSCA({ visible, onResult }: SandboxMockSCAProps) {
  return (
    <Modal visible={visible} transparent animationType="fade" statusBarTranslucent>
      <View className="flex-1 bg-black/60 items-center justify-center px-8">
        <View className="bg-white rounded-3xl p-8 w-full max-w-sm items-center">
          {/* SANDBOX label — always visible */}
          <View className="bg-amber-100 rounded-full px-4 py-1 mb-4">
            <Text className="text-amber-800 text-xs font-bold">⚠ MOCK SCA — SANDBOX ONLY</Text>
          </View>

          {/* Face ID icon (mock) */}
          <View className="w-20 h-20 rounded-full bg-slate-100 items-center justify-center mb-4">
            <Text className="text-4xl">🔒</Text>
          </View>

          <Text className="text-lg font-bold text-slate-900 mb-2 text-center">Authentication Required</Text>
          <Text className="text-sm text-slate-500 text-center mb-6">
            Face ID (Mock){"\n"}
            <Text className="text-amber-700 font-semibold">This is a sandbox simulation.{"\n"}No real biometric data is collected.</Text>
          </Text>

          {/* Simulate success */}
          <TouchableOpacity
            className="w-full bg-banxe-primary rounded-2xl py-4 mb-3"
            onPress={() => onResult(true)}
            accessibilityRole="button"
          >
            <Text className="text-white font-semibold text-center">Simulate Face ID ✓</Text>
          </TouchableOpacity>

          {/* Cancel */}
          <TouchableOpacity
            className="w-full bg-slate-100 rounded-2xl py-4"
            onPress={() => onResult(false)}
            accessibilityRole="button"
          >
            <Text className="text-slate-600 font-semibold text-center">Cancel</Text>
          </TouchableOpacity>

          <Text className="text-xs text-slate-400 mt-4 text-center">
            Production: expo-local-authentication.authenticateAsync() + HITL gate (I-27)
          </Text>
        </View>
      </View>
    </Modal>
  );
}
