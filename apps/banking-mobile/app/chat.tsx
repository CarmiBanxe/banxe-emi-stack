// SANDBOX: Fullscreen chat modal — streaming from LiteLLM :4000 (banxe-general).
// No real banking data is sent or received; backend is sandbox only.
import { ChatInterface } from "@/components/ChatInterface";
import { View } from "react-native";

export default function ChatModal() {
  return (
    <View className="flex-1 bg-white">
      <ChatInterface />
    </View>
  );
}
