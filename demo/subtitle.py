# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10"]
# ///
"""Burn movie-style subtitles under the recording and mask the org name.

- Reads caption/keycast events (epoch timestamps) from /tmp/demo-captions.tsv,
  written by demo/drive.sh during the recording.
- Syncs them to video time by detecting when the board's navy title bar first
  appears (the ANCHOR event was recorded ~1s before that).
- Pads the video with a black band at the bottom and renders an .ass subtitle
  track there: scene captions in white, pressed keys in yellow underneath.
- Also masks the org-name line in the Claude banner of the session-tab scene.

Writes demo/demo.gif in place.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

GIF = Path(__file__).parent / "demo.gif"
EVENTS = Path("/tmp/demo-captions.tsv")
BAR = (830, 40, 1380, 54)      # board navy title bar (split view)
MASK = (255, 202, 600, 236)    # org-name line in the wide Claude banner
W, H, BAND = 1400, 800, 64
BOARD_LOAD_OFFSET = 1.0        # seconds between ANCHOR and the bar appearing

rows = [line.split("\t", 2) for line in EVENTS.read_text().splitlines() if line]
events = [(float(ts), kind, text.strip()) for ts, kind, text in rows]
anchor = next(ts for ts, kind, _ in events if kind == "ANCHOR")

tmp = Path(tempfile.mkdtemp())
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(GIF),
                "-vf", "fps=2", str(tmp / "f%04d.png")], check=True)
frames = sorted(tmp.glob("f*.png"))

def bar_visible(path: Path) -> bool:
    img = Image.open(path).convert("RGB").crop(BAR)
    px = list(img.getdata())
    r = sum(p[0] for p in px) / len(px)
    b = sum(p[2] for p in px) / len(px)
    return b - r > 30

duration = len(frames) / 2
t_bar = next(i / 2 for i, f in enumerate(frames) if bar_visible(f))
to_video = lambda ts: t_bar + (ts - anchor) - BOARD_LOAD_OFFSET
print(f"bar appears at t={t_bar:.1f}s; anchor maps to {to_video(anchor):.1f}s")

# Fast-forward the "Claude is working" wait: from shortly after the request is
# submitted until shortly before the board-refresh scene.
caps_raw = [(to_video(ts), text) for ts, kind, text in events if kind == "CAP"]
ff_start = next(t for t, x in caps_raw if x.startswith("Claude is creating")) + 2.0
ff_end = next(t for t, x in caps_raw if x.startswith("2/5")) - 1.0
FF_TARGET = 4.0  # compress the wait to about this many seconds
factor = max(1.0, (ff_end - ff_start) / FF_TARGET)
print(f"fast-forward {ff_start:.1f}s..{ff_end:.1f}s at {factor:.1f}x")

def remap(t: float) -> float:
    if t <= ff_start:
        return t
    if t <= ff_end:
        return ff_start + (t - ff_start) / factor
    return t - (ff_end - ff_start) * (1 - 1 / factor)

new_duration = remap(duration)

# Session-tab scene (bar gone for good) for the org-name mask.
t_mask = None
for i, f in enumerate(frames):
    if bar_visible(f):
        t_mask = None
    elif t_mask is None:
        t_mask = i / 2
mask_filter = ""
if t_mask is not None:
    sample = Image.open(frames[min(int(t_mask * 2), len(frames) - 1)]).convert("RGB")
    color = sample.getpixel((MASK[2] + 40, (MASK[1] + MASK[3]) // 2))
    hexcolor = "0x{:02x}{:02x}{:02x}".format(*color)
    x, y, x2, y2 = MASK
    t_mask_r = remap(t_mask)
    mask_filter = (f"drawbox=x={x}:y={y}:w={x2-x}:h={y2-y}:color={hexcolor}:t=fill:"
                   f"enable='gte(t,{max(0, t_mask_r - 0.3)})',")
    print(f"masking org name from t={t_mask_r:.1f}s (remapped)")

# Build the .ass subtitle track in the bottom band.
def stamp(sec: float) -> str:
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"

caps = [(remap(t), text) for t, text in caps_raw]
keys = [(remap(to_video(ts)), text) for ts, kind, text in events if kind == "KEY"]
keys.append((remap(ff_start), ">> fast-forward"))
keys.sort()
lines = []
for i, (start, text) in enumerate(caps):
    end = caps[i + 1][0] if i + 1 < len(caps) else new_duration
    lines.append(f"Dialogue: 0,{stamp(start)},{stamp(end)},Cap,,0,0,0,,{text}")
for i, (start, text) in enumerate(keys):
    nxt = min([t for t, _ in caps + keys if t > start] + [new_duration])
    end = min(start + 4, nxt)
    lines.append(f"Dialogue: 0,{stamp(start)},{stamp(end)},Key,,0,0,0,,{text}")

ass = f"""[Script Info]
PlayResX: {W}
PlayResY: {H + BAND}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Alignment, MarginL, MarginR, MarginV, Outline, Shadow, BorderStyle
Style: Cap,Helvetica,26,&H00FFFFFF,&H00000000,&H00000000,-1,0,2,20,20,30,0,0,1
Style: Key,Helvetica,20,&H0050D8F0,&H00000000,&H00000000,0,0,2,20,20,8,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(lines) + "\n"
ass_path = tmp / "subs.ass"
ass_path.write_text(ass)

vf = (f"[0:v]trim=end={ff_start},setpts=PTS-STARTPTS[s1];"
      f"[0:v]trim=start={ff_start}:end={ff_end},setpts=(PTS-STARTPTS)/{factor}[s2];"
      f"[0:v]trim=start={ff_end},setpts=PTS-STARTPTS[s3];"
      "[s1][s2][s3]concat=n=3:v=1[cat];"
      f"[cat]{mask_filter}pad={W}:{H + BAND}:0:0:black,"
      f"ass={ass_path},"
      "split[a][b];[a]palettegen=max_colors=256[p];[b][p]paletteuse")
out = GIF.with_name("demo.subtitled.gif")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(GIF),
                "-filter_complex", vf, str(out)], check=True)
out.replace(GIF)
print(f"done: {GIF} ({new_duration:.0f}s)")
