# Architecture Diagrams — The Immortal AI Agent

## 1. System Component Diagram

```mermaid
graph TB
    subgraph Client ["Client Layer"]
        CLI["run_workflow.py<br/>(CLI Trigger)"]
        CMP["run_comparison.py<br/>(Comparison Demo)"]
    end

    subgraph Temporal ["Temporal Server :7233"]
        SRV["Temporal Server<br/>(State Persistence / Event History)"]
        UI["Temporal UI :8080<br/>(Search Attributes Filter)"]
        INIT["temporal-init<br/>(Search Attribute Setup)"]
    end

    subgraph Worker ["Worker Container :8000"]
        WF1["ai_agent_workflow"]
        WF2["comparison_workflow"]
        ACT1["call_llm_activity<br/>(Gemini 2.5 Flash)"]
        ACT2["call_mock_llm_activity<br/>(Mock LLM)"]
        OBS["core/observability.py<br/>(structlog + Prometheus)"]
    end

    subgraph Observability ["Observability Stack"]
        PROM["Prometheus :9090<br/>(Metrics Scrape / TSDB)"]
        GRAF["Grafana :3000<br/>(Dashboard / Visualization)"]
    end

    subgraph External ["External Services"]
        GEMINI["Google Gemini API<br/>(gemini-2.5-flash)"]
    end

    CLI -->|"gRPC :7233<br/>execute_workflow()"| SRV
    CMP -->|"gRPC :7233<br/>execute_workflow()"| SRV
    SRV -->|"Task dispatch<br/>(Pull model)"| WF1
    SRV -->|"Task dispatch<br/>(Pull model)"| WF2
    WF1 -->|"execute_activity()"| ACT1
    WF1 -->|"execute_activity()"| ACT2
    WF2 -->|"parallel activities"| ACT1
    WF2 -->|"parallel activities"| ACT2
    ACT1 --> OBS
    ACT2 --> OBS
    ACT1 -->|"HTTPS / REST"| GEMINI
    OBS -->|"metrics :8000/metrics"| PROM
    PROM -->|"PromQL queries"| GRAF
    INIT -->|"Register Search Attributes"| SRV
    UI --> SRV

    style Temporal fill:#e8f4fd,stroke:#2196F3
    style Worker fill:#e8f5e9,stroke:#4CAF50
    style Observability fill:#fff3e0,stroke:#FF9800
    style External fill:#fce4ec,stroke:#E91E63
    style Client fill:#f3e5f5,stroke:#9C27B0
```

---

## 2. Workflow Execution Sequence

```mermaid
sequenceDiagram
    actor User
    participant CLI as run_workflow.py
    participant TS as Temporal Server
    participant W as Worker
    participant WF as ai_agent_workflow
    participant ACT as call_llm_activity
    participant LLM as Gemini API
    participant OBS as observability.py
    participant PROM as Prometheus

    User->>CLI: python run_workflow.py "prompt"
    CLI->>TS: execute_workflow(ai_agent_workflow, prompt)
    TS-->>CLI: workflow_id (returns immediately)

    TS->>W: Dispatch workflow task
    W->>WF: run(prompt, use_mock=False)
    WF->>TS: upsert_search_attributes(LLM_Status="Running")

    WF->>TS: schedule_activity(call_llm_activity)
    TS->>W: Dispatch activity task
    W->>ACT: call_llm_activity(prompt)

    ACT->>OBS: log_llm_interaction(model, prompt)
    ACT->>LLM: generate_content(prompt)

    alt Success
        LLM-->>ACT: LLMResult (text, tokens, latency)
        ACT->>OBS: result_box.append(result)
        OBS->>OBS: llm_tokens_total.inc()<br/>latency_histogram.observe()
        OBS->>OBS: structlog.info(llm_interaction)
        ACT-->>WF: return LLMResult
        WF->>TS: upsert_search_attributes(LLM_Status="Success")
    else Failure (retry)
        LLM-->>ACT: Exception (rate limit / timeout)
        ACT->>OBS: structlog.error(llm_interaction)
        ACT-->>TS: Activity failed
        TS->>TS: Apply RetryPolicy<br/>(backoff: 2s → 4s → 8s)
        TS->>W: Re-dispatch activity task
        Note over TS,W: Up to max_attempts=3
    end

    PROM->>OBS: GET /metrics (every 15s scrape)
    OBS-->>PROM: llm_tokens_total, latency_histogram
    CLI-->>User: Print LLM response + Temporal UI URL
```

---

## 3. Comparison Workflow Sequence (Mock vs Gemini)

```mermaid
sequenceDiagram
    participant CMP as run_comparison.py
    participant TS as Temporal Server
    participant WF as comparison_workflow
    participant MOCK as call_mock_llm_activity
    participant REAL as call_llm_activity
    participant GEMINI as Gemini API

    CMP->>TS: execute_workflow(comparison_workflow, prompt)
    TS->>WF: run(prompt)
    WF->>TS: upsert(LLM_Status="Running")

    par Parallel Activity Execution
        WF->>TS: schedule(call_mock_llm_activity)
        TS->>MOCK: call_mock_llm_activity(prompt)
        MOCK->>MOCK: asyncio.sleep(0.3~1.5s)<br/>random tokens
        MOCK-->>WF: LLMResult (mock-llm-v1)
    and
        WF->>TS: schedule(call_llm_activity)
        TS->>REAL: call_llm_activity(prompt)
        REAL->>GEMINI: generate_content(prompt)
        GEMINI-->>REAL: real response + token count
        REAL-->>WF: LLMResult (gemini-2.5-flash)
    end

    WF->>TS: upsert(LLM_Model="comparison", Total_Tokens=combined)
    WF-->>CMP: {"mock": {...}, "gemini": {...}}
    CMP->>CMP: Print side-by-side comparison table
```

---

## 4. Observability Data Flow

```mermaid
flowchart LR
    subgraph Worker ["Worker Process"]
        ACT["Activity Execution"]
        CTX["log_llm_interaction<br/>(Context Manager)"]
        CNT["llm_tokens_total<br/>(Counter)"]
        HIST["llm_inference_latency<br/>(Histogram)"]
        GAUGE["llm_price_per_million<br/>(Gauge — set at boot)"]
        LOG["structlog JSON<br/>(stdout)"]
        HTTP["/metrics endpoint<br/>:8000"]
    end

    subgraph Storage ["Time-Series Storage"]
        TSDB["Prometheus TSDB<br/>(in-memory + WAL)"]
    end

    subgraph Visualization ["Grafana Dashboard"]
        P1["Cumulative Token<br/>Consumption (Stat)"]
        P2["Real-time OpEx<br/>USD (Stat)"]
        P3["Model Cost<br/>Breakdown (Pie)"]
        P4["Avg Latency<br/>(Time Series)"]
        P5["OpEx Over Time<br/>(Time Series)"]
        P6["Token Rate<br/>(Time Series)"]
    end

    ACT -->|"LLMResult"| CTX
    CTX --> CNT
    CTX --> HIST
    CTX --> LOG
    CNT --> HTTP
    HIST --> HTTP
    GAUGE --> HTTP
    HTTP -->|"scrape / 15s"| TSDB
    TSDB -->|"sum(llm_tokens_total)"| P1
    TSDB -->|"tokens * price / 1M"| P2
    TSDB -->|"sum by model (join)"| P3
    TSDB -->|"rate(sum) / rate(count)"| P4
    TSDB -->|"cumulative join"| P5
    TSDB -->|"rate * 60"| P6
```
