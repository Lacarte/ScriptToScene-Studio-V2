"""Quick dead-module finder. Lists studio/ .py files that no other Python file imports."""
import os
import re


def main():
    root = "."
    studio_files = []
    for r, dirs, files in os.walk("studio"):
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")
        for f in files:
            if f.endswith(".py") and f != "__init__.py":
                studio_files.append(os.path.join(r, f).replace(os.sep, "/"))

    print(f"Total .py files in studio/: {len(studio_files)}\n")

    def find_refs(leaf_name, exclude_self):
        pat = re.compile(
            r"(?:^|\s)(?:from|import)\s+(?:\w+\.)*"
            + re.escape(leaf_name)
            + r"(?:\b|\s|$)"
        )
        refs = []
        for r2, dirs2, files2 in os.walk("."):
            if "__pycache__" in dirs2:
                dirs2.remove("__pycache__")
            skip_any = False
            for skip in ("_dev", "venv", "node_modules", "static", "frontend"):
                if skip in r2:
                    skip_any = True
                    break
            if skip_any:
                continue
            for f2 in files2:
                if not f2.endswith(".py"):
                    continue
                full = os.path.join(r2, f2)
                if os.path.abspath(full) == os.path.abspath(exclude_self):
                    continue
                try:
                    content = open(full, encoding="utf-8").read()
                except Exception:
                    continue
                if pat.search(content):
                    refs.append(full.replace(os.sep, "/"))
        return refs

    dead = []
    for f in studio_files:
        leaf = os.path.basename(f).replace(".py", "")
        refs = find_refs(leaf, f)
        if not refs:
            dead.append(f)

    print(f"Modules with NO importers ({len(dead)}):")
    for m in sorted(dead):
        print(f"  {m}")


if __name__ == "__main__":
    main()
