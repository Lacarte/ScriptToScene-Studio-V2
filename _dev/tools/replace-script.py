"""Find-and-replace helper for bulk text substitution in a file."""
import sys
import pathlib
import traceback

try:
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(
        r'd:\@Workspace\@Development\@Scripts\@Python\ScriptToScene-Studio\timeline-editor\frontend\js\api.js'
    )
    old, new = ('proj_', 'pm_') if len(sys.argv) < 4 else (sys.argv[2], sys.argv[3])

    text = target.read_text(encoding='utf-8')
    new_text = text.replace(old, new)
    if text == new_text:
        print(f"No changes made. '{old}' not found in {target.name}.")
    else:
        target.write_text(new_text, encoding='utf-8')
        print(f"SUCCESS — replaced '{old}' → '{new}' in {target.name}")
except Exception:
    traceback.print_exc()
