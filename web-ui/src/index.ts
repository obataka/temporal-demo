import { Hono } from "hono";
import { serveStatic } from "hono/bun";
import { Client, Connection } from "@temporalio/client";

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
    const handle = client.workflow.getHandle(workflowId);
    const status = await handle.query<Record<string, unknown>>("get_status");
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
    const handle = client.workflow.getHandle(workflowId);
    await handle.signal("approve_pr");
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
    const handle = client.workflow.getHandle(workflowId);
    await handle.signal("reject_with_feedback", { comment: feedbackComment });
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

app.use("/*", serveStatic({ root: "./public" }));

export default { port: 3000, fetch: app.fetch };
