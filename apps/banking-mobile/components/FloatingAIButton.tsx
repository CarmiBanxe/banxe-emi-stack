// Floating AI button — Revolut AIR pattern.
// Positioned bottom-right; overlaid on all tab screens; opens /chat modal.
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { StyleSheet, TouchableOpacity, View } from "react-native";

export function FloatingAIButton() {
  const router = useRouter();

  return (
    <View style={styles.container} pointerEvents="box-none">
      <TouchableOpacity
        style={styles.button}
        onPress={() => router.push("/chat")}
        accessibilityRole="button"
        accessibilityLabel="Open AI Agent chat"
        accessibilityHint="Opens the Banking AI assistant"
      >
        <Ionicons name="sparkles" size={26} color="#ffffff" />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    bottom: 90, // above tab bar (~70) + gap
    right: 20,
    zIndex: 999,
  },
  button: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: "#1e40af",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#1e40af",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 8,
  },
});
