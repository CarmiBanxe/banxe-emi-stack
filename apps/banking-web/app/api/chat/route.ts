// SANDBOX: Streams from LiteLLM :4000 (banxe-general) — no live banking data.
// API key is read from environment, never hardcoded.
import { createOpenAI } from "@ai-sdk/openai";
import { streamText } from "ai";

// Allow streaming responses up to 30 seconds (sandbox; adjust for production).
export const maxDuration = 30;

const SANDBOX_SYSTEM_PROMPT = `You are the Banxe Banking Engine assistant running in SANDBOX MODE.

SANDBOX CONSTRAINTS:
- All data is synthetic test data. Never reference real customers, accounts, or transactions.
- You assist with banking operations queries using the sandbox LangGraph backend.
- No real payments or account changes are made in sandbox mode.
- For every response, remind the user this is sandbox data if they ask about balances or transactions.

You can help with: account balance queries (sandbox), transaction history (synthetic), payment intent simulation, and general banking questions.`;

export async function POST(req: Request) {
  const { messages } = await req.json();

  // All config from environment — no hardcoded secrets (BANXE security rule).
  const litellm = createOpenAI({
    baseURL: process.env.LITELLM_BASE_URL ?? "http://localhost:4000/v1",
    apiKey: process.env.LITELLM_API_KEY ?? "sandbox-key",
  });

  const model = process.env.BANKING_MODEL ?? "banxe-general";

  const result = streamText({
    model: litellm(model),
    system: SANDBOX_SYSTEM_PROMPT,
    messages,
  });

  return result.toDataStreamResponse();
}
