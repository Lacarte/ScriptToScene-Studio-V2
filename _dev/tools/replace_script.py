import pathlib

p = pathlib.Path('timeline-editor/frontend/js/api.js')
text = p.read_text(encoding='utf-8')
text = text.replace('proj_', 'pm_')
p.write_text(text, encoding='utf-8')
print("Done replacing.")
