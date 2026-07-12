// SANDBOX: Crypto tab — mock prices, no live exchange data.
import { ScrollView, Text, View } from "react-native";

interface CryptoRow {
  symbol: string;
  name: string;
  price: string;
  change: string;
  positive: boolean;
}

const MOCK_PRICES: CryptoRow[] = [
  { symbol: "BTC", name: "Bitcoin", price: "£62,450.00", change: "+2.4%", positive: true },
  { symbol: "ETH", name: "Ethereum", price: "£3,120.00", change: "-0.8%", positive: false },
  { symbol: "USDC", name: "USD Coin", price: "£0.79", change: "+0.1%", positive: true },
];

function CryptoRow({ row }: { row: CryptoRow }) {
  return (
    <View className="flex-row items-center justify-between bg-white rounded-xl px-4 py-3 mb-2 border border-slate-200">
      <View className="flex-row items-center gap-3">
        <View className="w-10 h-10 rounded-full bg-slate-100 items-center justify-center">
          <Text className="font-bold text-slate-700 text-xs">{row.symbol}</Text>
        </View>
        <View>
          <Text className="font-semibold text-slate-900">{row.name}</Text>
          <Text className="text-xs text-slate-500">{row.symbol}</Text>
        </View>
      </View>
      <View className="items-end">
        <Text className="font-semibold text-slate-900">{row.price}</Text>
        <Text className={`text-xs font-semibold ${row.positive ? "text-green-600" : "text-red-500"}`}>
          {row.change}
        </Text>
      </View>
    </View>
  );
}

export default function CryptoTab() {
  return (
    <ScrollView className="flex-1 bg-slate-50 px-4 pt-4">
      <Text className="text-xl font-bold text-slate-900 mb-1">Crypto</Text>
      <Text className="text-xs text-amber-700 mb-4">⚠ SANDBOX — synthetic prices, no live exchange data</Text>
      {MOCK_PRICES.map((row) => (
        <CryptoRow key={row.symbol} row={row} />
      ))}
    </ScrollView>
  );
}
