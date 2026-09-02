#!/usr/bin/env python3
"""
Companion to fix_unclosed_funcs.py: an unresolved `j`/`b` target can still
emit `goto L_XXXXXXXX;` even when that label's definition falls outside
whatever got recompiled for the function (the same root cause -- the jump
target isn't within the function nor a known function start). This finds
every `goto L_...;` whose label is never defined within the same function
and inserts a dummy `L_...: return;` for it right before the function's
closing brace, so the (already known to be semantically incomplete) function
at least compiles.
"""
import glob
import re

FUNC_START_RE = re.compile(r'^RECOMP_FUNC void (\S+)\(')
GOTO_RE = re.compile(r'\bgoto (L_[0-9A-Fa-f]+);')
# Not anchored to line start: the generator sometimes emits a label glued
# directly onto the end of the previous statement with no newline between
# them (e.g. "cop0_reg_write(ctx, 3, 0);L_1000620C:"), which an anchored
# pattern would miss and misreport as an undefined label, producing a
# duplicate definition.
LABEL_DEF_RE = re.compile(r'(L_[0-9A-Fa-f]+):')

def fix_file(path):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    # Find function boundaries: list of (start_index, end_index_exclusive)
    starts = [i for i, l in enumerate(lines) if FUNC_START_RE.match(l)]
    starts.append(len(lines))

    out = list(lines[:starts[0]]) if starts[0] > 0 else []
    fixed = 0
    for idx in range(len(starts) - 1):
        body = lines[starts[idx]:starts[idx + 1]]
        defined = {m for l in body for m in LABEL_DEF_RE.findall(l)}
        referenced = {m for l in body for m in GOTO_RE.findall(l)}
        missing = referenced - defined
        if missing:
            # Insert stub labels right before the last '}' in this chunk.
            last_brace = max(i for i, l in enumerate(body) if l.strip() == '}' or l.strip() == ';}')
            for label in sorted(missing):
                body.insert(last_brace, f"    {label}: return; // [fixup] jump target outside recompiled range\n")
                last_brace += 1
            fixed += len(missing)
        out.extend(body)

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
            print(f"{path}: added {n} missing label(s)")
    print(f"Total: {total} labels added across {files_fixed} files")

if __name__ == "__main__":
    main()
