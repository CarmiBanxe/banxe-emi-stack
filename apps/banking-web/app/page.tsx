// SANDBOX: Banking Engine Web UI — no live banking data.
import { BankingChat } from "@/components/BankingChat";
import { SandboxBanner } from "@/components/SandboxBanner";

export default function HomePage() {
  return (
    <div className="flex h-screen flex-col">
      <SandboxBanner />
      <header className="border-b border-border px-6 py-3">
        <h1 className="text-lg font-semibold">Banxe Banking Engine</h1>
        <p className="text-xs text-muted-foreground">Sandbox — LangGraph backend · banxe-general model</p>
      </header>
      <main className="flex flex-1 flex-col overflow-hidden">
        <BankingChat />
      </main>
    </div>
  );
}
