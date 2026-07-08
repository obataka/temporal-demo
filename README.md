# Temporal × CrewAI: Durable Multi-Agent Workflows with Strict Human Governance

*A reference implementation for running multi-agent LLM systems under hard human-approval gates — built on Temporal for durable state and explicit retry policy.*

---

## Why This Exists

Most "AI agent" demos share three properties that make them unfit for production: they hold state in process memory, they treat human approval as an optional UI affordance rather than a hard gate, and they have no answer for what happens when a call to the LLM provider times out at 2am. In a real deployment, approval waits legitimately span days, LLM calls fail routinely on rate limits and transient errors, and Human-in-the-Loop cannot be implemented as polling without inheriting the failure modes of a distributed system you never admitted to building. This repository is a reference implementation of an architecture that **survives process death, deploys, and crashes; handles failure under an explicit retry policy; and blocks on human judgment for an unbounded period** — without hand-rolling that infrastructure.

---

## Design Patterns Demonstrated

The four patterns below are implemented in `workflows/sop_workflow.py` / `activities/fix_sop_activity.py`. For the full design rationale, see the [technical article](technical-article-temporal-crewai-hitl.md).

### 1. Deterministic Sandbox Isolation
A Temporal Workflow is *replayed* from its Event History whenever a Worker restarts, which means the workflow function itself must be deterministic. CrewAI is not sandbox-safe — it imports `os` directly and makes network calls — so it is never imported at the workflow module level. It is passed through explicitly and only ever invoked from inside an Activity, which is allowed side effects and is retried independently by the runtime.

```python
# workflows/sop_workflow.py:35-43 (excerpt)
with workflow.unsafe.imports_passed_through():
    from activities.sop_activity import generate_sop_phase_activity
    ...
    from activities.fix_sop_activity import (
        fix_sop_with_crew_activity,
        writer_task_activity,
        reviewer_task_activity,
    )
    ...
```

### 2. Push-based Human-in-the-Loop
Approval gates block on a `Signal` + `wait_condition`, not a poll. A Signal delivered while the preceding Activity is still executing is not lost — `wait_condition` picks it up the instant control returns to the workflow.

```python
# workflows/sop_workflow.py:209
await workflow.wait_condition(lambda: self._signal_received)
```

### 3. Activity-grained Multi-Agent Execution
CrewAI's Writer and Reviewer are not bundled into a single `Crew.kickoff()`; they run as separate Activities. If the Reviewer's LLM call fails, only the Reviewer Activity is retried — the Writer's already-committed output is not re-run or re-billed.

```python
# activities/fix_sop_activity.py:253 / :348
async def writer_task_activity(...) -> LLMResult: ...
async def reviewer_task_activity(...) -> LLMResult: ...
```

### 4. Zero-Downtime Versioning
`workflow.patched()` switches a code path for new workflow instances without breaking instances already in flight. This was used in production when the fix-loop was refactored from a single CrewAI `kickoff()` into two separate Activities (commit `f79ddfc`) — workflows already running at deploy time kept using the old path.

```python
# workflows/sop_workflow.py:382-389
if workflow.patched("split-writer-reviewer"):
    return await self._call_fix_decomposed(sop_text, failures, human_feedback)
return await workflow.execute_activity(
    fix_sop_with_crew_activity,
    args=[sop_text, failures, human_feedback, self._fix_attempt],
    start_to_close_timeout=timedelta(minutes=7),
    retry_policy=LLM_RETRY_POLICY,
)
```

---

## Quick Start

```bash
# Set environment variables
echo "GEMINI_API_KEY=your_key_here" > .env

# Start the full stack (Temporal + Worker + Prometheus + Grafana)
docker compose up --build -d

# Run the Gemini-backed workflow
python run_workflow.py "Explain three principles of AI agent design"

# Mock mode (no API key required)
python run_workflow.py --mock "any prompt"

# Mock vs Gemini comparison demo
python run_comparison.py "Explain how to design highly reliable systems"
```

## Docker Compose Setup

`docker compose up` brings up a production-shaped, multi-container stack — no manual bootstrap steps beyond setting `GEMINI_API_KEY`.

| Service | Role |
|---|---|
| `postgresql` | Persistent store backing the Temporal server |
| `temporal` | Temporal server (gRPC frontend) |
| `temporal-ui` | Temporal Web UI |
| `temporal-init` | One-shot init container (`temporalio/admin-tools`) that registers custom Search Attributes (e.g. `Total_Tokens`) before the worker starts |
| `worker` | Runs the workflows/activities and exposes Prometheus metrics |
| `prometheus` | Scrapes worker metrics |
| `grafana` | Cost/latency dashboards over the Prometheus data |
| `web-ui` | HITL approval dashboard (Bun/Hono) |

`temporal-init` removes the manual "register this Search Attribute by hand" step that most Temporal demos require — the stack is queryable by token cost the moment it's up.

## Endpoints

| Service | URL |
|---|---|
| Temporal UI | http://localhost:8080 |
| Grafana Dashboard | http://localhost:3001 |
| Prometheus | http://localhost:9090 |
| Worker Metrics | http://localhost:8000/metrics |

---

## Reference Implementation: SOP Auto-Improvement Pipeline

The domain implemented by `workflows/sop_workflow.py` (`sop_generation_workflow`) is incidental — the patterns are the point. An LLM drafts an SOP in three phases; a human approves or sends back feedback at each phase; an autonomous fix loop (CrewAI Writer/Reviewer) resolves validation failures; and a final human gate approves the resulting GitHub PR.

```
Phase 1-3: outline → draft → review   (blocks on an approval Signal per phase)
Phase 4:   autonomous_fix              (validation → CrewAI fix, up to 3 attempts)
Phase 5:   github_pr                   (blocks on an approval Signal when require_approval=True)
```

All four human judgment gates are hard gates enforced by `@workflow.signal` — none are advisory.

## Immortal AI Agent Demo Architecture

A simpler demo (`ai_agent_workflow`), separate from the SOP pipeline above, is included for verifying the minimal shape of fault-tolerant Gemini calls and cost observability.

```
run_workflow.py ──gRPC──▶ Temporal Server
                               │
                        Task dispatch (Pull)
                               │
                               ▼
                         Worker Container
                    ┌─── ai_agent_workflow
                    │         └── call_llm_activity ──▶ Gemini API
                    │         └── call_mock_llm_activity
                    └─── observability.py
                              ├── structlog (JSON logs)
                              └── prometheus_client
                                       │
                              :8000/metrics ──▶ Prometheus ──▶ Grafana
```

Full architecture diagram (Mermaid): [`docs/architecture_diagram.md`](docs/architecture_diagram.md)

---

## Business Value

**Why this architecture reduces operating cost and improves reliability in production:**

- **Zero-operations recovery from LLM failures.**
  Temporal's Event History lets the workflow retry transient LLM failures (rate limits, timeouts, network errors) automatically to completion. No on-call engineer has to manually re-run a job at 2am, and the retry policy is declared once and enforced by the runtime rather than scattered across call sites.

- **Real-time LLM cost visibility to avoid vendor lock-in.**
  Prometheus + Grafana track cost per model (`OpEx by Model` panel) at second-level granularity. The dashboard makes the cost impact of a model switch visible before you commit to it, turning vendor negotiation and provider migration into a quantitative decision.

- **A reproducible, observable system for audit and compliance.**
  Every LLM call is logged as structured JSON via structlog, and per-workflow token consumption is persisted as a Temporal Search Attribute (`Total_Tokens`), queryable in the Temporal UI. Between `docker compose logs` and the Temporal UI, there is a complete audit trail of when a call was made, against which model, and how many tokens it used — sufficient for cost allocation, security audits, and SLA evidence.

---

## Key Design Decisions

| Pattern | Implementation | Reason |
|---|---|---|
| Interceptor | `log_llm_interaction` context manager | Separates LLM logic from observability |
| Sandbox Isolation | `core/models.py` kept free of structlog | Preserves the Temporal Workflow's deterministic execution guarantee |
| Strategy | `use_mock` flag switches Gemini ↔ Mock | Same code path runs in CI and in demos |
| Init Container | `temporalio/admin-tools` auto-registers Search Attributes | The stack is fully queryable with a single `docker compose up` |
| Gauge for pricing | `llm_price_per_million_tokens` Gauge + PromQL join | No PromQL changes needed when a per-token price changes |

Details: [`ARCHITECTURE.md`](ARCHITECTURE.md) / Cost design: [`docs/costs.md`](docs/costs.md)

---

## Deep Dive

- **Full design rationale**: [technical-article-temporal-crewai-hitl.md](technical-article-temporal-crewai-hitl.md)
- **Architecture document**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Cost model & pricing management**: [docs/costs.md](docs/costs.md)

## Live Demo

- **Reference Architecture & Demo Video**: https://project-sy5bk-qyr66bsfr-obataka123.vercel.app/lp.html
