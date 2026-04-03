"""
Generates sample data files for TLF Output Generator:
  1. sample_shell_annotated.png  — annotated oncology efficacy mock shell
  2. sample_adam_specs.xlsx      — sample ADRS AdaM dataset specifications
Run once:  python data/generate_samples.py
"""

import os
from pathlib import Path

OUT_DIR = Path(__file__).parent

# ─────────────────────────────────────────────────────────────────
# 1. Annotated PNG mock shell
# ─────────────────────────────────────────────────────────────────
def make_annotated_shell():
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1100, 780
    BG          = (255, 255, 255)
    BLACK       = (0,   0,   0)
    HEADER_BG   = (30,  60, 110)
    HEADER_FG   = (255, 255, 255)
    ALT_ROW     = (240, 245, 255)
    BORDER      = (180, 190, 210)
    ANN_BOX     = (255, 80,  40)   # annotation callout colour
    ANN_TEXT    = (200, 30,  10)
    ANN_LINE    = (220, 60,  20)
    GRID_LINE   = (210, 215, 225)

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ── try to load a decent system font; fall back gracefully ──
    def font(size, bold=False):
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/Arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
        ]
        for path in candidates:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    f_title   = font(13, bold=True)
    f_sub     = font(11)
    f_hdr     = font(11, bold=True)
    f_cell    = font(10)
    f_ann     = font(10, bold=True)
    f_ann_sm  = font(9)

    # ── table geometry ──
    L, T = 60, 120          # left / top of table body
    COL_W = [220, 150, 150, 150, 150]   # stub + 4 data cols
    ROW_H = 28
    COLS  = len(COL_W)

    col_x = [L]
    for w in COL_W[:-1]:
        col_x.append(col_x[-1] + w)
    TABLE_W = sum(COL_W)

    # ── title block ──
    draw.text((L, 18), "TLF Output Generator — Sample Oncology Efficacy Shell", font=f_title, fill=BLACK)
    draw.text((L, 38), "Table 14.3.1: Summary of Tumor Response by Best Overall Response", font=f_title, fill=BLACK)
    draw.text((L, 56), "Full Analysis Set (FAS) | Data Source: ADRS", font=f_sub, fill=(80, 80, 80))
    draw.text((L, 72), "Parameter: Best Overall Response (PARAMCD = 'BOR')", font=f_sub, fill=(80, 80, 80))
    draw.line([(L, 94), (L + TABLE_W, 94)], fill=BORDER, width=1)

    # ── header row ──
    headers = ["Response Category", "Placebo\n(N=xx)", "Drug A 50mg\n(N=xx)", "Drug A 100mg\n(N=xx)", "Total\n(N=xx)"]
    draw.rectangle([L, T, L + TABLE_W, T + ROW_H * 2], fill=HEADER_BG)
    for i, (hdr, x) in enumerate(zip(headers, col_x)):
        lines = hdr.split("\n")
        for j, line in enumerate(lines):
            draw.text((x + 6, T + 4 + j * 14), line, font=f_hdr, fill=HEADER_FG)

    # ── data rows ──
    rows = [
        ("Best Overall Response",             "",         "",         "",         ""),
        ("  Complete Response (CR)",           "x (x.x%)", "x (x.x%)", "x (x.x%)", "x (x.x%)"),
        ("  Partial Response (PR)",            "x (x.x%)", "x (x.x%)", "x (x.x%)", "x (x.x%)"),
        ("  Stable Disease (SD)",              "x (x.x%)", "x (x.x%)", "x (x.x%)", "x (x.x%)"),
        ("  Progressive Disease (PD)",         "x (x.x%)", "x (x.x%)", "x (x.x%)", "x (x.x%)"),
        ("  Not Evaluable / Missing",          "x (x.x%)", "x (x.x%)", "x (x.x%)", "x (x.x%)"),
        ("Overall Response Rate (CR+PR)",      "x (x.x%)", "x (x.x%)", "x (x.x%)", "x (x.x%)"),
        ("  95% CI (Clopper-Pearson)",         "(x.x, x.x)","(x.x, x.x)","(x.x, x.x)","(x.x, x.x)"),
        ("Disease Control Rate (CR+PR+SD)",    "x (x.x%)", "x (x.x%)", "x (x.x%)", "x (x.x%)"),
        ("  95% CI (Clopper-Pearson)",         "(x.x, x.x)","(x.x, x.x)","(x.x, x.x)","(x.x, x.x)"),
        ("Duration of Response (months)",      "",         "",         "",         ""),
        ("  Median (95% CI)",                  "x.x (x.x, x.x)","x.x (x.x, x.x)","x.x (x.x, x.x)","x.x (x.x, x.x)"),
    ]

    body_top = T + ROW_H * 2
    for r_idx, row in enumerate(rows):
        y0 = body_top + r_idx * ROW_H
        y1 = y0 + ROW_H
        bg = ALT_ROW if r_idx % 2 == 1 else BG
        draw.rectangle([L, y0, L + TABLE_W, y1], fill=bg)
        for c_idx, (cell, x) in enumerate(zip(row, col_x)):
            bold = (c_idx == 0 and not row[0].startswith("  "))
            draw.text((x + 6, y0 + 6), cell, font=f_hdr if bold else f_cell, fill=BLACK)

    # ── grid lines ──
    total_rows = len(rows)
    table_bottom = body_top + total_rows * ROW_H
    # horizontal
    for r in range(total_rows + 1):
        y = body_top + r * ROW_H
        draw.line([(L, y), (L + TABLE_W, y)], fill=GRID_LINE, width=1)
    # vertical
    for x in col_x:
        draw.line([(x, T), (x, table_bottom)], fill=GRID_LINE, width=1)
    draw.line([(L + TABLE_W, T), (L + TABLE_W, table_bottom)], fill=GRID_LINE, width=1)
    # outer border
    draw.rectangle([L, T, L + TABLE_W, table_bottom], outline=BORDER, width=2)

    # ── annotations ──
    def callout(ax, ay, bx, by, label, sub=""):
        """Draw annotation arrow from (ax,ay) to (bx,by) with a label box."""
        draw.line([(ax, ay), (bx, by)], fill=ANN_LINE, width=2)
        draw.ellipse([(bx-4, by-4), (bx+4, by+4)], fill=ANN_LINE)
        # box
        bw = max(len(label), len(sub)) * 7 + 10
        bh = 30 if sub else 18
        draw.rectangle([(ax-4, ay-bh), (ax+bw, ay+4)], fill=(255, 245, 240), outline=ANN_BOX, width=1)
        draw.text((ax, ay-bh+3), label, font=f_ann, fill=ANN_TEXT)
        if sub:
            draw.text((ax, ay-bh+16), sub, font=f_ann_sm, fill=ANN_TEXT)

    # Annotation 1: Dataset
    callout(ax=720, ay=T-12, bx=col_x[0]+110, by=T+12,
            label="Dataset: ADRS",
            sub="adam_specs → dataset_source")

    # Annotation 2: PARAMCD filter
    callout(ax=750, ay=T+62, bx=col_x[0]+60, by=body_top+4,
            label="Filter: PARAMCD = 'BOR'",
            sub="(Best Overall Response record)")

    # Annotation 3: AVALC variable
    callout(ax=730, ay=body_top+90, bx=col_x[0]+50, by=body_top + 1*ROW_H + 14,
            label="analysis_var: AVALC",
            sub="Response category (CR/PR/SD/PD)")

    # Annotation 4: ORR derived row
    callout(ax=730, ay=body_top+200, bx=col_x[0]+80, by=body_top + 6*ROW_H + 14,
            label="Derived: ORR = AVALC in (CR, PR)",
            sub="Condition from adam_specs codelist")

    # Annotation 5: Treatment column
    callout(ax=800, ay=H-60, bx=col_x[2]+75, by=T+10,
            label="Treatment var: TRTP",
            sub="(planned treatment variable)")

    # ── footnote ──
    draw.line([(L, table_bottom + 10), (L + TABLE_W, table_bottom + 10)], fill=BORDER, width=1)
    draw.text((L, table_bottom + 16), "Note: Percentages based on number of subjects in each treatment group (N).", font=f_ann_sm, fill=(80,80,80))
    draw.text((L, table_bottom + 30), "CI = Confidence Interval; CR = Complete Response; PR = Partial Response; SD = Stable Disease; PD = Progressive Disease.", font=f_ann_sm, fill=(80,80,80))

    # ── legend box ──
    lx, ly = L, H - 55
    draw.rectangle([(lx, ly), (lx+500, ly+45)], fill=(255,250,240), outline=ANN_BOX, width=1)
    draw.text((lx+6, ly+4),  "ANNOTATION LEGEND", font=f_ann, fill=ANN_TEXT)
    draw.text((lx+6, ly+18), "Red callouts = metadata used to generate R code (dataset, variables, filters, conditions)", font=f_ann_sm, fill=ANN_TEXT)
    draw.text((lx+6, ly+32), "Upload this shell in Step 1 · Upload AdaM specs in Step 2 · Generate R code in Step 4", font=f_ann_sm, fill=ANN_TEXT)

    out = OUT_DIR / "sample_shell_annotated.png"
    img.save(str(out), dpi=(150, 150))
    print(f"Saved: {out}")


# ─────────────────────────────────────────────────────────────────
# 2. Sample AdaM specs Excel (ADRS domain)
# ─────────────────────────────────────────────────────────────────
def make_adam_specs():
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()

    # ── helper styles ──
    HDR_FILL   = PatternFill("solid", fgColor="1E3C6E")
    HDR_FONT   = Font(bold=True, color="FFFFFF", size=10)
    SUB_FILL   = PatternFill("solid", fgColor="DCE6F1")
    SUB_FONT   = Font(bold=True, size=10)
    CELL_FONT  = Font(size=9)
    ALT_FILL   = PatternFill("solid", fgColor="F2F6FC")
    thin = Side(style="thin", color="B0B8C8")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(wrap_text=True, vertical="top")

    def hdr_row(ws, row, values):
        for col, val in enumerate(values, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.fill = HDR_FILL; c.font = HDR_FONT; c.alignment = wrap; c.border = border

    def data_row(ws, row, values, alt=False):
        fill = ALT_FILL if alt else PatternFill()
        for col, val in enumerate(values, 1):
            c = ws.cell(row=row, column=col, value=val)
            c.font = CELL_FONT; c.alignment = wrap; c.border = border
            if alt: c.fill = fill

    # ── Sheet 1: ADRS Variables ──
    ws1 = wb.active
    ws1.title = "ADRS_Variables"
    ws1.sheet_view.showGridLines = False

    # title
    ws1.merge_cells("A1:J1")
    t = ws1["A1"]
    t.value = "AdaM Dataset Specifications — ADRS (Oncology Response Dataset)"
    t.font = Font(bold=True, size=12, color="1E3C6E")
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[1].height = 24

    ws1.merge_cells("A2:J2")
    t2 = ws1["A2"]
    t2.value = "Standard: CDISC ADaM ADRS v1.0 | Population Flag: FASFL = 'Y' | Key Parameter: PARAMCD = 'BOR'"
    t2.font = Font(italic=True, size=10, color="555555")
    t2.alignment = Alignment(horizontal="center")

    cols = ["Variable", "Label", "Type", "Length", "Format", "Origin", "Codelist / Values", "ADaM Core", "Key Flag", "Programmer Notes"]
    hdr_row(ws1, 3, cols)

    variables = [
        ("STUDYID",  "Study Identifier",              "Char", 20,  "",           "SDTM",    "",                          "Req",    "",    ""),
        ("DOMAIN",   "Domain Abbreviation",           "Char", 2,   "",           "SDTM",    "ADRS",                      "Req",    "",    "Always 'ADRS'"),
        ("USUBJID",  "Unique Subject Identifier",     "Char", 40,  "",           "SDTM",    "",                          "Req",    "",    "Key for merging to ADSL"),
        ("SUBJID",   "Subject Identifier",            "Char", 20,  "",           "SDTM",    "",                          "Req",    "",    ""),
        ("SITEID",   "Study Site Identifier",         "Char", 20,  "",           "SDTM",    "",                          "Perm",   "",    ""),
        ("TRTP",     "Planned Treatment",             "Char", 200, "",           "Derived", "TRT01P from ADSL",          "Req",    "",    "Use for column grouping in Tplyr"),
        ("TRTA",     "Actual Treatment",              "Char", 200, "",           "Derived", "TRT01A from ADSL",          "Req",    "",    "Use TRTA for safety tables"),
        ("PARAMCD",  "Parameter Code",                "Char", 8,   "",           "Derived", "BOR=Best Overall Response\nORR=Overall Response Rate\nDCR=Disease Control Rate", "Req", "KEY", "Filter: PARAMCD='BOR' for response table"),
        ("PARAM",    "Parameter Description",         "Char", 200, "",           "Derived", "",                          "Req",    "",    "Long form of PARAMCD"),
        ("AVAL",     "Analysis Value (numeric)",      "Num",  8,   "",           "Derived", "1=Responder, 0=Non-resp",   "Req",    "",    "Used for ORR: AVAL=1 when AVALC in ('CR','PR')"),
        ("AVALC",    "Analysis Value (character)",    "Char", 200, "",           "Derived", "CR=Complete Response\nPR=Partial Response\nSD=Stable Disease\nPD=Progressive Disease\nNE=Not Evaluable", "Req", "KEY", "Primary analysis variable for response category"),
        ("ANL01FL",  "Analysis 01 Flag",              "Char", 1,   "",           "Derived", "Y / N",                     "Req",    "KEY", "Y = include in primary analysis. Filter: ANL01FL='Y'"),
        ("FASFL",    "Full Analysis Set Flag",        "Char", 1,   "",           "Derived", "Y / N",                     "Req",    "KEY", "Y = subject in FAS population. Filter: FASFL='Y'"),
        ("DTYPE",    "Derivation Type",               "Char", 8,   "",           "Derived", "INTERIM",                   "Perm",   "",    "Blank for observed records"),
        ("VISITNUM", "Visit Number",                  "Num",  8,   "",           "SDTM",    "",                          "Perm",   "",    ""),
        ("VISIT",    "Visit Name",                    "Char", 200, "",           "SDTM",    "",                          "Perm",   "",    ""),
        ("ADT",      "Analysis Date",                 "Num",  8,   "DATE9.",     "Derived", "",                          "Perm",   "",    "Date of response assessment"),
        ("ADTM",     "Analysis Datetime",             "Num",  8,   "DATETIME.",  "Derived", "",                          "Perm",   "",    ""),
    ]

    for i, row in enumerate(variables):
        data_row(ws1, i + 4, row, alt=(i % 2 == 1))

    # Column widths
    widths = [14, 26, 6, 8, 10, 12, 36, 10, 8, 42]
    for col, w in enumerate(widths, 1):
        ws1.column_dimensions[get_column_letter(col)].width = w
    ws1.row_dimensions[3].height = 18

    # ── Sheet 2: Analysis Conditions ──
    ws2 = wb.create_sheet("Analysis_Conditions")
    ws2.sheet_view.showGridLines = False

    ws2.merge_cells("A1:G1")
    t = ws2["A1"]
    t.value = "ADRS — Analysis Conditions and Table Mapping"
    t.font = Font(bold=True, size=12, color="1E3C6E")
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 24

    hdr_row(ws2, 2, ["Table Output", "Population Filter", "PARAMCD Filter", "ANL01FL", "Primary Variable", "Derived Condition", "R Skill to Apply"])

    conditions = [
        ("Table 14.3.1 Tumor Response",   "FASFL='Y'", "PARAMCD='BOR'",  "ANL01FL='Y'", "AVALC",   "n(%) by AVALC category",                          "SKILL 4 (group_count)"),
        ("Table 14.3.2 ORR",              "FASFL='Y'", "PARAMCD='ORR'",  "ANL01FL='Y'", "AVAL",    "ORR = AVAL=1; CI = Clopper-Pearson",              "SKILL 4 + CI layer"),
        ("Table 14.3.3 DCR",              "FASFL='Y'", "PARAMCD='DCR'",  "ANL01FL='Y'", "AVAL",    "DCR = AVALC in (CR,PR,SD)",                       "SKILL 4 + CI layer"),
        ("Table 14.3.4 DOR (KM)",         "FASFL='Y'", "PARAMCD='DOR'",  "ANL01FL='Y'", "AVAL",    "Median + 95% CI via survfit; CNSR=1 if censored", "SKILL 9 (survival/KM)"),
        ("Table 14.3.5 PFS (KM)",         "FASFL='Y'", "PARAMCD='PFS'",  "ANL01FL='Y'", "AVAL",    "Median PFS; CNSR=0=event",                        "SKILL 9 (survival/KM)"),
        ("Table 14.3.6 OS (KM)",          "FASFL='Y'", "PARAMCD='OS'",   "ANL01FL='Y'", "AVAL",    "Median OS; CNSR=0=event",                         "SKILL 9 (survival/KM)"),
    ]
    for i, row in enumerate(conditions):
        data_row(ws2, i + 3, row, alt=(i % 2 == 1))

    ws2_widths = [28, 16, 18, 12, 18, 38, 24]
    for col, w in enumerate(ws2_widths, 1):
        ws2.column_dimensions[get_column_letter(col)].width = w

    # ── Sheet 3: Codelist ──
    ws3 = wb.create_sheet("Codelists")
    ws3.sheet_view.showGridLines = False

    ws3.merge_cells("A1:E1")
    t = ws3["A1"]
    t.value = "ADRS Codelist Reference"
    t.font = Font(bold=True, size=12, color="1E3C6E")
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws3.row_dimensions[1].height = 24

    hdr_row(ws3, 2, ["Codelist Name", "Code", "Decode", "Used In", "Notes"])

    codes = [
        ("AVALC (Response)", "CR",  "Complete Response",     "AVALC",   "No residual tumor"),
        ("AVALC (Response)", "PR",  "Partial Response",      "AVALC",   ">=30% reduction in sum of diameters"),
        ("AVALC (Response)", "SD",  "Stable Disease",        "AVALC",   "Neither CR/PR nor PD criteria"),
        ("AVALC (Response)", "PD",  "Progressive Disease",   "AVALC",   ">=20% increase in sum of diameters"),
        ("AVALC (Response)", "NE",  "Not Evaluable",         "AVALC",   "Missing or unevaluable"),
        ("NY (Flags)",       "Y",   "Yes",                   "ANL01FL, FASFL", "Inclusion flag"),
        ("NY (Flags)",       "N",   "No",                    "ANL01FL, FASFL", "Exclusion flag"),
        ("TRTP (Treatment)", "Placebo",     "Placebo",       "TRTP",    "Control arm"),
        ("TRTP (Treatment)", "Drug A 50mg", "Drug A 50mg",   "TRTP",    "Low dose arm"),
        ("TRTP (Treatment)", "Drug A 100mg","Drug A 100mg",  "TRTP",    "High dose arm"),
    ]
    for i, row in enumerate(codes):
        data_row(ws3, i + 3, row, alt=(i % 2 == 1))

    ws3_widths = [22, 14, 26, 22, 40]
    for col, w in enumerate(ws3_widths, 1):
        ws3.column_dimensions[get_column_letter(col)].width = w

    out = OUT_DIR / "sample_adam_specs.xlsx"
    wb.save(str(out))
    print(f"Saved: {out}")


if __name__ == "__main__":
    make_annotated_shell()
    make_adam_specs()
    print("Sample files created successfully.")
