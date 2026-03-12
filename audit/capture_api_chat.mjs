import { POST } from "../frontend/app/api/chat/route.ts";

const payloadJson = process.argv[2];
const backendUrl = process.argv[3];

if (!payloadJson || !backendUrl) {
  throw new Error("Usage: node capture_api_chat.mjs '<payload-json>' '<backend-url>'");
}

const payload = JSON.parse(payloadJson);
const originalFetch = globalThis.fetch;

globalThis.fetch = async (input, init) => {
  const target =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;

  if (target === "http://localhost:8000/run") {
    return originalFetch(backendUrl, init);
  }
  return originalFetch(input, init);
};

const request = new Request("http://audit.local/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

const response = await POST(request);
const text = await response.text();

let body;
try {
  body = JSON.parse(text);
} catch {
  body = { raw_text: text };
}

process.stdout.write(
  JSON.stringify({
    status_code: response.status,
    content_type: response.headers.get("content-type"),
    ok: response.ok,
    body,
  }),
);
