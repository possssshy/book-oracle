"""
Book Oracle — Flask сервер
Запуск: python3 app.py
Потім відкрий: http://localhost:5000
"""
from flask import Flask, request, jsonify, send_from_directory
import pdfplumber
import csv, io, os, json, re, random

app = Flask(__name__, static_folder='.')

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

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

def extract_text(page_lines, line_num, lines_take):
    """Extract and clean text starting from line_num."""
    idx = line_num - 1

    # Step back if line starts with lowercase (continuation of prev line)
    start_idx = idx
    if start_idx > 0:
        target = page_lines[start_idx]
        if target and (target[0].islower() or target[0] in ',:;'):
            start_idx = max(0, start_idx - 1)

    # Collect window of lines
    window_lines = page_lines[start_idx:start_idx + lines_take + 8]

    # Fix hyphenated word-breaks (e.g. "сказа-" + "ла" -> "сказала")
    joined_parts = []
    for line in window_lines:
        if joined_parts and joined_parts[-1].endswith('-'):
            joined_parts[-1] = joined_parts[-1][:-1] + line
        else:
            joined_parts.append(line)
    raw = ' '.join(joined_parts)

    # Find sentence start: capital letter takes priority over dialog dash
    cap_match = re.search(r'[А-ЯІЇЄA-Z]', raw)
    dash_match = re.search(r'[\u2014\-]\s*(?=[а-яіїєА-ЯІЇЄ])', raw)

    if cap_match and dash_match:
        if cap_match.start() <= dash_match.start() + 3:
            raw = raw[cap_match.start():]
        else:
            raw = raw[dash_match.start():]
    elif cap_match:
        raw = raw[cap_match.start():]
    elif dash_match:
        raw = raw[dash_match.start():]

    # Find sentence end: stop at . ! ? after min 40 chars
    min_chars = 40
    max_chars = 400
    endings = [m.end() for m in re.finditer(r'[.!?»][)\s»"\']*', raw)]

    text = raw
    for end in endings:
        candidate = raw[:end].strip()
        if len(candidate) >= min_chars:
            text = candidate
            break

    if len(text) > max_chars:
        text = text[:max_chars].rsplit(' ', 1)[0] + '...'

    return text

def get_random_prophecy(pages, lines_take):
    """Pick a random page and line from the book."""
    page_keys = list(pages.keys())
    # try up to 20 times to find a good line
    for _ in range(20):
        page_key = random.choice(page_keys)
        page_lines = pages[page_key]
        if not page_lines:
            continue
        line_num = random.randint(1, len(page_lines))
        text = extract_text(page_lines, line_num, lines_take)
        if len(text) >= 40:
            return text, page_key, line_num
    # fallback
    page_key = page_keys[0]
    return extract_text(pages[page_key], 1, lines_take), page_key, 1

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
        raw_page = c.get('page', '')
        raw_line = c.get('line', '')

        # Check if coordinates are provided
        has_coords = (
            raw_page is not None and str(raw_page).strip() not in ('', '0') and
            raw_line is not None and str(raw_line).strip() not in ('', '0')
        )

        if not has_coords:
            # Random mode
            text, used_page, used_line = get_random_prophecy(pages, lines_take)
            results.append({
                'email': c.get('email', ''),
                'first_name': c.get('name', ''),
                'prophecy_text': text,
                'prophecy_page': used_page,
                'prophecy_line': used_line,
                'prophecy_source': book_name,
                'found': True,
                'mode': 'random'
            })
            continue

        # Coordinate mode
        page_key = str(raw_page).strip()
        line_num = int(str(raw_line).strip())
        page_lines = pages.get(page_key, [])

        if not page_lines:
            errors.append(f"{c.get('email')} — сторінка {page_key} не знайдена")
            text = f'[сторінка {page_key} не знайдена]'
            found = False
        elif line_num < 1 or line_num > len(page_lines):
            errors.append(f"{c.get('email')} — рядок {line_num} на стор. {page_key} не існує (макс: {len(page_lines)})")
            text = f'[рядок {line_num} не знайдено на стор. {page_key}]'
            found = False
        else:
            text = extract_text(page_lines, line_num, lines_take)
            found = True

        results.append({
            'email': c.get('email', ''),
            'first_name': c.get('name', ''),
            'prophecy_text': text,
            'prophecy_page': page_key,
            'prophecy_line': line_num,
            'prophecy_source': book_name,
            'found': found,
            'mode': 'coordinate'
        })

    return jsonify({'results': results, 'errors': errors})

if __name__ == '__main__':
    print('\n  Book Oracle запущено!')
    print('  Відкрий браузер: http://localhost:5000\n')
    app.run(debug=False, port=5000)
