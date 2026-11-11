"""Converte Caderno_de_Projeto_Silo.md em .docx (subconjunto de Markdown usado no caderno).
Uso: python gerar_docx.py      (requer python-docx)"""
import re
from pathlib import Path
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

aqui = Path(__file__).parent
linhas = (aqui / "Caderno_de_Projeto_Silo.md").read_text(encoding="utf-8").splitlines()

doc = Document()
sec = doc.sections[0]
sec.left_margin = sec.right_margin = Cm(1.8); sec.top_margin = sec.bottom_margin = Cm(1.8)
doc.styles["Normal"].font.name = "Calibri"; doc.styles["Normal"].font.size = Pt(10)
for h, tam in (("Heading 1", 14), ("Heading 2", 12)):
    st = doc.styles[h]; st.font.name = "Calibri"; st.font.size = Pt(tam); st.font.color.rgb = RGBColor(0x2F, 0x6B, 0x3A)

TOKENS = re.compile(r"(\*\*.+?\*\*|\*[^*\s][^*]*?\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")

def runs(par, texto, base_bold=False, tam=None):
    for parte in TOKENS.split(texto):
        if not parte: continue
        if parte.startswith("**") and parte.endswith("**"): r = par.add_run(parte[2:-2]); r.bold = True
        elif parte.startswith("`") and parte.endswith("`"): r = par.add_run(parte[1:-1]); r.font.name = "Consolas"; r.font.size = Pt(8.5); r.bold = base_bold
        elif parte.startswith("[") and "](" in parte: r = par.add_run(re.match(r"\[([^\]]+)\]", parte).group(1)); r.bold = base_bold
        elif parte.startswith("*") and parte.endswith("*") and len(parte) > 2: r = par.add_run(parte[1:-1]); r.italic = True; r.bold = base_bold
        else: r = par.add_run(parte); r.bold = base_bold
        if tam and not (parte.startswith("`")): r.font.size = Pt(tam)

def sombra(cel, cor):
    pr = cel._tc.get_or_add_tcPr(); s = OxmlElement("w:shd")
    s.set(qn("w:val"), "clear"); s.set(qn("w:color"), "auto"); s.set(qn("w:fill"), cor); pr.append(s)

def tabela(bloco):
    cab = [c.strip() for c in bloco[0].strip().strip("|").split("|")]
    corpo = [[c.strip() for c in re.split(r"(?<!\\)\|", l.strip()[1:-1])] for l in bloco[2:]]
    t = doc.add_table(rows=1, cols=len(cab)); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, c in enumerate(cab):
        cel = t.rows[0].cells[i]; cel.text = ""; runs(cel.paragraphs[0], c, base_bold=True, tam=9); sombra(cel, "DDEBDD")
    for lin in corpo:
        cels = t.add_row().cells
        for i, c in enumerate(lin[:len(cab)]):
            cels[i].text = ""
            for k, pedaco in enumerate(c.replace("\\|", "|").split("<br>")):
                par = cels[i].paragraphs[0] if k == 0 else cels[i].add_paragraph()
                par.paragraph_format.space_after = Pt(2); runs(par, pedaco, tam=9)
    doc.add_paragraph()

i = 0
while i < len(linhas):
    l = linhas[i]
    if l.startswith("```"):
        j = i + 1; cod = []
        while not linhas[j].startswith("```"): cod.append(linhas[j]); j += 1
        p = doc.add_paragraph(); r = p.add_run("\n".join(cod)); r.font.name = "Consolas"; r.font.size = Pt(5.5)
        i = j + 1; continue
    if l.startswith("|"):
        j = i
        while j < len(linhas) and linhas[j].startswith("|"): j += 1
        tabela(linhas[i:j]); i = j; continue
    m = re.match(r"^!\[(.*)\]\((.+)\)$", l)
    if m:
        doc.add_picture(str(aqui / m.group(2)), width=Cm(11 if "Wokwi" in m.group(1) else 16))
        cap = doc.add_paragraph(); r = cap.add_run(m.group(1)); r.italic = True; r.font.size = Pt(8.5)
        i += 1; continue
    if l.startswith("# "): doc.add_heading(l[2:], 1)
    elif l.startswith("## "): doc.add_heading(l[3:], 2)
    elif re.match(r"^\d+\. ", l): runs(doc.add_paragraph(style="List Number"), re.sub(r"^\d+\. ", "", l))
    elif l.strip(): runs(doc.add_paragraph(), l)
    i += 1

saida = aqui / "Caderno_de_Projeto_Silo.docx"
doc.save(saida); print("ok ->", saida)
