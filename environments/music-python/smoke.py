"""Synthetic-only readiness. No development images or reference files."""
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont
import music21, converter21
converter21.register()
out = Path('output'); out.mkdir(exist_ok=True)
Path('tmp').mkdir(exist_ok=True)
Path('tmp/write-check').write_text('writable')
s = music21.stream.Score(); p = music21.stream.Part(); p.append(music21.meter.TimeSignature('4/4'))
for pitch in ['C4', 'D4', 'E4', 'F4']: p.append(music21.note.Note(pitch, quarterLength=1))
s.append(p)
xml = s.write('musicxml', fp=str(out/'synthetic.musicxml'))
parsed = music21.converter.parse(xml)
assert len(parsed.recurse().notes) == 4
kern = parsed.write('humdrum', fp=str(out/'synthetic.krn'))
assert Path(kern).stat().st_size > 30
again = music21.converter.parse(str(kern)); assert len(again.recurse().notes) == 4
im = Image.new('RGB', (600, 140), 'white')
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 64)
ImageDraw.Draw(im).text((20,20), 'C G Am F', font=font, fill='black'); im.save(out/'text.png')
r = subprocess.run(['tesseract',str(out/'text.png'),'stdout','--psm','7'],capture_output=True,text=True,check=True)
assert 'C' in r.stdout and 'G' in r.stdout, r.stdout
print('READY: synthetic MusicXML -> nonempty kern -> parsed notes; OCR text; writable temp')
