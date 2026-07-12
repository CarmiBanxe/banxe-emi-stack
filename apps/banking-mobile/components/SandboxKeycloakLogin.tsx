// SANDBOX: Keycloak :8180 login stub — no real customers, no real sessions.
// Points to EXPO_PUBLIC_KEYCLOAK_URL (default: localhost:8180).
// Production: use expo-auth-session with proper PKCE flow + Keycloak :8180 → prod.
import { useCallback, useState } from "react";
import { Alert, Text, TextInput, TouchableOpacity, View } from "react-native";

const KEYCLOAK_URL = process.env.EXPO_PUBLIC_KEYCLOAK_URL ?? "http://localhost:8180";
const KEYCLOAK_REALM = process.env.EXPO_PUBLIC_KEYCLOAK_REALM ?? "banxe-sandbox";
const KEYCLOAK_CLIENT_ID = process.env.EXPO_PUBLIC_KEYCLOAK_CLIENT_ID ?? "banking-mobile-sandbox";

const TOKEN_ENDPOINT = `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`;

interface LoginState {
  loading: boolean;
  token: string | null;
  error: string | null;
}

export function SandboxKeycloakLogin() {
  const [username, setUsername] = useState("sandbox-user");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<LoginState>({ loading: false, token: null, error: null });

  const handleLogin = useCallback(async () => {
    if (!password) return;
    setState({ loading: true, token: null, error: null });

    try {
      const body = new URLSearchParams({
        grant_type: "password",
        client_id: KEYCLOAK_CLIENT_ID,
        username,
        password,
      });

      const res = await fetch(TOKEN_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });

      if (res.ok) {
        const data = await res.json();
        const shortToken = String(data.access_token ?? "").slice(0, 20) + "…";
        setState({ loading: false, token: shortToken, error: null });
      } else {
        const err = await res.text();
        // Sandbox: treat any error as a stub success for demo flow
        setState({
          loading: false,
          token: null,
          error: `[SANDBOX] Keycloak returned ${res.status}. Check :8180 is running.\n${err.slice(0, 80)}`,
        });
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      setState({
        loading: false,
        token: null,
        error: `[SANDBOX] Cannot reach ${TOKEN_ENDPOINT}.\n${msg}`,
      });
    }
  }, [username, password]);

  if (state.token) {
    return (
      <View className="flex-1 items-center justify-center px-6">
        <View className="bg-green-50 border border-green-200 rounded-2xl p-6 w-full">
          <Text className="text-green-800 font-bold text-lg mb-2 text-center">✓ Signed In (Sandbox)</Text>
          <Text className="text-green-700 text-xs text-center mb-2">Token prefix: {state.token}</Text>
          <Text className="text-green-600 text-xs text-center">⚠ SANDBOX session — no real customer data</Text>
        </View>
        <TouchableOpacity
          className="mt-4 bg-slate-100 rounded-xl px-6 py-3"
          onPress={() => setState({ loading: false, token: null, error: null })}
          accessibilityRole="button"
        >
          <Text className="text-slate-600 font-semibold">Sign Out</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View className="flex-1 justify-center px-6">
      <View className="items-center mb-8">
        <View className="bg-banxe-primary rounded-2xl px-6 py-3 mb-3">
          <Text className="text-white font-bold text-xl">Banxe</Text>
        </View>
        <Text className="text-xl font-bold text-slate-900">Sign In</Text>
        <View className="bg-amber-100 rounded-full px-4 py-1 mt-2">
          <Text className="text-amber-800 text-xs font-bold">⚠ SANDBOX — Keycloak :8180</Text>
        </View>
        <Text className="text-xs text-slate-500 mt-1 text-center">
          {KEYCLOAK_URL} / realm: {KEYCLOAK_REALM}
        </Text>
      </View>

      <TextInput
        className="border border-slate-300 rounded-xl px-4 py-3 mb-3 bg-white text-slate-900"
        placeholder="Username"
        value={username}
        onChangeText={setUsername}
        autoCapitalize="none"
        autoCorrect={false}
      />
      <TextInput
        className="border border-slate-300 rounded-xl px-4 py-3 mb-4 bg-white text-slate-900"
        placeholder="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        onSubmitEditing={handleLogin}
      />

      {state.error && (
        <View className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-4">
          <Text className="text-red-700 text-xs">{state.error}</Text>
        </View>
      )}

      <TouchableOpacity
        className={`rounded-xl py-4 ${state.loading || !password ? "bg-slate-300" : "bg-banxe-primary"}`}
        onPress={handleLogin}
        disabled={state.loading || !password}
        accessibilityRole="button"
      >
        <Text className="text-white font-semibold text-center text-base">
          {state.loading ? "Signing in…" : "Sign In (Sandbox)"}
        </Text>
      </TouchableOpacity>

      <Text className="text-xs text-slate-400 text-center mt-6">
        Production: PKCE flow via expo-auth-session + Keycloak prod realm
      </Text>
    </View>
  );
}
