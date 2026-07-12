// SANDBOX: 5-tab bottom navigator (Home, AI Agent, Cards, Crypto, Profile)
import { Ionicons } from "@expo/vector-icons";
import { Tabs } from "expo-router";

import { FloatingAIButton } from "@/components/FloatingAIButton";
import { SandboxBanner } from "@/components/SandboxBanner";

type IoniconName = React.ComponentProps<typeof Ionicons>["name"];

interface TabConfig {
  name: string;
  title: string;
  icon: IoniconName;
}

const TABS: TabConfig[] = [
  { name: "index", title: "Home", icon: "home-outline" },
  { name: "agent", title: "AI Agent", icon: "chatbox-ellipses-outline" },
  { name: "cards", title: "Cards", icon: "card-outline" },
  { name: "crypto", title: "Crypto", icon: "trending-up-outline" },
  { name: "profile", title: "Profile", icon: "person-outline" },
];

export default function TabsLayout() {
  return (
    <>
      <SandboxBanner />
      <Tabs
        screenOptions={({ route }) => {
          const tab = TABS.find((t) => t.name === route.name);
          return {
            headerShown: false,
            tabBarActiveTintColor: "#1e40af",
            tabBarInactiveTintColor: "#94a3b8",
            tabBarStyle: { borderTopWidth: 1, borderTopColor: "#e2e8f0" },
            tabBarIcon: ({ color, size }) => (
              <Ionicons name={tab?.icon ?? "ellipse-outline"} size={size} color={color} />
            ),
          };
        }}
      >
        {TABS.map((tab) => (
          <Tabs.Screen key={tab.name} name={tab.name} options={{ title: tab.title }} />
        ))}
      </Tabs>
      {/* Floating AI button — Revolut AIR pattern; overlaid on all tab screens */}
      <FloatingAIButton />
    </>
  );
}
