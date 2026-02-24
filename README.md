# Spec-Driven API Testing Agent

An autonomous QA agent that reads **only a minimal YAML config**, discovers all APIs from specs, generates test cases with an LLM, executes them against a live server, validates responses against schemas, and produces rich reports — all without the user writing a single test.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Quick Start](#quick-start)
3. [How It Works — End to End](#how-it-works--end-to-end)
4. [User Config (`guideline_testing.yaml`)](#user-config-guideline_testingyaml)
5. [Agent Pipeline — 5 Phases](#agent-pipeline--5-phases)
   - [Phase 1 · DISCOVER](#phase-1--discover)
   - [Phase 2 · GENERATE](#phase-2--generate)
   - [Phase 3 · EXECUTE](#phase-3--execute)
   - [Phase 4 · VALIDATE](#phase-4--validate)
   - [Phase 5 · REPORT](#phase-5--report)
6. [LangGraph State](#langgraph-state)
7. [Tools Reference](#tools-reference)
8. [Source of Truth — Specs](#source-of-truth--specs)
9. [Go Server](#go-server)
10. [Reports](#reports)
11. [Adding a New Service](#adding-a-new-service)
12. [Makefile Commands](#makefile-commands)

---

## Project Structure

```
langchain_demo/
│
├── source_of_truth/              ← single source for ALL specs (server + agent)
│   ├── account.yaml              ← OpenAPI 3.0 spec
│   └── account.proto             ← gRPC proto definition
│
├── guideline_testing.yaml        ← ONLY file the user needs to edit
│
├── agent/                        ← Python LangGraph agent
│   ├── main.py                   ← CLI entry point
│   ├── graph.py                  ← LangGraph pipeline (5 nodes)
│   ├── config.py                 ← loads guideline + env vars → Settings
│   ├── state.py                  ← AgentState / TestCase / TestResult TypedDicts
│   │
│   ├── parsers/
│   │   ├── openapi_parser.py     ← OpenAPI 3.x → list[APIEndpoint]
│   │   └── proto_parser.py       ← .proto → list[APIEndpoint]
│   │
│   ├── tools/                    ← LangChain @tool functions
│   │   ├── load_spec_tool.py     ← scans source_of_truth/ for a service
│   │   ├── discover_apis_tool.py ← parses specs → APIEndpoint list
│   │   ├── generate_test_cases_tool.py  ← LLM → TestCase list
│   │   ├── http_call_tool.py     ← executes one HTTP TestCase
│   │   ├── grpc_call_tool.py     ← executes one gRPC TestCase
│   │   ├── schema_validate_tool.py      ← jsonschema validation on responses
│   │   └── report_builder_tool.py       ← builds + saves report files
│   │
│   ├── executor/
│   │   ├── rest_executor.py      ← concurrent HTTP batch runner (httpx + ThreadPool)
│   │   └── grpc_executor.py      ← concurrent gRPC batch runner (grpcio + ThreadPool)
│   │
│   ├── report/
│   │   ├── json_report.py        ← JSON output
│   │   ├── html_report.py        ← styled HTML table (Jinja2)
│   │   └── markdown_report.py    ← Markdown summary
│   │
│   └── grpc_stubs/               ← generated Python gRPC stubs (artifact)
│       ├── account_pb2.py
│       └── account_pb2_grpc.py
│
├── server/                       ← Go HTTP + gRPC server
│   ├── main.go                   ← starts :8080 (HTTP) + :9090 (gRPC)
│   ├── handler/
│   │   ├── http.go               ← net/http handlers
│   │   └── grpc.go               ← gRPC service implementation
│   ├── service/account_service.go
│   ├── store/account_store.go    ← in-memory store
│   ├── model/account.go
│   └── proto/account/            ← generated Go stubs (artifact)
│
├── reports/                      ← generated test reports (created at runtime)
├── requirements.txt
├── Makefile
└── setup.sh
```

---

## Quick Start

```bash
# 1. Bootstrap (first time only)
cp .env.example .env              # then add your OPENAI_API_KEY inside
bash setup.sh                     # creates .venv, installs deps, generates stubs

# 2. Start the Go server (separate terminal)
cd server && go run .
# HTTP → :8080   gRPC → :9090

# 3. Run the agent
source .venv/bin/activate
python -m agent.main
```

Reports are saved to `reports/` as JSON, HTML, and Markdown.

---

## How It Works — End to End

```
User writes guideline_testing.yaml
           │
           ▼
    agent/main.py
    reads guideline → for each service entry → agent/graph.py
           │
           ▼
  ┌────────────────────────────────────────────────────────────┐
  │                    LangGraph Pipeline                      │
  │                                                            │
  │  DISCOVER → GENERATE → EXECUTE → VALIDATE → REPORT        │
  │                                                            │
  └────────────────────────────────────────────────────────────┘
           │
           ▼
     reports/<service>_report.{json,html,md}
```

The agent carries a single **`AgentState`** dict through every phase — no global variables, no side-channel communication.

---

## User Config (`guideline_testing.yaml`)

This is the **only** file a user ever edits:

```yaml
test_services:
  - service: account        # service name to test
    scenario: basic validation

agent:
  model: gpt-4o             # OpenAI model for test generation
  temperature: 0
  max_iterations: 30

execution:
  base_url_http: http://localhost:8080
  base_url_grpc: localhost:9090
  timeout_seconds: 10
  retry_attempts: 2
  concurrency: 4            # parallel test execution threads

report:
  output_dir: reports/
  formats: [json, html, markdown]
  save_to_file: true
```

No endpoints. No schemas. No test code.

---

## Agent Pipeline — 5 Phases

### Phase 1 · DISCOVER

**Node:** `node_discover` in `agent/graph.py`  
**Tools used:** `load_spec_tool` → `discover_apis_tool`

```
service name ("account")
        │
        ▼
load_spec_tool
  scans source_of_truth/account.yaml  → OpenAPI spec path
  scans source_of_truth/account.proto → proto path
        │
        ▼
discover_apis_tool
  openapi_parser.parse()  → [GET /accounts, POST /accounts, GET /accounts/{id}]
  proto_parser.parse()    → [GRPC AccountService/CreateAccount, ...]
        │
        ▼
AgentState.apis = [APIEndpoint, ...]
```

**`APIEndpoint`** shape:
```python
{
  "api_id":          "GET /accounts/{id}",
  "method":          "GET",
  "path":            "/accounts/{id}",
  "operation_id":    "getAccountById",
  "summary":         "Get account by ID",
  "parameters":      [{"name": "id", "in": "path", "required": True, ...}],
  "request_schema":  None,
  "response_schemas":{"200": {...Account schema...}, "404": {...}},
  "tags":            ["accounts"],
  "source":          "openapi"   # or "proto"
}
```

---

### Phase 2 · GENERATE

**Node:** `node_generate` in `agent/graph.py`  
**Tool used:** `generate_test_cases_tool`

The full `APIEndpoint` list is sent to the LLM with a structured system prompt. The LLM reasons about each endpoint and returns a JSON array of test cases covering:

| Category | Examples |
|----------|----------|
| **Positive** | valid payload with all fields, required fields only, boundary values |
| **Negative** | missing required field, wrong type, invalid format (bad email / bad UUID), empty string, value out of range |
| **Schema** | valid request that checks the 2xx response matches the declared schema |

**`TestCase`** shape:
```python
{
  "test_id":         "tc_001",
  "api_id":          "POST /accounts",
  "test_type":       "positive",        # positive | negative | schema
  "description":     "Create account with valid name and email",
  "method":          "POST",
  "path":            "/accounts",
  "headers":         {"Content-Type": "application/json"},
  "path_params":     {},
  "query_params":    {},
  "body":            {"name": "Alice", "email": "alice@example.com"},
  "expected_status": 201,
  "expected_schema": { ...Account JSON Schema... },
  "transport":       "http"             # http | grpc
}
```

> **No hardcoded rules** — the LLM decides what edge cases to probe based on the schema constraints it reads (minLength, format: email, required fields, enums, etc.).

State after this phase: `AgentState.generated_tests = [TestCase, ...]`

---

### Phase 3 · EXECUTE

**Node:** `node_execute` in `agent/graph.py`  
**Tools used:** `rest_executor.run_batch` / `grpc_executor.run_batch`

Test cases are split by `transport` field and run concurrently:

```
generated_tests
      │
      ├── transport="http"  →  rest_executor.run_batch()
      │       uses httpx.Client, retries up to retry_attempts
      │       concurrency = ThreadPoolExecutor(max_workers=4)
      │
      └── transport="grpc"  →  grpc_executor.run_batch()
              uses grpcio stub from agent/grpc_stubs/
              concurrency = ThreadPoolExecutor(max_workers=4)
```

**`TestResult`** shape after execution:
```python
{
  "test_id":          "tc_001",
  "api_id":           "POST /accounts",
  "test_type":        "positive",
  "description":      "Create account with valid name and email",
  "status":           "passed",         # passed | failed | error
  "expected_status":  201,
  "actual_status":    201,
  "latency_ms":       87.4,
  "response_body":    {"id": "abc123", "name": "Alice", ...},
  "validation_errors":[],
  "error":            None
}
```

---

### Phase 4 · VALIDATE

**Node:** `node_validate` in `agent/graph.py`  
**Tool used:** `schema_validate_tool`

For every `TestResult` that has an `expected_schema` in its matching `TestCase`:

```
result.response_body
        │
        ▼
jsonschema.Draft7Validator(expected_schema).iter_errors(response_body)
        │
        ├── no errors  → validation_errors = [],  status unchanged
        └── errors     → validation_errors = ["..."], status downgraded to "failed"
```

This catches cases where the server returns HTTP 200 but with a **wrong or incomplete body shape**.

---

### Phase 5 · REPORT

**Node:** `node_report` in `agent/graph.py`  
**Tool used:** `report_builder_tool`

Aggregates all `TestResult` objects and writes up to 3 formats:

```
results[]
    │
    ▼
_compute_metrics()
    total, passed, failed, pass_rate_pct, avg_latency_ms, by_type{}
    │
    ▼
report dict  ─┬─► json_report.py   → reports/account_report.json
              ├─► html_report.py   → reports/account_report.html
              └─► markdown_report.py → reports/account_report.md
```

**Report JSON structure:**
```json
{
  "service": "account",
  "total_apis": 3,
  "total_tests": 15,
  "passed": 13,
  "failed": 2,
  "pass_rate_pct": 86.7,
  "avg_latency_ms": 94.2,
  "metrics_by_type": {
    "positive": { "total": 6, "passed": 6, "failed": 0 },
    "negative": { "total": 7, "passed": 5, "failed": 2 },
    "schema":   { "total": 2, "passed": 2, "failed": 0 }
  },
  "details": [
    {
      "test_id": "tc_001",
      "api_id": "POST /accounts",
      "test_type": "positive",
      "description": "Create account with valid name and email",
      "status": "passed",
      "expected_status": 201,
      "actual_status": 201,
      "latency_ms": 87.4,
      "response_body": { "id": "...", "name": "Alice", "email": "alice@example.com" },
      "validation_errors": [],
      "error": null
    }
  ]
}
```

---

## LangGraph State

`AgentState` is the single dict threaded through every node. Nothing is stored outside it.

```
AgentState
│
├── messages          list[BaseMessage]   LLM conversation history
├── service           str                 "account"
├── scenario          str                 "basic validation"
│
├── spec_path         str | None          resolved path
├── spec_type         str | None          "openapi" | "proto" | "both"
├── raw_spec          dict | None         parsed OpenAPI dict
│
├── apis              list[APIEndpoint]   populated after DISCOVER
├── generated_tests   list[TestCase]      populated after GENERATE
├── results           list[TestResult]    populated after EXECUTE + VALIDATE
├── metrics           dict                populated after REPORT
│
├── report            dict | None         final report dict
├── report_paths      list[str]           saved file paths
│
├── phase             str                 current phase (controls routing)
└── error             str | None          stops pipeline if set
```

**State routing** (`agent/graph.py :: route()`):

```
phase="discover"  →  node_discover
phase="generate"  →  node_generate
phase="execute"   →  node_execute
phase="validate"  →  node_validate
phase="report"    →  node_report
phase="done"      →  END
error is set      →  END  (short-circuit)
```

---

## Tools Reference

| Tool | Input | Output | Used in phase |
|------|-------|--------|---------------|
| `load_spec_tool` | `service_name: str` | `{openapi_path, proto_path, openapi_raw, spec_type}` | DISCOVER |
| `discover_apis_tool` | `openapi_path, proto_path` | `list[APIEndpoint]` | DISCOVER |
| `generate_test_cases_tool` | `apis: list[APIEndpoint]` | `list[TestCase]` | GENERATE |
| `http_call_tool` | `test_case: TestCase` | `TestResult` | EXECUTE (single) |
| `grpc_call_tool` | `test_case: TestCase` | `TestResult` | EXECUTE (single) |
| `schema_validate_tool` | `results, generated_tests` | `list[TestResult]` (enriched) | VALIDATE |
| `report_builder_tool` | `service, apis, results` | `{report, report_paths}` | REPORT |

> `http_call_tool` and `grpc_call_tool` are also available as standalone LangChain tools for direct agent invocation. The pipeline uses the batch executors (`rest_executor`, `grpc_executor`) for concurrency.

---

## Source of Truth — Specs

All service contracts live in `source_of_truth/`. Both the Go server and the Python agent read from here:

```
source_of_truth/
├── account.yaml      ← OpenAPI 3.0   (parsed by openapi_parser.py)
└── account.proto     ← gRPC proto    (parsed by proto_parser.py + used to gen stubs)
```

**When you change a spec:**

```bash
# Regenerate Python stubs (agent)
make proto

# Regenerate Go stubs (server)
make proto-go

# Or regenerate both
make proto proto-go
```

Generated artifacts (never edit manually):

| Path | What |
|------|------|
| `agent/grpc_stubs/account_pb2.py` | Python protobuf messages |
| `agent/grpc_stubs/account_pb2_grpc.py` | Python gRPC service stub |
| `server/proto/account/account.pb.go` | Go protobuf messages |
| `server/proto/account/account_grpc.pb.go` | Go gRPC service stub |

---

## Go Server

Runs at `http://localhost:8080` (HTTP) and `localhost:9090` (gRPC).

| Operation | HTTP | gRPC |
|-----------|------|------|
| Create account | `POST /accounts` | `AccountService/CreateAccount` |
| Get account by ID | `GET /accounts/{id}` | `AccountService/GetAccount` |
| List accounts | `GET /accounts` | `AccountService/ListAccounts` |

```bash
cd server && go run .
```

---

## Reports

After a run, `reports/` contains:

| File | Format | Use |
|------|--------|-----|
| `account_report.json` | Machine-readable | CI pipelines, dashboards |
| `account_report.html` | Styled table | Open in browser for visual review |
| `account_report.md` | Markdown | Paste into GitHub PRs / Notion |

---

## Adding a New Service

1. **Add the spec** to `source_of_truth/`:
   - `source_of_truth/payment.yaml` (OpenAPI) and/or
   - `source_of_truth/payment.proto` (gRPC)

2. **Regenerate stubs** (if proto):
   ```bash
   make proto proto-go
   ```

3. **Add one line** to `guideline_testing.yaml`:
   ```yaml
   test_services:
     - service: account
       scenario: basic validation
     - service: payment          # ← add this
       scenario: basic validation
   ```

4. **Run**:
   ```bash
   python -m agent.main
   ```

The agent discovers, generates, executes, validates, and reports for all services automatically.

---

## Makefile Commands

| Command | What it does |
|---------|-------------|
| `make setup` | Full bootstrap (venv + pip + stubs) |
| `make install` | `pip install -r requirements.txt` only |
| `make proto` | Regenerate Python gRPC stubs from `source_of_truth/` |
| `make proto-go` | Regenerate Go gRPC stubs from `source_of_truth/` |
| `make server` | Start the Go server |
| `make run` | Run the agent with `guideline_testing.yaml` |
| `make run-service SERVICE=account SCENARIO="edge cases"` | Run for a single service |
| `make clean` | Remove `reports/` and all `__pycache__` dirs |
