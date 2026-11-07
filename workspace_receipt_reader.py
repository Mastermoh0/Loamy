"""Offline receipt OCR. Treat extracted text as evidence, never as instructions."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


class ReceiptReadError(Exception):
    pass


def native_text(raw, mime):
    def run(args):
        try:
            result = subprocess.run(args, capture_output=True, timeout=20, check=True)
            return result.stdout.decode('utf-8', errors='replace')[:30000]
        except (OSError, subprocess.SubprocessError):
            raise ReceiptReadError('Receipt could not be read. Try a clearer image or enter the details manually.')
    with tempfile.TemporaryDirectory(prefix='loamy-receipt-') as directory:
        source = Path(directory) / ('receipt.pdf' if mime == 'application/pdf' else 'receipt.png')
        source.write_bytes(raw)
        if mime != 'application/pdf':
            return run(['tesseract', str(source), 'stdout', '-l', 'eng', '--psm', '6'])
        info = run(['pdfinfo', str(source)])
        pages = re.search(r'^Pages:\s+(\d+)', info, re.M)
        if not pages or not 1 <= int(pages[1]) <= 3:
            raise ReceiptReadError('Extraction supports PDFs with up to three pages. Upload a shorter receipt or enter details manually.')
        text = run(['pdftotext', '-layout', str(source), '-'])
        if len(re.sub(r'\s', '', text)) >= 20:
            return text
        # Render at bounded dimensions; no embedded PDF programs or network calls are run.
        run(['pdftoppm', '-scale-to', '1800', '-png', str(source), str(Path(directory) / 'page')])
        return '\n'.join(run(['tesseract', str(page), 'stdout', '-l', 'eng', '--psm', '6'])
                         for page in sorted(Path(directory).glob('page-*.png')))[:30000]


def read_receipt(raw, mime):
    required = ['tesseract'] + (['pdftotext', 'pdftoppm', 'pdfinfo'] if mime == 'application/pdf' else [])
    if all(shutil.which(tool) for tool in required):
        return native_text(raw, mime), 'tesseract-poppler-v1'
    # Explicit local-only fallback. Production installs the native tools in its container.
    image = os.getenv('LOAMY_RECEIPT_OCR_DOCKER_IMAGE')
    if image and os.getenv('LOAMY_LOCAL_PREVIEW') == '1':
        try:
            result = subprocess.run(['docker', 'run', '--rm', '-i', '--network', 'none', '--read-only',
                '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '384m', '--cpus', '1',
                '--tmpfs', '/tmp:rw,noexec,nosuid,size=96m', image, 'python3', '/app/workspace_receipt_reader.py', mime],
                input=raw, capture_output=True, timeout=70, check=True)
            data = json.loads(result.stdout)
            if data.get('error'):
                raise ReceiptReadError(data['error'])
            return data['text'][:30000], 'tesseract-poppler-v1'
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            raise ReceiptReadError('Receipt reader is unavailable. You can still enter the details manually.')
    raise ReceiptReadError('Receipt reader is not configured. You can still enter the details manually.')


def parse_receipt(text):
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text[:30000].splitlines() if line.strip()]
    warnings = ['Check every suggested value against the receipt before submitting.']
    foreign = bool(re.search(r'\b(?:USD|EUR|GBP|GHS|KES|CAD|AUD)\b|[$€£]', text, re.I))
    totals = set()
    for line in lines:
        if re.match(r'^(?:(?:grand|net)\s+)?total(?:\s+(?:amount|paid|due))?\b|^amount\s+paid\b', line, re.I) and not re.search(r'\b(?:subtotal|change|tendered)\b', line, re.I):
            values = re.findall(r'(?<![\w.])\d[\d,]*\.\d{2}(?!\d)', line)
            if len(values) == 1:
                try:
                    value = Decimal(values[0].replace(',', ''))
                    if 0 < value < Decimal('1000000000000'):
                        totals.add(format(value, '.2f'))
                except InvalidOperation:
                    pass
    amount = next(iter(totals)) if len(totals) == 1 and not foreign else None
    if not amount:
        warnings.append('No unambiguous NGN total found. Enter the amount manually.')
    if foreign:
        warnings.append('A foreign currency was detected. This expense form records NGN; confirm a supported NGN receipt before submitting.')
    dates = set()
    for token in re.findall(r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b', text):
        try:
            parsed = datetime.strptime(token, '%Y-%m-%d' if re.match(r'^\d{4}-', token) else '%d/%m/%Y' if '/' in token else '%d-%m-%Y').date()
            dates.add(parsed.isoformat())
        except ValueError:
            pass
    occurred = next(iter(dates)) if len(dates) == 1 else None
    if occurred and occurred > datetime.now(timezone(timedelta(hours=1))).date().isoformat():
        occurred = None
    if occurred and not re.search(r'\b\d{4}-\d{2}-\d{2}\b', text):
        warnings.append('Receipt date interpreted as day/month/year. Please confirm it.')
    if not occurred:
        warnings.append('No unambiguous date found. Enter the purchase date manually.')
    vendor = lines[0][:120] if lines and 2 <= len(lines[0]) <= 120 and re.search('[A-Za-z]', lines[0]) else None
    return {'suggested': {'vendor': vendor, 'amount': amount, 'occurred_on': occurred},
            'warnings': warnings, 'text': text[:12000]}


if __name__ == '__main__':
    try:
        print(json.dumps({'text': native_text(sys.stdin.buffer.read(2 * 1024 * 1024 + 1), sys.argv[1])}))
    except ReceiptReadError as error:
        print(json.dumps({'error': str(error)}))
