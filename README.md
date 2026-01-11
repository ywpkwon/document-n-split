# Deterministic Document Segmentation via Atomic Parsing

This project explores **how to divide a long document into N coherent sections** in a **deterministic, inspectable, and extensible way**, without relying on LLMs to “understand” or rewrite the content.

Rather than treating the problem as text generation, we treat it as **structured document analysis**.

<img width="2500" height="1406" alt="doc-n-split" src="https://github.com/user-attachments/assets/54a03e57-215c-4376-b578-53eb09900dca" />

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
- cost-efficient (no token/inference/hardware cost)

> If needed, we can add LLMs *after* segmentation for optional refinement—e.g., improving inter-segment relationships, ranking split candidates, or tuning split thresholds.

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

<img width="840" height="652" alt="Screenshot 2026-01-11 at 1 44 10 AM" src="https://github.com/user-attachments/assets/0888fb96-a87e-41bf-9aec-d6c00f9e9716" />

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

The final output looks like the following:
```json
{
  "N": 5,
  "objective": [0, 91, 0.0],
  "cuts": [13, 30, 40, 54],
  "segments": [
    {
      "seg_idx": 0,
      "start_atom": 0,
      "end_atom_excl": 13,
      "words": 65,
      "start_path_ids": [1],
      "start_path_titles": ["Project Atlas: Strategy Memo"]
    },
    {
      "seg_idx": 1,
      "start_atom": 13,
      "end_atom_excl": 30,
      "words": 80,
      "start_path_ids": [1,2,4],
      "start_path_titles": [
        "Project Atlas: Strategy Memo",
        "1. Executive Summary",
        "1.1 Success Metrics"
      ]
    },
    ...
}
```

## Visualization (Mermaid)

The system can emit a **Mermaid flowchart** showing:

- section hierarchy (from headings)
- optional leaf nodes (paragraphs, lists, code, tables)
- coloring by split segment

This is especially useful when tuning split parameters or validating parser behavior.

### Example 
Below is an example Mermaid output. For the terminal command to generate the diagram, see **Usage (3)**. The source document is available at [./examples/example_minimal.md](./examples/example_minimal.md), and it is split into **N=3** parts. The diagram includes heading nodes and leaf nodes (paragraph, list, code block, table). Colors represent split groups.

~~~mermaid
%%{init: {"flowchart": {"nodeSpacing": 12, "rankSpacing": 28}} }%%
flowchart TD
classDef sec1 fill:#E3F2FD,stroke:#1E88E5,stroke-width:1px,color:#0D47A1;
classDef sec2 fill:#E8F5E9,stroke:#43A047,stroke-width:1px,color:#1B5E20;
classDef sec3 fill:#FFF3E0,stroke:#FB8C00,stroke-width:1px,color:#E65100;
classDef leafEmpty stroke-width:1px;
classDef leafLabeled stroke-width:1px;
    S1["Mini Example: Deterministic N-Split Demo"]
    S2["1. Background"]
    S3["Constraints"]
    S4["2. Method"]
class S1 sec1;
class S2,S3 sec2;
class S4 sec3;
    A2["P"]
    S1 --> A2
    class A2 leafLabeled;
    class A2 sec1;
    A8["P"]
    S2 --> A8
    class A8 leafLabeled;
    class A8 sec2;
    A11["L"]
    S3 --> A11
    class A11 leafLabeled;
    class A11 sec2;
    A17["P"]
    S4 --> A17
    class A17 leafLabeled;
    class A17 sec3;
    A19["C"]
    S4 --> A19
    class A19 leafLabeled;
    class A19 sec3;
    S1 --> S2
    S1 --> S4
    S2 --> S3
~~~

> In leaf nodes, `P=paragraph, L=list, C=code, T=table`

## Usage

### 1. Parse and inspect atoms

Parse a document into atomic units (headings, paragraphs, lists, code blocks, etc.) and print a structured inspection table. This is useful for understanding how the document is interpreted internally before performing any split.

~~~bash
python run_atomizer.py --file ./examples/example_mistral.md
~~~

### 2. Split into N sections

Split the document into *N* sections using the deterministic split algorithm:

```bash
python run_atomizer.py --file ./examples/example_mistral.md --split 3 --split-json-out out.json
```

By default, `--split-json-mode` is `plan`. In this mode, `out.json` contains **metadata only**, including cut indices, word counts, and section boundaries.

If you want **materialized text sections** (a list of strings whose concatenation exactly reconstructs the original document), use `--split-json-mode sections`:

```bash
python run_atomizer.py \
  --file ./examples/example_mistral.md \
  --split 3 \
  --split-json-mode sections \
  --split-json-out out.json
```

Example output:

```json
{
  "mode": "sections",
  "N": 3,
  "cuts": [25, 40],
  "sections": [
    "…exact original text for section 1…",
    "…exact original text for section 2…",
    "…exact original text for section 3…"
  ]
}
```

### 3. Export Mermaid diagram

Visualize the inferred document structure and section boundaries using Mermaid:

~~~bash
python run_atomizer.py \
  --file ./examples/example_mistral.md \
  --split 5 \
  --mermaid-out example_mistral.mmd \
  --mermaid-leaves
~~~

This generates a Mermaid diagram showing:
- Section hierarchy
- Optional leaf nodes (paragraphs, lists, code blocks)
- Section coloring (when splits are enabled)

> You can render the `.mmd` file using the Mermaid CLI (for example,  
> `npx -y -p @mermaid-js/mermaid-cli@10 mmdc -i out.mmd -o out.png -s 3`),  
> compatible Markdown renderers, or free online Mermaid editors such as  
> https://www.mermaidflow.app/editor.

> When using `npx`, for high-resolution exports (e.g., for papers or slides), increase the scale factor using `-s`.

## Summary

- Document segmentation is ambiguous — so we made it explicit.
- We avoid LLMs where generation is unnecessary.
- We parse once, then reason over atoms.
- Visualization is not an afterthought; it’s part of the design.
