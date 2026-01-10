from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from atomizer import Atom, AtomType
from bisect import bisect_right


def _segment_of_atom_idx(def_idx: int, cuts: List[int]) -> int:
    """
    cuts are start indices for segments 2..N (sorted).
    returns segment index in [0..N-1]
    """
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
        parent_id = pid[-2] if len(pid) >= 2 else None
        parent_map[node_id] = parent_id
        if parent_id is not None and parent_id in included_nodes:
            edges.add((parent_id, node_id))

    # Optionally include missing parents to keep the tree connected (best effort)
    if opts.include_root:
        ROOT_ID = 0
        included_nodes.add(ROOT_ID)
        node_atom[ROOT_ID] = -1  # sentinel
        for node_id, parent_id in parent_map.items():
            if node_id == ROOT_ID:
                continue
            if parent_id is None or parent_id not in included_nodes:
                edges.add((ROOT_ID, node_id))

    # Precompute section spans if requested
    section_span_cache: Dict[int, Tuple[int, int]] = {}
    if opts.include_section_stats:
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

    # Helper: attach leaves to nearest included section node
    def _attach_section_id(a: Atom) -> Optional[int]:
        if a.section_node_id is not None and a.section_node_id in included_nodes:
            return a.section_node_id
        for sid in reversed(a.section_path_ids):
            if sid in included_nodes:
                return sid
        return None

    # If cuts exist, compute section-node -> segment map (for coloring section nodes)
    node_to_seg: Dict[int, int] = {}
    if cuts is not None:
        for nid, atom_idx in node_atom.items():
            if nid == 0 or atom_idx < 0:
                continue
            node_to_seg[nid] = _segment_of_atom_idx(atom_idx, cuts)

    # Render Mermaid
    lines: List[str] = []
    lines.append("```mermaid")

    if cuts is not None:
        lines.append('%%{init: {"flowchart": {"nodeSpacing": 12, "rankSpacing": 28}} }%%')

    lines.append(f"flowchart {opts.direction}")

    # --- Define class styles FIRST (so leaves can reference sec* classes) ---
    if cuts is not None:
        n_segs = len(cuts) + 1
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
        for s in range(n_segs):
            fill, stroke, text = palette[s % len(palette)]
            lines.append(
                f"classDef sec{s+1} fill:{fill},stroke:{stroke},stroke-width:1px,color:{text};"
            )

    # Leaf styles: keep them subtle
    lines.append("classDef leafEmpty stroke-width:1px;")
    lines.append("classDef leafLabeled stroke-width:1px;")

    # Emit section nodes (always flat)
    for nid in sorted(included_nodes):
        if nid == 0:
            lines.append('    ROOT["ROOT"]')
            continue
        atom_idx = node_atom.get(nid)
        if atom_idx is None:
            continue
        lbl = label_for_node(nid, atom_idx)
        lines.append(f'    S{nid}["{lbl}"]')

    # Color section nodes
    if cuts is not None:
        seg_to_nodes: Dict[int, List[int]] = {}
        for nid in sorted(included_nodes):
            if nid == 0:
                continue
            seg = node_to_seg.get(nid, 0)
            seg_to_nodes.setdefault(seg, []).append(nid)
        for seg, nids in sorted(seg_to_nodes.items()):
            joined = ",".join(f"S{nid}" for nid in nids)
            lines.append(f"class {joined} sec{seg+1};")

    # Optional: emit leaf atoms (paragraph/list/code/table) under nearest included section node
    if opts.include_leaves:
        name_to_type = {
            "paragraph": AtomType.PARAGRAPH,
            "list": AtomType.LIST_BLOCK,
            "code": AtomType.CODE_FENCE,
            "code_fence": AtomType.CODE_FENCE,
            "table": AtomType.TABLE,
        }

        leaf_atom_types: Set[AtomType] = set()
        for tname in opts.leaf_types:
            at = name_to_type.get(tname.strip().lower())
            if at is not None:
                leaf_atom_types.add(at)

        empty_leaf_atom_types: Set[AtomType] = set()
        for tname in opts.empty_leaf_types:
            at = name_to_type.get(tname.strip().lower())
            if at is not None:
                empty_leaf_atom_types.add(at)

        leaves_by_section: Dict[int, List[int]] = {}
        for a in atoms:
            if a.atom_type == AtomType.BLANK:
                continue
            if a.atom_type not in leaf_atom_types:
                continue
            sid = _attach_section_id(a)
            if sid is None:
                continue
            leaves_by_section.setdefault(sid, []).append(a.idx)

        for sid, atom_indices in leaves_by_section.items():
            atom_indices = atom_indices[: opts.max_leaves_per_section]

            for ai in atom_indices:
                a = atoms[ai]
                leaf_id = f"A{ai}"

                # Color leaves by THEIR OWN segment membership (based on atom index),
                # so leaf colors reflect the actual split even if attached to an ancestor section.
                sec_class = None
                if cuts is not None:
                    leaf_seg = _segment_of_atom_idx(ai, cuts)
                    sec_class = f"sec{leaf_seg+1}"

                if a.atom_type in empty_leaf_atom_types:
                    lines.append(f'    {leaf_id}["·"]')
                    lines.append(f"    S{sid} --> {leaf_id}")
                    if sec_class is not None:
                        lines.append(f"    class {leaf_id} leafEmpty;")
                        lines.append(f"    class {leaf_id} {sec_class};")
                    else:
                        lines.append(f"    class {leaf_id} leafEmpty;")
                else:
                    if a.atom_type == AtomType.CODE_FENCE:
                        lbl = "C"
                    elif a.atom_type == AtomType.TABLE:
                        lbl = "T"
                    elif a.atom_type == AtomType.PARAGRAPH:
                        lbl = "P"
                    elif a.atom_type == AtomType.LIST_BLOCK:
                        lbl = "L"
                    else:
                        lbl = a.atom_type.value

                    lines.append(f'    {leaf_id}["{lbl}"]')
                    lines.append(f"    S{sid} --> {leaf_id}")
                    if sec_class is not None:
                        lines.append(f"    class {leaf_id} leafLabeled;")
                        lines.append(f"    class {leaf_id} {sec_class};")
                    else:
                        lines.append(f"    class {leaf_id} leafLabeled;")

            total = len(leaves_by_section[sid])
            if total > opts.max_leaves_per_section:
                more_id = f"A{sid}_MORE"
                lines.append(f'    {more_id}["… (+{total - opts.max_leaves_per_section})"]')
                lines.append(f"    S{sid} --> {more_id}")
                sec_class = None
                if cuts is not None and atom_indices:
                    leaf_seg = _segment_of_atom_idx(atom_indices[-1], cuts)
                    sec_class = f"sec{leaf_seg+1}"
                if sec_class is not None:
                    lines.append(f"    class {more_id} leafLabeled;")
                    lines.append(f"    class {more_id} {sec_class};")
                else:
                    lines.append(f"    class {more_id} leafLabeled;")

    # Emit section-to-section edges
    for p, c in sorted(edges):
        pkey = f"S{p}" if p != 0 else "ROOT"
        ckey = f"S{c}" if c != 0 else "ROOT"
        lines.append(f"    {pkey} --> {ckey}")

    lines.append("```")
    return "\n".join(lines)
