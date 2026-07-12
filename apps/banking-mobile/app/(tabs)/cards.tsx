// SANDBOX: Cards tab — mock card display, no real card data.
import { ScrollView, Text, View } from "react-native";

function SandboxCard({ label, last4, status }: { label: string; last4: string; status: string }) {
  return (
    <View className="rounded-2xl bg-banxe-primary p-5 mb-4">
      <Text className="text-blue-200 text-xs font-semibold mb-1">SANDBOX CARD ⚠</Text>
      <Text className="text-white font-bold text-lg mb-4">{label}</Text>
      <Text className="text-blue-200 text-base tracking-widest">•••• •••• •••• {last4}</Text>
      <View className="flex-row items-center justify-between mt-4">
        <Text className="text-blue-200 text-xs">Banxe AI Bank</Text>
        <View className="bg-green-400 rounded-full px-3 py-1">
          <Text className="text-green-900 text-xs font-bold">{status}</Text>
        </View>
      </View>
    </View>
  );
}

export default function CardsTab() {
  return (
    <ScrollView className="flex-1 bg-slate-50 px-4 pt-4">
      <Text className="text-xl font-bold text-slate-900 mb-4">Your Cards</Text>
      <SandboxCard label="GBP Current" last4="0001" status="SANDBOX" />
      <SandboxCard label="EUR Travel" last4="0002" status="SANDBOX" />
      <Text className="text-center text-amber-700 text-xs mt-2">
        ⚠ These are synthetic sandbox cards — no real payment capability.
      </Text>
    </ScrollView>
  );
}
