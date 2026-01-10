import json
import argparse
from pathlib import Path
from atomizer import detect_mode, atomize
from render import render_mermaid, MermaidOptions
from partition import build_cut_candidates, partition_into_n


def _preview(text: str, n: int = 50) -> str:
    s = " ".join(text.strip().split())
    return (s[:n] + "…") if len(s) > n else s


def print_atoms(atoms, max_preview=50):
    print(
        f"{'idx':>4}  {'type':<14} {'lines':<11} {'bytes':<12} "
        f"{'words':>6} {'chars':>6} {'dep':>3} {'cut':>3} {'bnd':>4} "
        f"{'sid':>4} {'pid':<12}  preview"
    )
    print("-" * 140)

    for a in atoms:
        lines = f"{a.start_line}-{a.end_line}"
        bytes_ = f"{a.start_byte}-{a.end_byte}"
        sid = a.section_node_id if a.section_node_id is not None else "-"
        pid = "/".join(map(str, a.section_path_ids)) if a.section_path_ids else "-"
        # path = "/".join(a.section_path) if a.section_path else "-"
        # if len(path) > 30:
        #     path = path[:27] + "…"

        print(
            f"{a.idx:>4}  {a.atom_type.value:<14} {lines:<11} {bytes_:<12} "
            f"{a.weight_words:>6} {a.weight_chars:>6} {a.depth:>3} {int(a.can_cut_before):>3} "
            f"{a.boundary_strength:>4.2f} {str(sid):>4} {pid:<12}  {_preview(a.text, max_preview)}"
        )

    
def _print_split(res):
    print("\nSplit result")
    print("-" * 80)
    print(f"Objective (non_heading_cuts, max_words, penalty_sum): {res.objective}")
    print(f"Cuts (start atom indices for sections 2..N): {res.cuts}")
    print()

    for seg in res.segments:
        title = "/".join(seg.start_path_titles) if seg.start_path_titles else "-"
        print(
            f"Section {seg.seg_idx + 1:02d}: atoms [{seg.start_atom}:{seg.end_atom_excl}) "
            f"words={seg.words:4d}  start_path={title}"
        )


def main():
    ap = argparse.ArgumentParser(description="Run atomizer and optionally export Mermaid section diagram.")
    ap.add_argument("--file", type=str, help="Path to input text/markdown file.")
    ap.add_argument("--text", type=str, help="Inline text (alternative to --file).")
    ap.add_argument("--max-preview", type=int, default=60, help="Max preview chars per atom.")
    ap.add_argument("--no-print", action="store_true", help="Do not print atoms table.")
    ap.add_argument("--mermaid-out", type=str, default=None, help="Write Mermaid diagram markdown to this file.")
    ap.add_argument("--mermaid-dir", type=str, default="TD", help="Mermaid direction: TD, LR, RL, BT.")
    ap.add_argument("--mermaid-no-pseudo", action="store_true", help="Exclude pseudo headings from diagram.")
    ap.add_argument("--mermaid-stats", action="store_true", help="Include rough section stats in node labels.")
    ap.add_argument("--mermaid-leaves", action="store_true")
    ap.add_argument("--mermaid-max-leaves-per-section", type=int, default=10)
    ap.add_argument("--mermaid-leaf-types", type=str, default="paragraph,list,code,table")
    # spit
    ap.add_argument("--split", type=int, default=None, help="Split into N sections (choose N-1 cut boundaries).")
    ap.add_argument("--split-relax", action="store_true",
                    help="Relax candidate cuts if needed (allow list/table/code, then paragraphs).")
    ap.add_argument("--split-no-pseudo", action="store_true",
                    help="Do not use pseudo headings (**Title**) as cut candidates.")
    ap.add_argument("--split-no-hr", action="store_true",
                    help="Do not use horizontal rules (---) as cut candidates.")
    ap.add_argument("--split-json-out", type=str, default=None,
                    help="Write split result (cuts + segments) to JSON.")
    args = ap.parse_args()

    if not args.file and not args.text:
        ap.error("Provide --file or --text")

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        text = args.text

    mode = detect_mode(text)
    atoms, section_registry = atomize(text, mode=mode)

    print(f"Detected mode: {mode.value}")
    print(f"Num atoms: {len(atoms)}")
    print(f"Num sections: {len(section_registry)}")

    if not args.no_print:
        print_atoms(atoms, max_preview=args.max_preview)

    res = None
    if args.split is not None:
        N = args.split
        allow_pseudo = not args.split_no_pseudo
        allow_hr = not args.split_no_hr

        # strict candidates first
        cands = build_cut_candidates(
            atoms,
            allow_pseudo=allow_pseudo,
            allow_hr=allow_hr,
            allow_list_table_code=False,
            allow_paragraph_fallback=False,
        )

        # attempt partition; if it fails and --split-relax, relax in stages
        try:
            res = partition_into_n(atoms, N=N, candidates=cands)
        except ValueError as e:
            if not args.split_relax:
                raise
            # relax 1: allow list/table/code
            cands2 = build_cut_candidates(
                atoms,
                allow_pseudo=allow_pseudo,
                allow_hr=allow_hr,
                allow_list_table_code=True,
                allow_paragraph_fallback=False,
            )
            try:
                res = partition_into_n(atoms, N=N, candidates=cands2)
            except ValueError:
                # relax 2: allow paragraph fallback
                cands3 = build_cut_candidates(
                    atoms,
                    allow_pseudo=allow_pseudo,
                    allow_hr=allow_hr,
                    allow_list_table_code=True,
                    allow_paragraph_fallback=True,
                )
                res = partition_into_n(atoms, N=N, candidates=cands3)

        _print_split(res)

        if args.split_json_out:
            payload = {
                "N": N,
                "objective": list(res.objective),
                "cuts": res.cuts,
                "segments": [
                    {
                        "seg_idx": s.seg_idx,
                        "start_atom": s.start_atom,
                        "end_atom_excl": s.end_atom_excl,
                        "words": s.words,
                        "start_path_ids": list(s.start_path_ids),
                        "start_path_titles": list(s.start_path_titles),
                    }
                    for s in res.segments
                ],
            }
            Path(args.split_json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"\nWrote split JSON to: {args.split_json_out}")
    
    if args.mermaid_out:
        opts = MermaidOptions(
            direction=args.mermaid_dir,
            include_pseudo_headings=(not args.mermaid_no_pseudo),
            include_section_stats=args.mermaid_stats,
            include_leaves=args.mermaid_leaves,
            max_leaves_per_section=args.mermaid_max_leaves_per_section,
            leaf_types=tuple(x.strip() for x in args.mermaid_leaf_types.split(",")),
            empty_leaf_types=(),
        )
        mm = render_mermaid(atoms, section_registry, opts=opts, cuts=res.cuts if res else None)
        Path(args.mermaid_out).write_text(mm, encoding="utf-8")
        print(f"Wrote Mermaid diagram to: {args.mermaid_out}")


if __name__ == "__main__":
    main()

