from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from atomizer import Atom, AtomType


@dataclass(frozen=True)
class Segment:
    seg_idx: int
    start_atom: int
    end_atom_excl: int
    words: int
    start_path_ids: Tuple[int, ...]
    start_path_titles: Tuple[str, ...]


@dataclass(frozen=True)
class PartitionResult:
    cuts: List[int]                 # length N-1; each is atom index where a new segment starts
    segments: List[Segment]         # length N
    objective: Tuple[int, int, float]  # (non_heading_cuts, max_words, penalty_sum)


def _prefix_words(atoms: List[Atom]) -> List[int]:
    pref = [0]
    s = 0
    for a in atoms:
        s += a.weight_words
        pref.append(s)
    return pref


def _is_heading_atom(a: Atom) -> bool:
    return a.atom_type == AtomType.HEADING


def _cut_tier(a: Atom) -> int:
    """
    Smaller is better.
    0: markdown HEADING (#/##/###)
    1: PSEUDO_HEADING (**Title**)
    2: HR
    3: everything else (rare; only if you enable)
    """
    if a.atom_type == AtomType.HEADING:
        return 0
    if a.atom_type == AtomType.PSEUDO_HEADING:
        return 1
    if a.atom_type == AtomType.HR:
        return 2
    return 3


def build_cut_candidates(
    atoms: List[Atom],
    *,
    prefer_headings: bool = True,
    allow_pseudo: bool = True,
    allow_hr: bool = True,
    # fallback knobs (set these False initially if you want strict structure cuts)
    allow_list_table_code: bool = False,
    allow_paragraph_fallback: bool = False,
) -> List[int]:
    """
    Returns candidate cut positions i (1..M-1), meaning 'start a new section at atoms[i]'.
    Always excludes BLANK as a cut target (too noisy).
    """
    cands: List[int] = []
    M = len(atoms)
    for i in range(1, M):
        a = atoms[i]
        if a.atom_type == AtomType.BLANK:
            continue
        if not a.can_cut_before:
            continue

        if a.atom_type == AtomType.HEADING:
            cands.append(i)
            continue
        if allow_pseudo and a.atom_type == AtomType.PSEUDO_HEADING:
            cands.append(i)
            continue
        if allow_hr and a.atom_type == AtomType.HR:
            cands.append(i)
            continue
        if allow_list_table_code and a.atom_type in {AtomType.LIST_BLOCK, AtomType.TABLE, AtomType.CODE_FENCE}:
            cands.append(i)
            continue
        if allow_paragraph_fallback and a.atom_type == AtomType.PARAGRAPH:
            cands.append(i)
            continue

    # If the user prefers headings, we don't remove non-headings here;
    # preference is enforced by the DP objective (lexicographic).
    return cands


def partition_into_n(
    atoms: List[Atom],
    N: int,
    candidates: List[int],
    *,
    non_heading_penalty: float = 1.0,
    tier_penalties: Optional[Dict[int, float]] = None,
) -> PartitionResult:
    """
    Lexicographic DP:
      minimize (#non_heading_cuts, max_segment_words, penalty_sum)

    - candidates: possible cut positions i (start indices) in [1, M-1]
    - returns cuts of length N-1 (start indices of segments 2..N)
    """
    assert N >= 1
    M = len(atoms)
    if N == 1:
        pref = _prefix_words(atoms)
        seg = Segment(
            seg_idx=0,
            start_atom=0,
            end_atom_excl=M,
            words=pref[M] - pref[0],
            start_path_ids=atoms[0].section_path_ids,
            start_path_titles=atoms[0].section_path,
        )
        return PartitionResult(cuts=[], segments=[seg], objective=(0, seg.words, 0.0))

    # Prepare candidate positions in DP space:
    # positions are boundaries between segments, so include 0 (start) and M (end).
    pos = [0] + sorted(set(candidates)) + [M]
    L = len(pos)

    # Penalties
    if tier_penalties is None:
        tier_penalties = {0: 0.0, 1: 0.2, 2: 0.5, 3: 1.0}

    def cut_cost(i_boundary: int) -> Tuple[int, float]:
        """
        Cost of choosing a cut that starts a segment at atom index i_boundary.
        - For i_boundary == M (end), no cut.
        """
        if i_boundary == M or i_boundary == 0:
            return (0, 0.0)
        a = atoms[i_boundary]
        tier = _cut_tier(a)
        is_non_heading = 0 if _is_heading_atom(a) else 1
        penalty = tier_penalties.get(tier, 1.0)
        return (is_non_heading, penalty)

    pref = _prefix_words(atoms)

    def seg_words(j: int, i: int) -> int:
        # segment covers atoms[pos[j] : pos[i]]
        return pref[pos[i]] - pref[pos[j]]

    # DP over k segments using boundaries in pos.
    # dp[k][i] = best objective for partitioning [0..pos[i]) into k segments, where last boundary is pos[i]
    # parent pointers for reconstruction.
    INF = (10**9, 10**9, 1e30)
    dp: List[List[Tuple[int, int, float]]] = [[INF] * L for _ in range(N + 1)]
    parent: List[List[int]] = [[-1] * L for _ in range(N + 1)]

    # Base: 1 segment ending at i
    for i in range(1, L):
        w = seg_words(0, i)
        dp[1][i] = (0, w, 0.0)  # no cuts
        parent[1][i] = 0

    # Transitions
    for k in range(2, N + 1):
        for i in range(1, L):
            best = INF
            best_j = -1
            # Try previous boundary j < i
            for j in range(0, i):
                prev = dp[k - 1][j]
                if prev == INF:
                    continue
                w = seg_words(j, i)
                non_head, pen = cut_cost(pos[j])  # cut that starts segment k at pos[j], except k=1 handled above
                # IMPORTANT: the cut that *creates* segment k is at boundary pos[j] (start of current segment)
                # For k segments, we have cuts at starts of segments 2..k => boundaries pos[j] when transitioning.
                cand = (
                    prev[0] + non_head,
                    max(prev[1], w),
                    prev[2] + non_heading_penalty * float(non_head) + pen,
                )
                if cand < best:
                    best = cand
                    best_j = j
            dp[k][i] = best
            parent[k][i] = best_j

    # We require exactly N segments ending at M -> position index L-1
    obj = dp[N][L - 1]
    if obj == INF:
        raise ValueError("No feasible partition: not enough candidate boundaries or N too large.")

    # Reconstruct boundaries (pos indices)
    boundaries: List[int] = []
    cur_i = L - 1
    for k in range(N, 1, -1):
        j = parent[k][cur_i]
        if j < 0:
            raise RuntimeError("DP reconstruction failed.")
        boundaries.append(pos[j])  # start index of segment k
        cur_i = j
    boundaries.reverse()  # these are cut starts for segments 2..N

    # Build segments list
    segs: List[Segment] = []
    starts = [0] + boundaries
    ends = boundaries + [M]
    for sidx, (s, e) in enumerate(zip(starts, ends)):
        w = pref[e] - pref[s]
        sp_ids = atoms[s].section_path_ids if s < M else tuple()
        sp_titles = atoms[s].section_path if s < M else tuple()
        segs.append(Segment(
            seg_idx=sidx,
            start_atom=s,
            end_atom_excl=e,
            words=w,
            start_path_ids=sp_ids,
            start_path_titles=sp_titles,
        ))

    return PartitionResult(cuts=boundaries, segments=segs, objective=obj)

