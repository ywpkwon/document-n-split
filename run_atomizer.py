import argparse
from pathlib import Path
from atomizer import detect_mode, atomize
from render import render_mermaid, MermaidOptions


def _preview(text: str, n: int = 50) -> str:
    s = " ".join(text.strip().split())
    return (s[:n] + "…") if len(s) > n else s


def print_atoms(atoms, max_preview=50):
    print(
        f"{'idx':>4}  {'type':<14} {'lines':<11} {'bytes':<15} "
        f"{'words':>6} {'chars':>6} {'dep':>3} {'cut':>3} {'bnd':>4} "
        f"{'sid':>4} {'pid':<12} {'path':<30}  preview"
    )
    print("-" * 140)

    for a in atoms:
        lines = f"{a.start_line}-{a.end_line}"
        bytes_ = f"{a.start_byte}-{a.end_byte}"
        sid = a.section_node_id if a.section_node_id is not None else "-"
        pid = "/".join(map(str, a.section_path_ids)) if a.section_path_ids else "-"
        path = "/".join(a.section_path) if a.section_path else "-"
        if len(path) > 30:
            path = path[:27] + "…"

        print(
            f"{a.idx:>4}  {a.atom_type.value:<14} {lines:<11} {bytes_:<15} "
            f"{a.weight_words:>6} {a.weight_chars:>6} {a.depth:>3} {int(a.can_cut_before):>3} "
            f"{a.boundary_strength:>4.2f} {str(sid):>4} {pid:<12} {path:<30}  {_preview(a.text, max_preview)}"
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

    if args.mermaid_out:
        opts = MermaidOptions(
            direction=args.mermaid_dir,
            include_pseudo_headings=(not args.mermaid_no_pseudo),
            include_section_stats=args.mermaid_stats,
        )
        mm = render_mermaid(atoms, section_registry, opts=opts)
        Path(args.mermaid_out).write_text(mm, encoding="utf-8")
        print(f"Wrote Mermaid diagram to: {args.mermaid_out}")


if __name__ == "__main__":
    main()
