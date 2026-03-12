with open(r'd:\@Workspace\@Development\@Scripts\@Python\ScriptToScene-Studio\timeline-editor\frontend\js\video-editor.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

with open(r'd:\@Workspace\@Development\@Scripts\@Python\ScriptToScene-Studio\out2.txt', 'w', encoding='utf-8') as out:
    for i, l in enumerate(lines):
        if 'init' in l:
            out.write(f'{i+1}: {l}')
