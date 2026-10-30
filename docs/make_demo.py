"""Render docs/demo.gif: a stylized Win+R + terminal walkthrough of quickrun.

Terminal text is real quickrun output (username replaced with "you").
"""
import sys
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1]
W, H = 980, 520
FONT = ImageFont.truetype(r"C:\Windows\Fonts\CascadiaMono.ttf", 14)
UI = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 14)
UI_B = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 15)
CAP = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 20)
LH = 21

BG = (24, 24, 32)
BAR = (40, 40, 52)
FG = (220, 222, 228)
DIM = (130, 134, 150)
PROMPT = (110, 200, 250)
OK = (120, 220, 140)
WARN = (240, 190, 90)
ERR = (240, 110, 110)

frames, durations = [], []


def emit(img, ms):
    frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=64))
    durations.append(ms)


def color_for(line):
    if line.startswith("[OK]"):
        return OK
    if line.startswith("Not found"):
        return WARN
    if line.startswith("(") or line.strip().startswith("("):
        return DIM
    return FG


MAX_CHARS = int((W - 36) // FONT.getlength("M"))


def wrap(lines):
    out = []
    for line in lines:
        limit = MAX_CHARS - (4 if line.startswith("> ") else 0)
        while len(line) > limit:
            cut = line.rfind(" ", 0, limit)
            if cut <= 4:
                cut = limit
            out.append(line[:cut])
            line = "    " + line[cut:].lstrip()
        out.append(line)
    return out


def terminal(lines, caption=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 34], fill=BAR)
    d.text((16, 17), "Windows PowerShell", font=UI, fill=DIM, anchor="lm")
    cx = W - 110
    d.line([cx - 5, 17, cx + 5, 17], fill=DIM, width=1)
    d.rectangle([cx + 35, 12, cx + 45, 22], outline=DIM, width=1)
    d.line([cx + 75, 12, cx + 85, 22], fill=DIM, width=1)
    d.line([cx + 75, 22, cx + 85, 12], fill=DIM, width=1)
    y = 48
    for line in wrap(lines)[-19:]:
        if line.startswith("> "):
            d.text((18, y), "PS>", font=FONT, fill=PROMPT)
            d.text((18 + 36, y), line[2:], font=FONT, fill=FG)
        else:
            d.text((18, y), line, font=FONT, fill=color_for(line))
        y += LH
    if caption:
        draw_caption(d, caption)
    return img


def draw_caption(d, text):
    w = d.textlength(text, font=CAP) + 40
    x0 = (W - w) / 2
    d.rounded_rectangle([x0, H - 62, x0 + w, H - 20], radius=12,
                        fill=(70, 90, 200))
    d.text((W / 2, H - 41), text, font=CAP, fill=(255, 255, 255), anchor="mm")


def run_dialog(typed, result=None, result_color=None, caption=None):
    img = Image.new("RGB", (W, H), (32, 60, 110))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 250, 120, 730, 330
    d.rounded_rectangle([x0 + 6, y0 + 8, x1 + 6, y1 + 8], radius=8,
                        fill=(20, 36, 70))
    d.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=(243, 243, 243))
    d.text((x0 + 16, y0 + 12), "Run", font=UI_B, fill=(30, 30, 30))
    d.text((x0 + 16, y0 + 48),
           "Type the name of a program, folder, document, or Internet",
           font=UI, fill=(40, 40, 40))
    d.text((x0 + 16, y0 + 68), "resource, and Windows will open it for you.",
           font=UI, fill=(40, 40, 40))
    d.text((x0 + 16, y0 + 112), "Open:", font=UI, fill=(40, 40, 40))
    d.rectangle([x0 + 70, y0 + 106, x1 - 16, y0 + 136], fill=(255, 255, 255),
                outline=(0, 103, 192), width=2)
    d.text((x0 + 78, y0 + 112), typed + "|", font=UI, fill=(20, 20, 20))
    for i, label in enumerate(["OK", "Cancel", "Browse..."]):
        bx = x1 - 16 - (3 - i) * 96 + 8
        d.rounded_rectangle([bx, y1 - 46, bx + 86, y1 - 16], radius=4,
                            fill=(0, 103, 192) if i == 0 else (225, 225, 225))
        d.text((bx + 43, y1 - 31), label, font=UI,
               fill=(255, 255, 255) if i == 0 else (30, 30, 30), anchor="mm")
    d.text((W / 2, 70), "Win + R", font=CAP, fill=(200, 215, 240), anchor="mm")
    if result:
        d.text((W / 2, 380), result, font=CAP, fill=result_color, anchor="mm")
    if caption:
        draw_caption(d, caption)
    return img


def type_into_dialog(word, result, color, caption):
    for i in range(len(word) + 1):
        emit(run_dialog(word[:i], caption=caption), 110 if i else 700)
    emit(run_dialog(word, result, color, caption), 2200)


def type_command(history, cmd, output, caption=None, hold=2600):
    for i in range(0, len(cmd) + 1, 2):
        emit(terminal(history + ["> " + cmd[:i]], caption), 35)
    history = history + ["> " + cmd]
    emit(terminal(history, caption), 350)
    for line in output:
        history = history + [line]
        emit(terminal(history, caption), 70)
    durations[-1] = hold
    return history


# 1. Before
type_into_dialog("word", "Windows cannot find 'word'.", ERR,
                 "Before: third-party apps don't work in Win+R")

# 2. Bind it
h = type_command(
    [], r'quickrun bind "C:\Program Files (x86)\Microsoft Office\Root\Office16\WINWORD.EXE" word',
    [r'[OK] Win+R -> "word" now opens C:\Program Files (x86)\Microsoft Office\Root\Office16\WINWORD.EXE'],
    "One command. No admin. Instant.")

# 3. After
type_into_dialog("word", "Microsoft Word opens.", (120, 230, 150),
                 "After: Win+R -> word just works")

# 4. Quickstart with custom apps
h = type_command(
    [], 'quickrun quickstart --apps "telegram, obsidian, notion"',
    ["Scanning for installed apps...", "",
     '  looking for "telegram" ...',
     '  looking for "obsidian" ...',
     '  looking for "notion" ...', "",
     "Found - will bind:",
     r"  telegram  ->  C:\Users\you\AppData\Roaming\Telegram Desktop\Telegram.exe",
     r"  notion    ->  C:\Users\you\AppData\Local\Programs\Notion\Notion.exe", "",
     "Not found: obsidian",
     "  (try the exe's real name, or a deeper interactive search: quickrun find <name>)",
     "", "Bind the 2 alias(es) found? [Y/n] y", "",
     "[OK] 2 alias(es) bound. Try Win+R and type one of them."],
    "Or let quickstart find your apps", hold=3200)

# 5. Terminal alias
type_command(
    h, "quickrun alias --cmd quickrun qr",
    [r'[OK] Terminal alias "qr" -> C:\Users\you\AppData\Local\Programs\quickrun\quickrun.exe added to your PowerShell profiles.'],
    "Terminal aliases too", hold=3000)

frames[0].save(OUT, save_all=True, append_images=frames[1:],
               duration=durations, loop=0, optimize=True, disposal=1)
print(f"{len(frames)} frames, {sum(durations) / 1000:.1f}s")
