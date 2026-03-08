import sys
import traceback

try:
    import pathlib
    p = pathlib.Path(r'd:\@Workspace\@Development\@Scripts\@Python\ScriptToScene-Studio\timeline-editor\frontend\js\api.js')
    text = p.read_text(encoding='utf-8')
    new_text = text.replace('proj_', 'pm_')
    if text == new_text:
        print("No changes made. proj_ not found.")
    else:
        p.write_text(new_text, encoding='utf-8')
        print("SUCCESS")
except Exception as e:
    print(traceback.format_exc())
