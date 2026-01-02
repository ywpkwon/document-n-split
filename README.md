# Document Atomizer & Section-Aware Chunking

A lightweight Python tool to **parse documents into atomic units**, infer a
**pseudo-hierarchical structure**, and enable **structure-aware partitioning**
(e.g. dividing a document into *N* balanced sections without touching content or order).

This project is designed as a foundation for:

- document chunking for LLM pipelines
- section-aware summarization
- balanced context-window packing
- structural visualization (Mermaid)
- future algorithmic (non-LLM) partitioning

---

## Motivation

Given:
- a document (Markdown or plain text)
- an integer **N**

We want to:
- divide the document into **N contiguous sections**
- preserve **content and order exactly**
- respect **semantic structure** (headings, pseudo-headings, lists, code blocks)
- avoid brittle heuristics or blind token splitting

Instead of forcing a rigid tree upfront, this project:
- keeps a **linear atom stream**
- annotates atoms with **pseudo-tree metadata**
- reconstructs structure *only when needed*

---

## Core Concepts

### Atom

An **atom** is the smallest indivisible unit allowed for splitting:

- headings
- paragraphs
- list blocks
- tables
- code fences
- horizontal rules
- blank lines

Atoms are never split internally.

---

### Pseudo-Tree Metadata

Each atom is annotated with:

- `section_node_id` — stable identifier of the section it belongs to
- `section_path_ids` — ancestry chain (implicit tree path)
- `section_path` — human-readable titles
- `depth` — structural depth (Markdown level or inferred)
- `can_cut_before` — whether a cut before this atom is allowed
- `boundary_strength` — heuristic importance of the boundary

This gives **tree-like reasoning power without building a tree**.

---

## Project Structure

~~~text
.
├── atomizer.py           # Core atomization logic
├── render.py             # Mermaid diagram rendering
├── run_atomizer.py       # CLI runner
├── README.md
└── examples/
    ├── sample_structure.md
    └── sample_structure.mmd
~~~

---

## Usage

### Run atomizer on a Markdown file

~~~bash
python run_atomizer.py --file sample.md
~~~

This prints a table of atoms with structural metadata.

---

### Export a Mermaid section diagram

~~~bash
python run_atomizer.py \
  --file sample.md \
  --mermaid-out outline.mmd
~~~

Optional flags:

~~~text
--mermaid-no-pseudo     exclude pseudo-headings
--mermaid-stats         include rough section stats
--mermaid-dir LR        layout direction (TD, LR, RL, BT)
~~~

---

## Example: Input Markdown and its Parsing Result (Diagram Visualization)

Input [markdown document](./examples/example_structure.md)

Parsing result:

~~~text
Detected mode: markdown
Num atoms: 66
Num sections: 15
 idx  type           lines       bytes            words  chars dep cut  bnd  sid pid          path                            preview
--------------------------------------------------------------------------------------------------------------------------------------------
   0  heading        0-0         0-31                 5     31   1   1 1.00    1 1            Project Atlas: Strategy Memo    # Project Atlas: Strategy Memo
   1  blank          1-1         31-32                0      1   0   0 0.00    1 1            Project Atlas: Strategy Memo
   2  paragraph      2-3         32-182              22    150   0   0 0.10    1 1            Project Atlas: Strategy Memo    A short, nicely structured sam…
   3  blank          4-4         182-183              0      1   0   0 0.00    1 1            Project Atlas: Strategy Memo
   4  hr             5-5         183-187              1      4   0   1 0.90    1 1            Project Atlas: Strategy Memo    ---
   5  blank          6-6         187-188              0      1   0   0 0.00    1 1            Project Atlas: Strategy Memo
   6  heading        7-7         188-212              4     24   2   1 1.00    2 1/2          Project Atlas: Strategy Mem…    ## 1. Executive Summary
   7  blank          8-8         212-213              0      1   0   0 0.00    2 1/2          Project Atlas: Strategy Mem…
   8  paragraph      9-9         213-280             11     67   0   0 0.10    2 1/2          Project Atlas: Strategy Mem…    **What this is:** A compact me…
   9  blank          10-10       280-281              0      1   0   0 0.00    2 1/2          Project Atlas: Strategy Mem…
  10  pseudo_heading 11-11       281-295              2     14   3   1 0.95    3 1/2/3        Project Atlas: Strategy Mem…    **Key goals**
  11  list           12-14       295-394             20     99   0   1 0.50    3 1/2/3        Project Atlas: Strategy Mem…    - Ship a reliable v1 by Q2 - K…
  12  blank          15-15       394-395              0      1   0   0 0.00    3 1/2/3        Project Atlas: Strategy Mem…
  13  heading        16-16       395-419              4     24   3   1 1.00    4 1/2/4        Project Atlas: Strategy Mem…    ### 1.1 Success Metrics
  14  blank          17-17       419-420              0      1   0   0 0.00    4 1/2/4        Project Atlas: Strategy Mem…
  15  paragraph      18-18       420-447              5     27   0   0 0.10    4 1/2/4        Project Atlas: Strategy Mem…    We will track success via:
...
~~~

Visualization of parsing result:

~~~mermaid
flowchart TD
    S1["Project Atlas: Strategy Memo (atoms 0-65, words=376)"]
    S2["1. Executive Summary (atoms 6-24, words=91)"]
    S3["Key goals (atoms 10-12, words=22)"]
    S4["1.1 Success Metrics (atoms 13-18, words=32)"]
    S5["1.2 Non-Goals (atoms 19-24, words=22)"]
    S6["2. Background & Problem (atoms 25-39, words=85)"]
    S7["2.1 Constraints (atoms 30-33, words=26)"]
    S8["2.2 Assumptions (atoms 34-39, words=33)"]
    S9["3. Proposed Solution (atoms 40-65, words=172)"]
    S10["3.1 Architecture (atoms 45-58, words=99)"]
    S11["High-level components (atoms 47-49, words=20)"]
    S12["3.1.1 Data Flow (atoms 50-53, words=35)"]
    S13["3.1.2 Storage Schema (atoms 54-58, words=41)"]
    S14["3.2 API Sketch (atoms 59-62, words=12)"]
    S15["3.3 Pseudocode (atoms 63-65, words=28)"]
    S1 --> S2
    S1 --> S6
    S1 --> S9
    S2 --> S3
    S2 --> S4
    S2 --> S5
    S6 --> S7
    S6 --> S8
    S9 --> S10
    S9 --> S14
    S9 --> S15
    S10 --> S11
    S10 --> S12
    S10 --> S13
~~~

---

## Mermaid Visualization

The tool can render the inferred section hierarchy as a Mermaid diagram:

- stable section IDs
- parent–child relationships
- optional pseudo-heading inclusion
- optional section span statistics

Useful for:
- debugging structure inference
- UI outline previews
- explaining chunking decisions
- document navigation

---

## Roadmap / TODO

### Atomization (done)

- [x] Markdown heading detection
- [x] Pseudo-heading detection (`**Title**`, ALL CAPS)
- [x] List / table / code-fence grouping
- [x] Stable section IDs
- [x] Section registry (`node_id → atom_idx`)
- [x] Sanity invariants

---

### Structure & Analysis (done)

- [x] Implicit pseudo-tree via `section_path_ids`
- [x] Parent section lookup
- [x] Mermaid rendering

---

### 🚧 Partitioning (next)

**Goal:**  
Divide the atom stream into **N contiguous chunks** by choosing **N−1 boundaries**, without modifying content.

Planned work:

- [ ] Define candidate cut positions (`can_cut_before == True`)
- [ ] Assign per-atom cost (chars / words / tokens)
- [ ] Implement balanced partitioning objective  
  - minimize max chunk size
  - penalize cuts inside strong sections
- [ ] Prefer higher `boundary_strength`
- [ ] Graceful fallback when N is large
- [ ] Deterministic, non-LLM baseline algorithm

---

### Optional Extensions

- [ ] Token-based weights (via tokenizer)
- [ ] Sentence-level fallback atoms
- [ ] Section span precomputation
- [ ] JSON export for downstream pipelines
- [ ] LLM-assisted refinement (optional layer)

---

## Design Philosophy

- **Content is immutable**
- **Structure is inferred, not enforced**
- **Linear first, tree later**
- **Algorithms before prompts**
- **LLMs are optional, not required**

---

## Status

This project currently provides:
- a robust atomization pipeline
- implicit structural reasoning
- Mermaid-based visualization

The **N-partitioning algorithm** is the next major milestone.

