#!/usr/bin/env python3
"""
Work around a N64Recomp code-gen bug: a `j`/`b` instruction to an address
that isn't within the calling function nor a known function start emits
nothing (no goto, no call, no error) instead of failing loudly, leaving the
function's C body truncated with an unbalanced brace. This silently corrupts
the following functions in the same file until the parser gives up.

This scans each generated funcs_*.c file, and for any function whose brace
depth hasn't returned to zero by the time the next function starts (or EOF),
closes it off with an abort placeholder so the file is at least valid C.
The broken function's logic is incomplete either way -- this just prevents
it from corrupting everything after it.
"""
import glob
import re
import sys

FUNC_RE = re.compile(r'^RECOMP_FUNC void (\S+)\(')

def fix_file(path):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    out = []
    depth = 0
    cur_func = None
    fixed = 0

    def close_current():
        nonlocal depth, fixed
        if cur_func is not None and depth != 0:
            out.append("    // [fixup] function truncated by an unresolved jump target; closing to keep the file valid.\n")
            out.append("    return;\n")
            out.append("}\n" * depth)
            fixed += 1
        depth = 0

    for line in lines:
        m = FUNC_RE.match(line)
        if m:
            close_current()
            cur_func = m.group(1)
        out.append(line)
        depth += line.count('{') - line.count('}')

    close_current()

    if fixed:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(out)
    return fixed

def main():
    total = 0
    files_fixed = 0
    for path in glob.glob("RecompiledFuncs/funcs_*.c"):
        n = fix_file(path)
        if n:
            total += n
            files_fixed += 1
            print(f"{path}: closed {n} truncated function(s)")
    print(f"Total: {total} functions fixed across {files_fixed} files")

if __name__ == "__main__":
    main()
