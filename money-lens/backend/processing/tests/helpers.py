"""Builders for realistic PDF statement fixtures (reportlab is a test-only dependency)."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

FIXTURES = Path(__file__).parent / 'fixtures'

HEADER = ['Date', 'Description', 'Debit', 'Credit', 'Balance']
ROWS = [
    ['03-Sep-2025', 'NIP TRANSFER TO AHMED MUSA/School fees', '15,000.00', '', '985,000.00'],
    ['08-Sep-2025', 'TRF TO AHMED MUSA', '10,000.00', '', '975,000.00'],
    ['09-Sep-2025', 'NIP TRANSFER FROM GRACE OKAFOR FOR rent', '', '50,000.00', '1,025,000.00'],
    ['10-Sep-2025', 'POS PURCHASE SHOPRITE', '4,500.00', '', '1,020,500.00'],
]


def build_table_pdf(path, rows=ROWS, header=HEADER, repeat_page=False):
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4))
    table = Table([header] + rows, repeatRows=1)
    table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    story = [table]
    if repeat_page:  # simulates a page extracted twice
        from reportlab.platypus import PageBreak
        story += [PageBreak(), Table([header] + rows, repeatRows=1, style=[('GRID', (0, 0), (-1, -1), 0.5, colors.black)])]
    doc.build(story)
    return path


def build_text_pdf(path, lines):
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(30, y, line)
        y -= 16
    c.save()
    return path


def build_blank_pdf(path):
    c = canvas.Canvas(str(path), pagesize=A4)
    c.showPage()
    c.save()
    return path


def build_gtco_style_pdf(path, entries, opening='100,000.00', period='01-Aug-2026 to 26-Sep-2026',
                         currency='NIGERIAN NAIRA'):
    """A statement laid out like a GTBank PDF: period line, key/value header block, then the transaction table.

    entries: (date, reference, debit, credit, remarks) with amounts as strings or ''. Balances are computed.
    Returns the totals the header block prints, so tests can reconcile extraction against the statement itself.
    """
    from decimal import Decimal

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer

    def money(s):
        return Decimal(s.replace(',', '')) if s else Decimal('0')

    cell = ParagraphStyle('cell', fontSize=7, leading=8.5)
    balance = money(opening)
    total_debit = total_credit = Decimal('0')
    rows = [['Trans. Date', 'Value. Date', 'Reference', 'Debits', 'Credits', 'Balance', 'Originating Branch', 'Remarks']]
    for date_text, ref, debit, credit, remarks in entries:
        balance += money(credit) - money(debit)
        total_debit += money(debit)
        total_credit += money(credit)
        rows.append([date_text, date_text, Paragraph(ref, cell), debit, credit, f'{balance:,.2f}', '635 AKIN ADESOLA',
                     Paragraph(remarks, cell)])   # long references wrap onto two lines, as in the real statement
    header_block = [['Print. Date', '26-Sep-2026'], ['Account No', '0000000000'], ['Currency', currency],
                    ['Total Debit', f'{total_debit:,.2f}'], ['Total Credit', f'{total_credit:,.2f}'],
                    ['Closing Balance', f'{balance:,.2f}'], ['Opening Balance', opening]]
    grid = TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('FONTSIZE', (0, 0), (-1, -1), 7)])
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=30, rightMargin=30)
    story = [Paragraph(f'Statement Period :{period}', cell), Spacer(1, 8),
             Table(header_block, style=grid, hAlign='LEFT'), Spacer(1, 12),
             Table(rows, colWidths=[55, 55, 85, 50, 50, 55, 85, 330], repeatRows=1, style=grid)]
    doc.build(story)
    return {'total_debit': total_debit, 'total_credit': total_credit, 'closing': balance}


def build_moniepoint_style_pdf(path, entries, opening='5,000.00'):
    """A borderless, 19-column statement laid out like a Moniepoint PDF: shaded alternating rows, no gridlines,
    every cell wrapped over several lines, and a summary block above the table. Returns the printed totals."""
    import textwrap
    from decimal import Decimal

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer

    def money(v):
        return Decimal(v.replace(',', '')) if v else Decimal('0')

    def wrap(text, width):
        return '\n'.join(textwrap.wrap(text, width, break_long_words=False)) if text else ''

    widths = [40.5, 52.9, 79.1, 69.8, 55.7, 34.8, 365.2, 56.4, 69.8, 65.1, 65.2, 52.8, 52.9, 46.5, 74.0, 66.8, 62.1, 69.1, 270]
    header = ['Date', 'Account\nName', 'Transaction\nType', 'Transaction\nStatus', 'Terminal\nID', 'RRN', 'Transaction Ref',
              'Reversal\nStatus', 'Transaction\nAmount', 'Settlement\nDebit', 'Settlement\nCredit', 'Balance\nBefore',
              'Balance\nAfter', 'Charge', 'Beneficiary', 'Beneficiary\nInstitution', 'Source', 'Source\nInstitution', 'Narration']
    balance = money(opening)
    total_debit = total_credit = Decimal('0')
    rows = [header]
    for e in entries:
        debit, credit = money(e.get('debit', '')), money(e.get('credit', ''))
        before, balance = balance, balance - debit + credit
        total_debit += debit
        total_credit += credit
        y, mo, rest = e['when'].split('-', 2)
        day, clock = rest.split('T')
        hh, mm, ss = clock.split(':')
        rows.append([
            f'{y}-\n{mo}-\n{day}T{hh}:\n{mm}:{ss}', 'TEST\nUSER\nONE', e.get('type', ''), 'COMPLETED', '', '', e['ref'], 'N/A',
            e.get('amount', ''), f'{debit:,.2f}', f'{credit:,.2f}', f'{before:,.2f}', f'{balance:,.2f}', e.get('charge', ''),
            wrap(e.get('ben', ''), 11), wrap(e.get('inst', ''), 11), e.get('source', '5311023949'), wrap(e.get('src_inst', ''), 11),
            wrap(e.get('narration', ''), 52)])
    style = TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 6), ('LEADING', (0, 0), (-1, -1), 6.3), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 1), (-1, -1), 24), ('BOTTOMPADDING', (0, 1), (-1, -1), 24),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 20),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#c9c4bb'), colors.white]),   # bands only, no gridlines
    ])
    small = ParagraphStyle('s', fontSize=7, leading=9)
    doc = SimpleDocTemplate(str(path), pagesize=(1705, 842), leftMargin=46.5, rightMargin=20, topMargin=40, bottomMargin=30)
    story = [Paragraph('Account Statement', small), Paragraph('Business Name TEST USER ONE', small),
             Paragraph('Account Number 5311023949', small), Paragraph('Currency', small),
             Paragraph('Date 28/07/2026 - 26/10/2026', small), Spacer(1, 6),
             Paragraph(f'Opening Balance {opening}', small), Paragraph(f'Total Debits {total_debit:,.2f}', small),
             Paragraph(f'Total Credits {total_credit:,.2f}', small), Paragraph(f'Closing Balance {balance:,.2f}', small),
             Spacer(1, 40), Table(rows, colWidths=widths, style=style, repeatRows=0, hAlign='LEFT')]
    doc.build(story)
    return {'total_debit': total_debit, 'total_credit': total_credit, 'closing': balance}


def build_opay_style_pdf(path, sections):
    """A statement laid out like an OPay PDF: several account sections, each with its own title, summary box and
    table (shaded rows, no gridlines, tiny font, pipe-delimited descriptions). Returns each section's printed totals.

    sections: [{'title': 'Wallet Account', 'opening': '0.00', 'rows': [(time, description, debit, credit), ...]}]
    """
    import os
    import textwrap
    from decimal import Decimal

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import PageBreak, Paragraph, Spacer

    font, naira = 'Helvetica', 'N'
    for candidate in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'C:/Windows/Fonts/arial.ttf'):
        if os.path.exists(candidate):
            pdfmetrics.registerFont(TTFont('OpayTest', candidate))
            font, naira = 'OpayTest', '₦'
            break

    def money(v):
        return Decimal(v.replace(',', '')) if v else Decimal('0')

    widths = [61, 48, 121, 38, 38, 42, 57, 100]
    small = ParagraphStyle('s', fontName=font, fontSize=6, leading=8)
    story, printed = [Paragraph('Account Statement', small), Spacer(1, 20)], []
    for number, section in enumerate(sections):
        balance = money(section['opening'])
        total_debit = total_credit = Decimal('0')
        rows = [['Trans. Time', 'Value Date', 'Description', f'Debit({naira})', f'Credit({naira})', f'Balance After\n({naira})',
                 'Channel', 'Transaction\nReference']]
        for index, (when, description, debit, credit) in enumerate(section['rows']):
            balance += money(credit) - money(debit)
            total_debit += money(debit)
            total_credit += money(credit)
            day = when.split(' ')[0:3]
            rows.append([when.replace(' 0', '\n0', 1) if ' 0' in when else when, ' '.join(day),
                         '\n'.join(textwrap.wrap(description, 34, break_long_words=False)),
                         debit or '--', credit or '--', f'{balance:,.2f}', 'Mobile', f'2609{number}{index:018d}'])
        story += [Paragraph(f"{section['title']} Period: 26 Sep 2026 - 25 Oct 2026", small), Spacer(1, 14),
                  Paragraph(f"Opening Balance {naira}{section['opening']}  Total Debit {naira}{total_debit:,.2f}  Debit Count "
                            f"{sum(1 for r in section['rows'] if r[2])}", small),
                  Paragraph(f"Closing Balance {naira}{balance:,.2f}  Total Credit {naira}{total_credit:,.2f}  Credit Count "
                            f"{sum(1 for r in section['rows'] if r[3])}", small), Spacer(1, 22),
                  Table(rows, colWidths=widths, hAlign='LEFT', style=TableStyle([
                      ('FONTNAME', (0, 0), (-1, -1), font), ('FONTSIZE', (0, 0), (-1, -1), 5), ('LEADING', (0, 0), (-1, -1), 6),
                      ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                      ('TOPPADDING', (0, 1), (-1, -1), 8), ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                      ('BOTTOMPADDING', (0, 0), (-1, 0), 14),
                      ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f2f2f2'), colors.white])])),
                  Spacer(1, 30)]
        printed.append({'total_debit': total_debit, 'total_credit': total_credit, 'closing': balance})
    SimpleDocTemplate(str(path), pagesize=(595, 842), leftMargin=71, rightMargin=19, topMargin=40, bottomMargin=30).build(story)
    return printed
