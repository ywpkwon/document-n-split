# Deterministic Document Segmentation via Atomic Parsing

This project explores **how to divide a long document into N coherent sections** in a **deterministic, inspectable, and extensible way**, without relying on LLMs to “understand” or rewrite the content.

Rather than treating the problem as text generation, we treat it as **structured document analysis**.

---

## Motivation

Splitting documents sounds simple, but in practice it is ambiguous:

- Where *should* a document be split?
- Should headings always dominate?
- What about lists, tables, or long paragraphs?
- How do we debug or adjust a bad split?

### Key design decisions

#### 1. No LLMs for segmentation
This system **does not generate or modify content**.  
It only **divides** existing content.

Because of that, we intentionally avoid LLM-based heuristics and instead use:

- Deterministic parsing
- Explicit rules
- Reproducible outcomes

This makes the system:
- predictable
- debuggable
- suitable for automation pipelines

#### 2. Atom-first representation
Instead of directly “splitting a document,” we first parse it into **atomic units**:

- headings
- pseudo-headings (e.g. `**Title**`)
- paragraphs
- list blocks
- tables
- code blocks
- horizontal rules
- blanks

Each atom carries metadata:
- position (line, byte, index)
- word/character counts
- loose hierarchical context
- boundary strength (how good a cut this atom represents)

This **atom layer** is the core abstraction.

#### 3. Loose structure, not a rigid tree
Documents are not always well-formed trees.

We therefore model:
- a *pseudo-tree* using heading depth and section paths
- without enforcing strict parent/child constraints

This allows:
- flat documents (e.g. novels)
- semi-structured memos
- messy markdown
- mixed formats

All future logic (splitting, visualization, tuning) operates on atoms.

#### 4. Visualization as a first-class tool
Understanding segmentation decisions is hard without seeing structure.

We therefore add:
- Mermaid-based section diagrams
- optional leaf-level visualization (paragraphs, lists, code, tables)
- segment coloring for split results

Visualization serves two purposes:
- **debugging** (why did this split happen?)
- **future interaction** (manual tweaking, UI-based adjustment)

---

## High-level pipeline

~~~
Raw document
   ↓
Atomization (deterministic)
   ↓
Atoms + pseudo-structure
   ↓
Candidate cut generation
   ↓
N-way partitioning (by word balance)
   ↓
Optional visualization
~~~

---

## Atomization

The parser detects document mode (Markdown vs plain text) and emits a **linear sequence of atoms**.

Each atom includes:
- `atom_type` (heading, paragraph, list, …)
- `weight_words`, `weight_chars`
- `depth` (for headings / pseudo-headings)
- `section_path_ids`
- `can_cut_before` + `boundary_strength`

This representation is intentionally **over-complete** to support future policies.

> Think of atoms as “document pixels”: small, immutable, and composable.

---

## Splitting into N sections

Splitting is framed as:

> Choose **N−1 cut points** from valid boundaries to balance total word count.

### Candidate cuts
Candidates are selected from atoms that are:
- strong boundaries (headings, pseudo-headings, HRs)
- optionally lists / tables / code blocks
- optionally paragraphs (fallback)

Relaxation happens in stages if strict candidates cannot produce N segments.

### Objective
The default objective minimizes deviation from equal word counts across segments, while respecting boundary preferences.

This makes the behavior:
- explainable
- tunable
- extensible

---

## Visualization (Mermaid)

The system can emit a **Mermaid flowchart** showing:

- section hierarchy (from headings)
- optional leaf nodes (paragraphs, lists, code, tables)
- coloring by split segment

This is especially useful when tuning split parameters or validating parser behavior.

### Example (section-level)

~~~mermaid
flowchart TD
    S1["Introduction"]
    S2["Background"]
    S3["Method"]
    S1 --> S2
    S2 --> S3
~~~

---

## Usage

### Parse and inspect atoms
~~~
python main.py --file input.md
~~~

### Split into N sections
~~~
python main.py --file input.md --split 5
~~~

### Export Mermaid diagram
~~~
python main.py --file input.md \
  --split 5 \
  --mermaid-out structure.md \
  --mermaid-leaves
~~~

---

## Summary

- Document segmentation is ambiguous — so we made it explicit.
- We avoid LLMs where generation is unnecessary.
- We parse once, then reason over atoms.
- Visualization is not an afterthought; it’s part of the design.
