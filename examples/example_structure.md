# Project Atlas: Strategy Memo

A short, nicely structured sample document with nested headings (depth 1–3),
lists, a table, and fenced code blocks—useful for testing your atomizer.

---

## 1. Executive Summary

**What this is:** A compact memo describing a product launch plan.

**Key goals**
- Ship a reliable v1 by Q2
- Keep infra costs predictable
- Build a feedback loop with early users

### 1.1 Success Metrics

We will track success via:

- Activation rate (first meaningful action within 10 minutes)
- 7-day retention
- Median latency at p95
- Support tickets per 1k users

### 1.2 Non-Goals

- Building a fully general platform in v1
- Supporting on-prem deployments before we have a hosted baseline

---

## 2. Background & Problem

Users currently struggle to:
- find relevant artifacts quickly,
- understand dependencies among components,
- and collaborate asynchronously without losing context.

### 2.1 Constraints

1. **Privacy:** Some inputs may be sensitive.
2. **Latency:** Interactive workflows should feel instant.
3. **Portability:** Users should export results as plain files.

### 2.2 Assumptions

- We can store metadata (names, sizes) without storing raw user content.
- Most sessions are short (under 5 minutes).
- Batch processing can be deferred to off-peak windows.

---

## 3. Proposed Solution

We will provide a lightweight web UI that indexes local project data and renders:
- a searchable tree view,
- a dependency summary,
- and an “export report” button.

### 3.1 Architecture

**High-level components**
- UI (client-side rendering)
- API gateway (auth + routing)
- Worker (batch indexing)
- Storage (metadata only)

#### 3.1.1 Data Flow

1. User selects a local project directory.
2. Client computes file fingerprints (no uploads by default).
3. Server stores only metadata and derived indices.
4. UI displays structure + search results.

#### 3.1.2 Storage Schema

| Entity     | Key            | Stored fields                     |
|------------|----------------|-----------------------------------|
| Project    | project_id     | name, created_at                  |
| File       | file_id        | path, size, mtime, fingerprint    |
| TensorInfo | tensor_id      | dtype, shape, offset, file_id     |


### 3.2 API Sketch

```http
GET /projects/{project_id}/files?query=...
POST /projects/{project_id}/index
GET /projects/{project_id}/report
```

### 3.3 Pseudocode

```
def build_index(root_dir: str) -> dict:
    files = scan_files(root_dir)
    meta = [extract_metadata(f) for f in files]
    inv  = build_inverted_index(meta)
    return {"files": meta, "index": inv}
```
