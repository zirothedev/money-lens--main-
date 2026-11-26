"""Position-based reading for PDF tables that have no usable ruling lines.

Some banks (e.g. Moniepoint) draw rows as shaded bands with no gridlines, so the table detector sees
fragments. Here the table is rebuilt from where each character sits on the page:

* text lines are grouped into blocks; rows are separated by clearly larger vertical gaps than the lines
  inside a row, so a row is one block (wrapped cells and all);
* column boundaries come from the header's x-positions;
* a block whose date cell doesn't start with a date is the tail of a row split across a page break and is
  merged back into the row above.
"""
import re

from pdfplumber.utils import extract_text, extract_words

from .columns import ColumnMap, map_columns

LINE_TOLERANCE = 3        # chars whose tops differ by less than this are on one text line (pt)
BLOCK_GAP = 10            # whitespace larger than this starts a new block (pt)
SAME_LABEL_GAP = 6        # header words closer than this on one line are one label ("Transaction Ref")
COLUMN_TOLERANCE = 3
_HEADER_VOCABULARY = {'date', 'transaction', 'type', 'status', 'ref', 'reference', 'amount', 'debit', 'credit', 'balance',
                      'narration', 'remarks', 'description', 'settlement', 'beneficiary', 'source', 'charge', 'reversal',
                      'before', 'after', 'account', 'name', 'terminal', 'institution', 'time', 'channel', 'value'}
_DATE_START = re.compile(r'^\s*(?:\d{4}\s*-|\d{1,2}\s*[-/]\s*(?:\d{1,2}|[A-Za-z]{3})\s*[-/]|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})')


def read_positioned_table(pdf) -> list[tuple[list[str], ColumnMap, list[list[str]]]] | None:
    """Return the statement's table sections as [(header cells, column map, rows)], or None if there is none.

    * A header anywhere starts a new section with its own column positions (a statement can hold several accounts).
    * A dateless block that is FIRST on its page is the tail of a row split by the page break: merged into the row above.
    * A dateless block that is LAST on its page, followed by a dated row at the top of the next page, is the first
      line(s) of that row: merged into it.
    * A dateless block anywhere else is a title, summary box or footer and is ignored.
    """
    sections: list[dict] = []
    current: dict | None = None
    pending_head: list[str] | None = None
    for page in pdf.pages:
        head, pending_head = pending_head, None
        blocks = _blocks(page.chars)
        for position, block in enumerate(blocks):
            first_block = position == 0
            starts = _header_starts(block)
            if starts is not None:
                header_cells = _cells(block['chars'], starts)
                cmap = map_columns(header_cells)
                if cmap.is_usable:
                    current = {'starts': starts, 'header': header_cells, 'cmap': cmap, 'rows': [],
                               'date_col': cmap.indices['date']}
                    sections.append(current)
            elif current is not None:
                cells = _cells(block['chars'], current['starts'])
                if _DATE_START.match(cells[current['date_col']]):
                    if first_block and head:
                        cells = [f'{h} {c}'.strip() for h, c in zip(head, cells)]
                    current['rows'].append(cells)
                elif first_block and current['rows']:
                    for i, cell in enumerate(cells):
                        if cell:
                            current['rows'][-1][i] = f"{current['rows'][-1][i]} {cell}".strip()
                elif position == len(blocks) - 1:
                    pending_head = cells
    result = [(c['header'], c['cmap'], c['rows']) for c in sections if c['rows']]
    return result or None


def _blocks(chars) -> list[dict]:
    chars = [c for c in chars if c['text'] != '']          # keep real space characters: they split words reliably
    chars.sort(key=lambda c: (c['top'], c['x0']))
    blocks: list[dict] = []
    line_top = None
    for c in chars:
        new_line = line_top is None or c['top'] - line_top > LINE_TOLERANCE
        if new_line:
            line_top = c['top']
        if not blocks or (new_line and c['top'] - blocks[-1]['bottom'] > BLOCK_GAP):
            blocks.append({'top': c['top'], 'bottom': c['bottom'], 'chars': []})
        block = blocks[-1]
        block['chars'].append(c)
        block['bottom'] = max(block['bottom'], c['bottom'])
    return blocks


def _header_starts(block) -> list[float] | None:
    """Column left-edges if this block is a table header, else None."""
    words = extract_words(block['chars'], x_tolerance=2, y_tolerance=2)
    texts = {re.sub(r'[^a-z]', '', w['text'].lower()) for w in words}     # 'Debit(₦)' -> 'debit'
    # A real table header uses many distinct column words; a summary box ("Opening Balance ...") doesn't.
    if 'date' not in texts or len(texts & _HEADER_VOCABULARY) < 6:
        return None
    starts = _column_starts(words)
    return starts if len(starts) >= 6 else None


def _column_starts(words) -> list[float]:
    """Left edge of each header column. Header words on one line that nearly touch form one label."""
    lines: dict[int, list] = {}
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        key = next((k for k in lines if abs(k - w['top']) <= LINE_TOLERANCE), round(w['top']))
        lines.setdefault(key, []).append(w)
    labels = []
    for line in lines.values():
        line.sort(key=lambda w: w['x0'])
        current = dict(x0=line[0]['x0'], x1=line[0]['x1'])
        for w in line[1:]:
            if w['x0'] - current['x1'] <= SAME_LABEL_GAP:
                current['x1'] = w['x1']
            else:
                labels.append(current)
                current = dict(x0=w['x0'], x1=w['x1'])
        labels.append(current)
    starts: list[float] = []
    for x0 in sorted(label['x0'] for label in labels):
        if not starts or x0 - starts[-1] > COLUMN_TOLERANCE:
            starts.append(x0)
    return starts


def _cells(chars, starts) -> list[str]:
    buckets: list[list] = [[] for _ in starts]
    for c in chars:
        index = 0
        for i, left in enumerate(starts):
            if c['x0'] >= left - COLUMN_TOLERANCE:
                index = i
        buckets[index].append(c)
    return [re.sub(r'\s+', ' ', extract_text(b, x_tolerance=2, y_tolerance=3) or '').strip() if b else '' for b in buckets]
