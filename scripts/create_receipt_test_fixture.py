"""Create a fictional receipt for local browser QA; never reads user receipts."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
target = root / '.local-data' / 'fictional-receipt.png'
target.parent.mkdir(exist_ok=True)
picture = Image.new('RGB', (1200, 600), 'white')
font_path = 'C:/Windows/Fonts/arial.ttf' if Path('C:/Windows/Fonts/arial.ttf').exists() else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
ImageDraw.Draw(picture).multiline_text((50, 40), 'TEST OFFICE STORE\nFICTIONAL RECEIPT\nDate 2026-11-06\nPaper supplies\nTOTAL NGN 1,000.10', fill='black', font=ImageFont.truetype(font_path, 44), spacing=25)
picture.save(target)
print('Created ignored fictional receipt fixture')
