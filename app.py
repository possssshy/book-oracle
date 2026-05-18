"""
Book Oracle — Flask сервер
Запуск: python3 app.py
Потім відкрий: http://localhost:5000
"""
from flask import Flask, request, jsonify, send_from_directory
import pdfplumber
import csv, io, os, json, re

app = Flask(__name__, static_folder='.')

# ── Головна сторінка ──────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# ── Завантаження PDF ──────────────────────────────────────────────────────────
@app.route('/parse-pdf', methods=['POST'])
def parse_pdf():
    if 'pdf' not in request.files:
        return jsonify({'error': 'Файл не надіслано'}), 400

    f = request.files['pdf']
    pages = {}
    try:
        with pdfplumber.open(f) as pdf:
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    if lines:
                        pages[str(i)] = lines
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({
        'total_pages': total,
        'total_lines': sum(len(v) for v in pages.values()),
        'pages': pages
    })

# ── Генерація CSV ─────────────────────────────────────────────────────────────
@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    pages = data.get('pages', {})
    contacts = data.get('contacts', [])
    lines_take = int(data.get('lines_take', 2))
    book_name = data.get('book_name', 'Книга')

    results = []
    errors = []

    for c in contacts:
        page_key = str(c.get('page', ''))
        line_num = int(c.get('line', 0))
        page_lines = pages.get(page_key, [])

        if not page_lines:
            errors.append(f"{c.get('email')} — сторінка {page_key} не знайдена")
            text = f'[сторінка {page_key} не знайдена]'
        elif line_num < 1 or line_num > len(page_lines):
            errors.append(f"{c.get('email')} — рядок {line_num} на стор. {page_key} не існує (макс: {len(page_lines)})")
            text = f'[рядок {line_num} не знайдено на стор. {page_key}]'
        else:
            idx = line_num - 1

            # If the target line starts with a lowercase letter or a continuation
            # (word break from previous line), step back to find the real start
            start_idx = idx
            if start_idx > 0:
                target = page_lines[start_idx]
                # starts with lowercase or dash continuation from prev line
                if target and (target[0].islower() or target[0] in ',:;'):
                    start_idx = max(0, start_idx - 1)

            # Collect a window of lines starting from adjusted position
            window_lines = page_lines[start_idx:start_idx + lines_take + 8]

            # Join lines, fixing hyphenated word-breaks (e.g. "сказа-" + "ла" → "сказала")
            joined_parts = []
            for i, line in enumerate(window_lines):
                if joined_parts and joined_parts[-1].endswith('-'):
                    # merge: remove trailing hyphen and join without space
                    joined_parts[-1] = joined_parts[-1][:-1] + line
                else:
                    joined_parts.append(line)
            raw = ' '.join(joined_parts)

            # Find sentence start — find first capital letter or «-» dialog start
            sentence_start = re.search(r'([-«""\u2014]?\s*[А-ЯІЇЄA-Z])', raw)
            if sentence_start:
                raw = raw[sentence_start.start():]

            # Find sentence end — cut at first . ! ? after min_chars
            min_chars = 40
            max_chars = 400
            endings = [m.end() for m in re.finditer(r'[.!?»][)\s»"\']*', raw)]

            text = raw  # fallback
            for end in endings:
                candidate = raw[:end].strip()
                if len(candidate) >= min_chars:
                    text = candidate
                    break

            if len(text) > max_chars:
                text = text[:max_chars].rsplit(' ', 1)[0] + '...'

        results.append({
            'email': c.get('email', ''),
            'first_name': c.get('name', ''),
            'prophecy_text': text,
            'prophecy_page': c.get('page', ''),
            'prophecy_line': c.get('line', ''),
            'prophecy_source': book_name,
            'found': not text.startswith('[')
        })

    return jsonify({'results': results, 'errors': errors})

if __name__ == '__main__':
    print('\n  Book Oracle запущено!')
    print('  Відкрий браузер: http://localhost:5000\n')
    app.run(debug=False, port=5000)
