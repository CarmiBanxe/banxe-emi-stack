// SANDBOX: Keycloak sandbox login stub — points to :8180, no real customers.
import { SandboxKeycloakLogin } from "@/components/SandboxKeycloakLogin";
import { View } from "react-native";

export default function LoginScreen() {
  return (
    <View className="flex-1 bg-slate-50">
      <SandboxKeycloakLogin />
    </View>
  );
}
