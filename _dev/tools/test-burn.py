import subprocess

vf = "split[base][mask_bg];[mask_bg]format=gbrp,drawbox=x=0:y=0:w=iw:h=ih:color=0x000000:t=fill,drawtext=text='TEXT':fontsize=80:fontcolor=#969696:x=(w-text_w)/2:y=h*81/100-80/2[mask];[base]format=gbrp[base_rgb];[base_rgb][mask]blend=all_mode=difference,format=yuv420p,drawtext=text='TEXT':fontsize=80:fontcolor=#FFFFFF@0x5e:x=(w-text_w)/2:y=h*81/100-80/2"

cmd = [
    r"D:\@Workspace\@Development\@Scripts\@Python\ScriptToScene-Studio\bin\ffmpeg.exe", '-y',
    '-f', 'lavfi', '-i', 'color=c=black:s=1080x1920:d=1',
    '-vf', vf,
    '-c:v', 'libx264',
    '-preset', 'fast',
    '-crf', '23',
    'test_burn.mp4'
]

print("Running command...")
result = subprocess.run(cmd, capture_output=True, text=True)
with open("test_burn_err.log", "w", encoding="utf-8") as f:
    f.write(result.stderr)
print("Return code:", result.returncode)
