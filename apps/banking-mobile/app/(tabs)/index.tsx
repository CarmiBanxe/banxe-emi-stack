// SANDBOX: Home tab — synthetic account summary, no real balances.
import { ScrollView, Text, View } from "react-native";

function BalanceCard({ label, amount }: { label: string; amount: string }) {
  return (
    <View className="rounded-xl bg-white p-4 shadow-sm border border-slate-200 mb-3">
      <Text className="text-xs text-slate-500 mb-1">{label}</Text>
      <Text className="text-2xl font-bold text-slate-900">{amount}</Text>
      <Text className="text-xs text-amber-700 mt-1">⚠ SANDBOX — synthetic data</Text>
    </View>
  );
}

export default function HomeTab() {
  return (
    <ScrollView className="flex-1 bg-slate-50 px-4 pt-4">
      <Text className="text-xl font-bold text-slate-900 mb-4">Overview</Text>
      <BalanceCard label="Current Account (GBP) — TEST" amount="£9,750.00" />
      <BalanceCard label="Safeguarded Funds (GBP) — TEST" amount="£250,000.00" />
      <BalanceCard label="FX Reserve (EUR) — TEST" amount="€12,000.00" />
      <View className="mt-4 rounded-xl bg-banxe-primary p-4">
        <Text className="text-white font-semibold text-base">Tap the AI button to ask about your accounts</Text>
        <Text className="text-blue-200 text-xs mt-1">All data is synthetic. Sandbox mode.</Text>
      </View>
    </ScrollView>
  );
}
