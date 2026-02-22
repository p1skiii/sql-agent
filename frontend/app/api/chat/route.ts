import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const body = await request.json();
  const question = body?.question;
  if (!question || typeof question !== "string") {
    return NextResponse.json({ error: "question is required" }, { status: 400 });
  }

  const resp = await fetch("http://localhost:8000/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, allow_write: body?.allow_write ?? false, dry_run: body?.dry_run ?? true, force: body?.force ?? false }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    return NextResponse.json({ error: text || resp.statusText }, { status: resp.status });
  }

  const data = await resp.json();
  return NextResponse.json({ summary: data.summary ?? data.reason ?? "No response", raw: data });
}
