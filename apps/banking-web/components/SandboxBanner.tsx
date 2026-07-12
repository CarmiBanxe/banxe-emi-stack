// SANDBOX: visible warning — no live banking data, no real transactions.
export function SandboxBanner() {
  return (
    <div className="w-full bg-sandbox-bg border-b border-sandbox-border px-4 py-2 text-center text-sm font-semibold text-sandbox-text">
      ⚠ SANDBOX MODE — No live banking data. Backend: LangGraph sandbox + LiteLLM :4000. Not for production use.
    </div>
  );
}
