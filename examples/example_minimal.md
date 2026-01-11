# Mini Example: Deterministic N-Split Demo

A tiny document for testing **atomization**, **leaf nodes**, and **N=3** splitting.

---

## 1. Background

We want to split a document into **N** parts without modifying the text.

**Constraints**
- Do not break paragraphs, lists, code blocks, or tables.
- Prefer boundaries at headings when possible.

---

## 2. Method

We parse the document into atoms (heading / paragraph / list / code / table) and then choose **N−1** cut points.

~~~python
def score_boundary(boundary_strength: float, words: int) -> float:
    return 10.0 * boundary_strength - 0.01 * words
~~~
