"""Regenerate the licensed terminal icon subset from Nerd Fonts v3.4.0."""
import sys
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / 'gateway/web/fonts'
RANGES = [(0xe5fa, 0xe6b7), (0xe700, 0xe8ef), (0xf000, 0xf2e0),
          (0xf400, 0xf533), (0xf0001, 0xf1af0)]
font = TTFont(sys.argv[1])
options = subset.Options()
options.name_IDs = ['*']
options.name_legacy = True
options.name_languages = ['*']
subsetter = subset.Subsetter(options=options)
subsetter.populate(unicodes=[code for first, last in RANGES for code in range(first, last + 1)])
subsetter.subset(font)
font.save(FONT_DIR / 'terminal-icons.ttf')
font.flavor = 'woff2'
font.save(FONT_DIR / 'terminal-icons.woff2')
notices = '\n\n'.join(path.read_text() for path in sorted(FONT_DIR.glob('LICENSE-*.txt')))
for font_path, notice_path in [
    ('ios/ZedLink/Resources/terminal-icons.ttf', 'ios/ZedLink/Resources/terminal-font-licenses.txt'),
    ('android/app/src/main/res/font/terminal_icons.ttf', 'android/app/src/main/res/raw/terminal_font_licenses.txt'),
]:
    (ROOT / font_path).write_bytes((FONT_DIR / 'terminal-icons.ttf').read_bytes())
    (ROOT / notice_path).write_text(notices)
