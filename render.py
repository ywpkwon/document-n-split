from dataclasses import dataclass
from typing import Optional, Dict, Iterable, List, Optional, Set, Tuple
from atomizer import Atom, AtomType
from bisect import bisect_right


def _segment_of_atom_idx(def_idx: int, cuts: List[int]) -> int:
    """
    cuts are start indices for segments 2..N (sorted).
    returns segment index in [0..N-1]
    """
    # Example: cuts [10, 30] => ranges [0,10), [10,30), [30, M)
    return bisect_right(cuts, def_idx)


def _escape_mermaid_label(s: str) -> str:
    """
    Mermaid node labels are usually placed inside double quotes:
        S1["label"]
    Escape backslashes and double quotes, and collapse newlines.
    """
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = " ".join(s.splitlines())
    return s.strip()


@dataclass(frozen=True)
class MermaidOptions:
    direction: str = "TD"  # TD, LR, RL, BT
    include_pseudo_headings: bool = True
    include_root: bool = False  # if False, uses first seen top-level section(s) as roots
    include_section_stats: bool = False  # append "(atoms a-b, words=W)" to labels
    max_label_len: int = 80  # truncate long labels
    dedupe_titles: bool = False  # if True, include node_id in label to avoid confusing duplicates

    include_leaves: bool = False
    max_leaves_per_section: int = 10
    leaf_types: Tuple[str, ...] = ("paragraph", "list", "code_fence", "table")
    empty_leaf_types: Tuple[str, ...] = ("paragraph", "list")  # render as empty boxes


def render_mermaid(
    atoms: List[Atom],
    section_registry: Dict[int, int],
    *,
    opts: Optional[MermaidOptions] = None,
    cuts: Optional[List[int]] = None,
) -> str:
    """
    Render a Mermaid flowchart showing the section hierarchy implied by:
      - Atom.section_path_ids / Atom.section_path
      - section_registry: section_node_id -> atom_idx (defining HEADING/PSEUDO_HEADING atom)

    Returns Mermaid markdown string (starts with '```mermaid').
    """
    if opts is None:
        opts = MermaidOptions()

    # --- helpers ---
    def label_for_node(node_id: int, atom_idx: int) -> str:
        a = atoms[atom_idx]
        title = a.section_path[-1] if a.section_path else f"section_{node_id}"
        if opts.dedupe_titles:
            title = f"{title} [{node_id}]"
        if opts.include_section_stats:
            span = _section_span_atom_indices(node_id)
            if span is not None:
                lo, hi = span
                w = sum(atoms[k].weight_words for k in range(lo, hi + 1))
                title = f"{title} (atoms {lo}-{hi}, words={w})"
        if len(title) > opts.max_label_len:
            title = title[: opts.max_label_len - 1] + "…"
        return _escape_mermaid_label(title)

    # Determine which nodes to include (filter pseudo headings if desired)
    included_nodes: Set[int] = set()
    node_atom: Dict[int, int] = {}

    for node_id, atom_idx in section_registry.items():
        if atom_idx < 0 or atom_idx >= len(atoms):
            continue
        a = atoms[atom_idx]
        if a.atom_type == AtomType.PSEUDO_HEADING and not opts.include_pseudo_headings:
            continue
        if a.atom_type not in {AtomType.HEADING, AtomType.PSEUDO_HEADING}:
            continue
        included_nodes.add(node_id)
        node_atom[node_id] = atom_idx

    # Build parent -> child edges using section_path_ids from the defining atom
    edges: Set[Tuple[int, int]] = set()
    parent_map: Dict[int, Optional[int]] = {}

    for node_id, atom_idx in node_atom.items():
        pid = atoms[atom_idx].section_path_ids
        # pid ends with node_id; parent is pid[-2] if exists
        parent_id = pid[-2] if len(pid) >= 2 else None
        parent_map[node_id] = parent_id
        if parent_id is not None:
            # Only add edge if parent is also included (or if we want to force-root parent nodes)
            if parent_id in included_nodes:
                edges.add((parent_id, node_id))

    # Optionally include missing parents to keep the tree connected (best effort)
    if opts.include_root:
        # Make a synthetic ROOT and connect top-level nodes to it.
        ROOT_ID = 0
        included_nodes.add(ROOT_ID)

        # Create a pseudo atom label for ROOT
        node_atom[ROOT_ID] = -1  # sentinel
        for node_id, parent_id in parent_map.items():
            if node_id == ROOT_ID:
                continue
            if parent_id is None or parent_id not in included_nodes:
                edges.add((ROOT_ID, node_id))

    # Precompute section spans if requested
    section_span_cache: Dict[int, Tuple[int, int]] = {}
    if opts.include_section_stats:
        # We'll derive spans from section_node_id membership across atoms.
        # Span is from defining atom_idx to right before the next atom that is outside this node's subtree.
        # For now, a simple conservative span: [defining_idx, last_idx where section_path_ids contains node_id]
        membership: Dict[int, List[int]] = {nid: [] for nid in included_nodes if nid != 0}
        for k, a in enumerate(atoms):
            for nid in a.section_path_ids:
                if nid in membership:
                    membership[nid].append(k)
        for nid, ks in membership.items():
            if ks:
                section_span_cache[nid] = (min(ks), max(ks))

    def _section_span_atom_indices(node_id: int) -> Optional[Tuple[int, int]]:
        return section_span_cache.get(node_id)

    node_to_seg: Dict[int, int] = {}
    if cuts is not None:
        for node_id, atom_idx in node_atom.items():
            if atom_idx < 0:
                continue
            node_to_seg[node_id] = _segment_of_atom_idx(atom_idx, cuts)

    # Render Mermaid
    lines: List[str] = []
    lines.append("```mermaid")

    # Optional layout tuning (some renderers honor this init block)
    if cuts is not None:
        lines.append('%%{init: {"flowchart": {"nodeSpacing": 12, "rankSpacing": 28}} }%%')

    lines.append(f"flowchart {opts.direction}")

    # Emit nodes (always flat; no subgraphs)
    for nid in sorted(included_nodes):
        if nid == 0:
            lines.append('    ROOT["ROOT"]')
            continue
        atom_idx = node_atom.get(nid)
        if atom_idx is None:
            continue
        lbl = label_for_node(nid, atom_idx)
        lines.append(f'    S{nid}["{lbl}"]')

    # Optional: emit leaf atoms (paragraph/list/code/table) under their local section node
    if opts.include_leaves:
        # Map user-facing strings -> AtomType
        name_to_type = {
            "paragraph": AtomType.PARAGRAPH,
            "list": AtomType.LIST_BLOCK,
            "code": AtomType.CODE_FENCE,
            "code_fence": AtomType.CODE_FENCE,
            "table": AtomType.TABLE,
        }

        leaf_atom_types = set()
        for tname in opts.leaf_types:
            at = name_to_type.get(tname.strip().lower())
            if at is not None:
                leaf_atom_types.add(at)

        empty_leaf_atom_types = set()
        for tname in opts.empty_leaf_types:
            at = name_to_type.get(tname.strip().lower())
            if at is not None:
                empty_leaf_atom_types.add(at)

        # Collect leaves under their *local* section (leaf.section_node_id)
        leaves_by_section: Dict[int, List[int]] = {}
        for a in atoms:
            if a.atom_type not in leaf_atom_types:
                continue
            if a.section_node_id is None:
                continue
            # Only attach leaves to section nodes that exist in this diagram
            if a.section_node_id not in included_nodes:
                continue
            # Skip blanks always
            if a.atom_type == AtomType.BLANK:
                continue
            leaves_by_section.setdefault(a.section_node_id, []).append(a.idx)

        # Leaf styles: empty boxes for paragraph/list
        lines.append("classDef leafEmpty fill:#ffffff,stroke:#999,stroke-width:1px,color:#999;")
        lines.append("classDef leafLabeled fill:#ffffff,stroke:#666,stroke-width:1px,color:#111;")

        for sid, atom_indices in leaves_by_section.items():
            # cap number of leaves per section
            atom_indices = atom_indices[: opts.max_leaves_per_section]

            for ai in atom_indices:
                a = atoms[ai]
                leaf_id = f"A{ai}"

                if a.atom_type in empty_leaf_atom_types:
                    # empty box
                    lines.append(f'    {leaf_id}["·"]')
                    lines.append(f"    S{sid} --> {leaf_id}")
                    lines.append(f"    class {leaf_id} leafEmpty;")
                else:
                    # short label for code/table (avoid width explosion)
                    if a.atom_type == AtomType.CODE_FENCE:
                        lbl = "code"
                    elif a.atom_type == AtomType.TABLE:
                        lbl = "table"
                    else:
                        lbl = a.atom_type.value

                    lines.append(f'    {leaf_id}["{lbl}"]')
                    lines.append(f"    S{sid} --> {leaf_id}")
                    lines.append(f"    class {leaf_id} leafLabeled;")

            # If truncated, show overflow marker
            total = len(leaves_by_section[sid])
            if total > opts.max_leaves_per_section:
                more_id = f"A{sid}_MORE"
                lines.append(f'    {more_id}["… (+{total - opts.max_leaves_per_section})"]')
                lines.append(f"    S{sid} --> {more_id}")
                lines.append(f"    class {more_id} leafLabeled;")

    # Emit edges
    for p, c in sorted(edges):
        pkey = f"S{p}" if p != 0 else "ROOT"
        ckey = f"S{c}" if c != 0 else "ROOT"
        lines.append(f"    {pkey} --> {ckey}")

    # If cuts exist, color nodes by segment
    if cuts is not None:
        # Compute segment index per node (0-based)
        node_to_seg: Dict[int, int] = {}
        for nid, atom_idx in node_atom.items():
            if nid == 0 or atom_idx < 0:
                continue
            node_to_seg[nid] = _segment_of_atom_idx(atom_idx, cuts)

        n_segs = len(cuts) + 1

        # A small palette of pleasant colors (background, stroke, text)
        # If n_segs > palette size, we cycle.
        palette = [
            ("#E3F2FD", "#1E88E5", "#0D47A1"),  # blue
            ("#E8F5E9", "#43A047", "#1B5E20"),  # green
            ("#FFF3E0", "#FB8C00", "#E65100"),  # orange
            ("#F3E5F5", "#8E24AA", "#4A148C"),  # purple
            ("#FCE4EC", "#D81B60", "#880E4F"),  # pink
            ("#E0F7FA", "#00ACC1", "#006064"),  # cyan
            ("#F1F8E9", "#7CB342", "#33691E"),  # lime
            ("#EFEBE9", "#6D4C41", "#3E2723"),  # brown
        ]

        # Define class styles
        for s in range(n_segs):
            fill, stroke, text = palette[s % len(palette)]
            lines.append(
                f"classDef sec{s+1} fill:{fill},stroke:{stroke},stroke-width:1px,color:{text};"
            )

        # Assign nodes to classes
        seg_to_nodes: Dict[int, List[int]] = {}
        for nid in sorted(included_nodes):
            if nid == 0:
                continue
            seg = node_to_seg.get(nid, 0)
            seg_to_nodes.setdefault(seg, []).append(nid)

        for seg, nids in sorted(seg_to_nodes.items()):
            # Mermaid 'class' statement can take a comma-separated list
            joined = ",".join(f"S{nid}" for nid in nids)
            lines.append(f"class {joined} sec{seg+1};")

    lines.append("```")
    return "\n".join(lines)

