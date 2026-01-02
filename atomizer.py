from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
import re


class DocMode(str, Enum):
    MARKDOWN = "markdown"
    PLAIN = "plain"


class AtomType(str, Enum):
    HEADING = "heading"                 # # / ## / ###
    PSEUDO_HEADING = "pseudo_heading"   # **Roadmap** on its own line, ALLCAPS, etc.
    PARAGRAPH = "paragraph"
    LIST_BLOCK = "list"
    CODE_FENCE = "code_fence"
    TABLE = "table"
    HR = "hr"                           # --- / *** / ___
    BLANK = "blank"


@dataclass
class Atom:
    # Identity & location
    idx: int
    atom_type: AtomType
    start_byte: int
    end_byte: int
    start_line: int  # 0-based
    end_line: int    # inclusive, 0-based

    # Content
    text: str

    # Weights (cheap now; token count can be added later)
    weight_chars: int
    weight_words: int

    # Pseudo-tree metadata
    depth: int = 0  # 0 = top; heading depth for markdown headings (1..6). For plain paragraphs usually 0.
    section_path: Tuple[str, ...] = field(default_factory=tuple)  # e.g., ("Roadmap", "First year")
    section_path_ids: Tuple[int, ...] = field(default_factory=tuple)
    section_node_id: Optional[int] = None

    # Boundary info
    can_cut_before: bool = False        # true if "starting here" is a good cut point
    boundary_strength: float = 0.0      # [0..1], heading-like boundaries high, paragraph low

    # Extra features for later
    keywords: Tuple[str, ...] = field(default_factory=tuple)


# -----------------------------
# Step 0: detect mode
# -----------------------------

_MD_HINTS = [
    re.compile(r"^\s{0,3}#{1,6}\s+\S", re.M),             # headings
    re.compile(r"^\s{0,3}(```|~~~)", re.M),               # fenced code
    re.compile(r"^\s{0,3}([-*+]|(\d+\.))\s+\S", re.M),    # lists
    re.compile(r"^\s{0,3}>\s+\S", re.M),                  # blockquote
    re.compile(r"\[[^\]]+\]\([^)]+\)"),                   # links
    re.compile(r"^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$", re.M) # hr
]

def detect_mode(text: str) -> DocMode:
    """Heuristic: if there are multiple markdown signals, treat as markdown."""
    hits = 0
    for pat in _MD_HINTS:
        if pat.search(text):
            hits += 1
    # If it shows at least 2 markdown characteristics, call it markdown.
    return DocMode.MARKDOWN if hits >= 2 else DocMode.PLAIN


# -----------------------------
# Step 1: atomization
# -----------------------------

_RE_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")
_RE_HR = re.compile(r"^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$")
_RE_FENCE = re.compile(r"^\s{0,3}(```|~~~)\s*(\S+)?\s*$")  # ```lang
_RE_LIST = re.compile(r"^\s{0,3}([-*+])\s+\S|^\s{0,3}\d+\.\s+\S")
_RE_TABLE_SEP = re.compile(r"^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$")
_RE_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")

def _is_standalone_bold_heading(line: str) -> Optional[str]:
    """
    Detect lines like:
      **Roadmap**
    on their own line (optionally surrounded by whitespace).
    Returns extracted title if match, else None.
    """
    s = line.strip()
    m = re.fullmatch(r"\*\*(.+?)\*\*", s)
    if m:
        title = m.group(1).strip()
        # Avoid matching "**bold** in a sentence" (must be whole line)
        if title:
            return title
    return None

def _is_allcaps_heading(line: str) -> Optional[str]:
    s = line.strip()
    if not s:
        return None
    # Short-ish, mostly letters/spaces, and many caps
    if len(s) <= 80 and re.fullmatch(r"[A-Z0-9][A-Z0-9 \-:,'\".()]+", s):
        # Require at least one letter and majority uppercase
        letters = [c for c in s if c.isalpha()]
        if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
            return s
    return None

def _count_words(s: str) -> int:
    return len(re.findall(r"\S+", s))

def atomize(text: str, mode: Optional[DocMode] = None) -> tuple[list[Atom], dict[int, int]]:
    """
    Convert a document to a linear atom stream with rich metadata.
    - Preserves content (atoms reference slices).
    - Avoids splitting inside code fences, list blocks, tables.
    - Adds pseudo-tree info via heading stack when detected.
    """
    if mode is None:
        mode = detect_mode(text)

    # Work line-by-line but keep byte offsets
    lines = text.splitlines(keepends=True)

    # Precompute byte offsets per line (start byte of each line)
    line_start_byte: List[int] = []
    b = 0
    for ln in lines:
        line_start_byte.append(b)
        b += len(ln.encode("utf-8")) if False else len(ln)  # assume Python str is fine for offsets in this context

    atoms: List[Atom] = []
    idx = 0

    # Pseudo-tree heading stack: list of (depth, node_id, title)
    heading_stack: List[Tuple[int, int, str]] = []
    next_node_id = 1

    section_registry: dict[int, int] = {}  # node_id -> atom_idx

    def current_section_path_titles() -> Tuple[str, ...]:
        return tuple(title for _, _, title in heading_stack)

    def current_section_path_ids() -> Tuple[int, ...]:
        return tuple(node_id for _, node_id, _ in heading_stack)

    def current_section_node_id() -> Optional[int]:
        return heading_stack[-1][1] if heading_stack else None

    def push_heading(depth: int, title: str) -> None:
        nonlocal next_node_id
        while heading_stack and heading_stack[-1][0] >= depth:
            heading_stack.pop()
        heading_stack.append((depth, next_node_id, title))
        next_node_id += 1

    def emit(atom_type: AtomType, start_line: int, end_line: int,
             depth: int = 0, can_cut_before: bool = False, boundary_strength: float = 0.0) -> None:
        nonlocal idx
        start_byte = line_start_byte[start_line] if start_line < len(line_start_byte) else len(text)
        # end_byte = start of line after end_line, or end of text
        if end_line + 1 < len(line_start_byte):
            end_byte = line_start_byte[end_line + 1]
        else:
            end_byte = len(text)

        chunk = "".join(lines[start_line:end_line + 1])
        atoms.append(Atom(
            idx=idx,
            atom_type=atom_type,
            start_byte=start_byte,
            end_byte=end_byte,
            start_line=start_line,
            end_line=end_line,
            text=chunk,
            weight_chars=len(chunk),
            weight_words=_count_words(chunk),
            depth=depth,
            section_path=current_section_path_titles(),
            section_path_ids=current_section_path_ids(),
            section_node_id=current_section_node_id(),
            can_cut_before=can_cut_before,
            boundary_strength=boundary_strength,
        ))
        idx += 1

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip("\n")

        # Blank line
        if line.strip() == "":
            emit(AtomType.BLANK, i, i, can_cut_before=False, boundary_strength=0.0)
            i += 1
            continue

        # Horizontal rule
        if _RE_HR.match(line):
            emit(AtomType.HR, i, i, can_cut_before=True, boundary_strength=0.9)
            i += 1
            continue

        # Fenced code block
        m_f = _RE_FENCE.match(line)
        if m_f:
            fence = m_f.group(1)
            start = i
            i += 1
            while i < len(lines):
                if re.match(rf"^\s{{0,3}}{re.escape(fence)}\s*$", lines[i].rstrip("\n")):
                    i += 1
                    break
                i += 1
            emit(AtomType.CODE_FENCE, start, i - 1, can_cut_before=True, boundary_strength=0.6)
            continue

        # Markdown heading (# ...)
        if mode == DocMode.MARKDOWN:
            m_h = _RE_HEADING.match(line)
            if m_h:
                depth = len(m_h.group(1))
                title = m_h.group(2).strip()
                push_heading(depth, title)
                emit(AtomType.HEADING, i, i, depth=depth, can_cut_before=True, boundary_strength=1.0)
                section_registry[current_section_node_id()] = idx - 1
                i += 1
                continue

        # Pseudo heading: standalone **Title** or ALLCAPS line
        title = _is_standalone_bold_heading(line) or _is_allcaps_heading(line)
        if title:
            parent_depth = heading_stack[-1][0] if heading_stack else 0
            pseudo_depth = min(parent_depth + 1, 6) if parent_depth > 0 else 1

            push_heading(pseudo_depth, title)
            emit(AtomType.PSEUDO_HEADING, i, i, depth=pseudo_depth, can_cut_before=True, boundary_strength=0.95)

            section_registry[current_section_node_id()] = idx - 1

            i += 1
            continue

        # Table block (simple heuristic)
        # Detect a table header row followed by separator line; or consecutive |...| lines
        if mode == DocMode.MARKDOWN and _RE_TABLE_ROW.match(line):
            # If next line looks like separator, treat as a table block
            if i + 1 < len(lines) and _RE_TABLE_SEP.match(lines[i + 1].rstrip("\n")):
                start = i
                i += 2
                while i < len(lines) and _RE_TABLE_ROW.match(lines[i].rstrip("\n")):
                    i += 1
                emit(AtomType.TABLE, start, i - 1, can_cut_before=True, boundary_strength=0.6)
                continue

        # List block
        if _RE_LIST.match(line):
            start = i
            i += 1
            # Continue while lines are list-ish or indented continuation lines
            while i < len(lines):
                nxt = lines[i].rstrip("\n")
                if nxt.strip() == "":
                    # stop before blank line; blank becomes its own atom
                    break
                if _RE_LIST.match(nxt):
                    i += 1
                    continue
                # continuation: indented line (common in lists)
                if re.match(r"^\s{2,}\S", nxt):
                    i += 1
                    continue
                break
            emit(AtomType.LIST_BLOCK, start, i - 1, can_cut_before=True, boundary_strength=0.5)
            continue

        # Paragraph: consume until blank line or a strong boundary starter
        start = i
        i += 1
        while i < len(lines):
            nxt_raw = lines[i]
            nxt = nxt_raw.rstrip("\n")
            if nxt.strip() == "":
                break
            if _RE_HR.match(nxt):
                break
            if _RE_FENCE.match(nxt):
                break
            if mode == DocMode.MARKDOWN and _RE_HEADING.match(nxt):
                break
            if _is_standalone_bold_heading(nxt) or _is_allcaps_heading(nxt):
                break
            if _RE_LIST.match(nxt):
                break
            # Table start checks
            if mode == DocMode.MARKDOWN and _RE_TABLE_ROW.match(nxt):
                if i + 1 < len(lines) and _RE_TABLE_SEP.match(lines[i + 1].rstrip("\n")):
                    break
            i += 1

        emit(AtomType.PARAGRAPH, start, i - 1, can_cut_before=False, boundary_strength=0.1)
        continue

    # Post-pass: mark "can_cut_before" for paragraphs that follow a blank or are large (fallback boundaries)
    # (Optional) You can keep this off initially.
    # for j in range(1, len(atoms)):
    #     if atoms[j].atom_type == AtomType.PARAGRAPH and atoms[j-1].atom_type in {AtomType.BLANK, AtomType.HR}:
    #         atoms[j].can_cut_before = True
    #         atoms[j].boundary_strength = max(atoms[j].boundary_strength, 0.2)

    # -----------------------------
    # Sanity checks (debug / dev)
    # -----------------------------
    for node_id, atom_idx in section_registry.items():
        assert 0 <= atom_idx < len(atoms), (
            f"section_registry points to invalid atom_idx {atom_idx}"
        )
        a = atoms[atom_idx]
        assert a.section_node_id == node_id, (
            f"Mismatch: registry node_id={node_id}, "
            f"atom.section_node_id={a.section_node_id}, atom.idx={a.idx}"
        )
        assert a.atom_type in {AtomType.HEADING, AtomType.PSEUDO_HEADING}, (
            f"Registry points to non-heading atom type {a.atom_type}"
        )

    return atoms, section_registry


# -----------------------------
# Tiny debug helper
# -----------------------------

def summarize_atoms(atoms: List[Atom], max_preview: int = 60) -> str:
    rows = []
    for a in atoms:
        preview = a.text.replace("\n", "\\n")
        if len(preview) > max_preview:
            preview = preview[:max_preview] + "…"
        rows.append(
            f"[{a.idx:03d}] {a.atom_type:14s} lines {a.start_line}-{a.end_line} "
            f"w={a.weight_words:4d} depth={a.depth} cut={int(a.can_cut_before)} "
            f"path={'/'.join(a.section_path) if a.section_path else '-'} :: {preview}"
        )
    return "\n".join(rows)
