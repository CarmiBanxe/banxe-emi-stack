// SANDBOX: Banking Mobile root layout — no live banking data.
import "../global.css";

import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

export default function RootLayout() {
  return (
    <>
      <StatusBar style="auto" />
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="chat"
          options={{
            title: "AI Agent (Sandbox)",
            presentation: "modal",
            headerStyle: { backgroundColor: "#1e40af" },
            headerTintColor: "#ffffff",
          }}
        />
        <Stack.Screen
          name="login"
          options={{
            title: "Sign In (Sandbox)",
            headerShown: false,
          }}
        />
      </Stack>
    </>
  );
}
