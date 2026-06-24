import { Hono } from "hono";
import { handle } from "hono/vercel";
import { serveStatic } from "hono/bun";
import { Client, Connection } from "@temporalio/client";
import nodemailer from "nodemailer";

const TEMPORAL_ADDRESS = process.env.TEMPORAL_HOST ?? "temporal:7233";

// モジュール起動時に一度だけ gRPC 接続を確立するシングルトン
let clientPromise: Promise<Client> | null = null;

function getClient(): Promise<Client> {
  if (!clientPromise) {
    clientPromise = Connection.connect({ address: TEMPORAL_ADDRESS }).then(
      (connection) => new Client({ connection })
    );
  }
  return clientPromise;
}


const app = new Hono();

app.get("/health", (c) => c.json({ status: "ok" }));

app.get("/api/workflows", async (c) => {
  const limit = Math.min(Number(c.req.query("limit") ?? 30), 100);
  try {
    const client = await getClient();
    const items: object[] = [];
    for await (const wf of client.workflow.list({ pageSize: limit })) {
      items.push({
        workflowId:   wf.workflowId,
        status:       (wf.status as unknown as { name?: string }).name ?? "UNKNOWN",
        startTime:    wf.startTime?.toISOString() ?? null,
        closeTime:    wf.closeTime?.toISOString() ?? null,
        workflowType: wf.type,
      });
    }
    return c.json(items);
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return c.json({ error: message }, 500);
  }
});

app.get("/api/status/:workflowId", async (c) => {
  const workflowId = c.req.param("workflowId");
  try {
    const client = await getClient();
    const wfHandle = client.workflow.getHandle(workflowId);
    const status = await wfHandle.query<Record<string, unknown>>("get_status");
    // Python ワークフローは snake_case で返す可能性があるため両方チェックし string を保証する
    // 将来 get_status が agent_logs / agentLogs を返したとき自動的に中継される
    const agentLogs: string =
      typeof status["agentLogs"] === "string"
        ? status["agentLogs"]
        : typeof status["agent_logs"] === "string"
        ? status["agent_logs"]
        : "";
    return c.json({ ...status, agentLogs });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    // gRPC NOT_FOUND (status code 5) または message 文字列で判定
    const isNotFound =
      message.toLowerCase().includes("not found") ||
      (error as { code?: number }).code === 5;
    if (isNotFound) {
      return c.json({ error: "Workflow not found", workflowId }, 404);
    }
    return c.json({ error: message }, 500);
  }
});

app.post("/api/approve", async (c) => {
  const body = await c.req.json<{ workflowId?: string }>();
  const { workflowId } = body;

  if (!workflowId) {
    return c.json({ error: "workflowId is required" }, 400);
  }

  try {
    const client = await getClient();
    const wfHandle = client.workflow.getHandle(workflowId);
    await wfHandle.signal("approve_pr");
    return c.json({ success: true });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    const isNotFound =
      message.toLowerCase().includes("not found") ||
      (error as { code?: number }).code === 5;
    if (isNotFound) {
      return c.json({ error: "Workflow not found or already completed", workflowId }, 404);
    }
    return c.json({ error: message }, 500);
  }
});

app.post("/api/reject", async (c) => {
  const body = await c.req.json<{ workflowId?: string; feedbackComment?: string }>();
  const { workflowId, feedbackComment } = body;

  if (!workflowId) {
    return c.json({ error: "workflowId is required" }, 400);
  }
  if (!feedbackComment) {
    return c.json({ error: "feedbackComment is required" }, 400);
  }

  try {
    const client = await getClient();
    const wfHandle = client.workflow.getHandle(workflowId);
    await wfHandle.signal("reject_with_feedback", { comment: feedbackComment });
    return c.json({ success: true });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    const isNotFound =
      message.toLowerCase().includes("not found") ||
      (error as { code?: number }).code === 5;
    if (isNotFound) {
      return c.json({ error: "Workflow not found or already completed", workflowId }, 404);
    }
    console.error("[/api/reject]", message);
    return c.json({ error: message }, 500);
  }
});

interface ContactBody {
  name?: string;
  company?: string;
  email?: string;
  message?: string;
  sop_attachment?: boolean;
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

app.post("/api/contact", async (c) => {
  let body: ContactBody;
  try {
    body = await c.req.json<ContactBody>();
  } catch {
    return c.json({ error: "Invalid JSON body" }, 400);
  }

  const { name, company, email, message, sop_attachment } = body;

  if (!name || typeof name !== "string" || name.trim().length === 0 || name.length > 100) {
    return c.json({ error: "お名前は必須です（最大100文字）" }, 400);
  }
  if (!company || typeof company !== "string" || company.trim().length === 0 || company.length > 200) {
    return c.json({ error: "会社名は必須です（最大200文字）" }, 400);
  }
  if (!email || typeof email !== "string" || !EMAIL_REGEX.test(email)) {
    return c.json({ error: "有効なメールアドレスを入力してください" }, 400);
  }
  if (message && typeof message === "string" && message.length > 2000) {
    return c.json({ error: "メッセージは2000文字以内で入力してください" }, 400);
  }

  const notificationEmail = process.env.NOTIFICATION_EMAIL;
  if (!notificationEmail) {
    console.warn("[/api/contact] NOTIFICATION_EMAIL is not set — skipping email send");
    return c.json({ accepted: true, emailed: false });
  }

  const smtpHost = process.env.SMTP_HOST;
  const smtpUser = process.env.SMTP_USER;
  const smtpPass = process.env.SMTP_PASS;

  if (!smtpHost || !smtpUser || !smtpPass) {
    console.warn("[/api/contact] SMTP credentials incomplete — skipping email send");
    return c.json({ accepted: true, emailed: false });
  }

  const smtpPort = Number(process.env.SMTP_PORT ?? 587);
  const fromEmail = process.env.FROM_EMAIL ?? smtpUser;

  try {
    const transporter = nodemailer.createTransport({
      host: smtpHost,
      port: smtpPort,
      secure: smtpPort === 465,
      auth: { user: smtpUser, pass: smtpPass },
    });

    const sopLabel = sop_attachment ? "希望あり" : "希望なし";
    const mailBody = [
      `【SOP Platform Labs — 無償PoC申し込み】`,
      ``,
      `お名前　: ${name.trim()}`,
      `会社名　: ${company.trim()}`,
      `メール　: ${email.trim()}`,
      `手順書Markdown化代行: ${sopLabel}`,
      ``,
      `【メッセージ】`,
      message?.trim() || "（記入なし）",
    ].join("\n");

    await transporter.sendMail({
      from: `"SOP Platform Labs" <${fromEmail}>`,
      to: notificationEmail,
      subject: `[SOP PoC申し込み] ${company.trim()} / ${name.trim()}`,
      text: mailBody,
    });

    return c.json({ accepted: true, emailed: true });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("[/api/contact] SMTP error:", msg);
    return c.json({ error: "Internal error" }, 500);
  }
});

app.use("/*", serveStatic({ root: "./public" }));

// Vercel Serverless Functions (Node.js runtime)
export const GET = handle(app);
export const POST = handle(app);

// Bun HTTP server (local Docker)
export default { port: 3000, fetch: app.fetch };
