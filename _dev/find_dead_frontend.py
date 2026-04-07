"""Find frontend .vue/.js files that nothing else imports."""
import os
import re


def main():
    src_root = "frontend/src"
    files = []
    for r, dirs, fs in os.walk(src_root):
        if "node_modules" in dirs:
            dirs.remove("node_modules")
        for f in fs:
            if f.endswith((".vue", ".js")):
                full = os.path.join(r, f).replace(os.sep, "/")
                # Skip the main entry points — these are bootstrap files
                base = os.path.basename(full)
                if base in ("main.js", "router.js", "App.vue"):
                    continue
                files.append(full)

    print(f"Total scannable files: {len(files)}\n")

    def find_refs(target_path, exclude_self):
        leaf = os.path.basename(target_path)
        leaf_no_ext = os.path.splitext(leaf)[0]
        # Build patterns:
        #  - import ... from '<...>/leaf'
        #  - import ... from '<...>/leaf.vue|.js'
        #  - dynamic import('...leaf...')
        #  - vite/router lazy: () => import('...leaf...')
        # Plus '@/<path>' alias style
        pat_full = re.compile(rf"['\"`][^'\"`]*\b{re.escape(leaf)}\b['\"`]")
        pat_noext = re.compile(rf"['\"`][^'\"`]*\b{re.escape(leaf_no_ext)}\b['\"`]")
        refs = []
        for r2, dirs2, fs2 in os.walk(src_root):
            if "node_modules" in dirs2:
                dirs2.remove("node_modules")
            for f2 in fs2:
                if not f2.endswith((".vue", ".js", ".ts")):
                    continue
                full = os.path.join(r2, f2).replace(os.sep, "/")
                if os.path.abspath(full) == os.path.abspath(exclude_self):
                    continue
                try:
                    content = open(full, encoding="utf-8").read()
                except Exception:
                    continue
                if pat_full.search(content) or pat_noext.search(content):
                    refs.append(full)
        return refs

    dead = []
    for f in files:
        if not find_refs(f, f):
            dead.append(f)

    print(f"Files with NO importers ({len(dead)}):")
    for f in sorted(dead):
        print(f"  {f}")


if __name__ == "__main__":
    main()
