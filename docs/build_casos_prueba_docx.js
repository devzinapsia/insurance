// Usage: npm install docx@9.5.1 && node docs/build_casos_prueba_docx.js docs/casos_prueba_manual.md docs/casos_prueba_manual.docx
// Build docs/casos_prueba_manual.docx from docs/casos_prueba_manual.md.
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, LevelFormat, AlignmentType, Footer, Header,
  PageNumber, TableOfContents, PageBreak,
} = require("docx");

const [src, out] = process.argv.slice(2);
const lines = fs.readFileSync(src, "utf8").split("\n");

const FONT = "Arial";
const ACCENT = "1F4E79";
const PAGE_W = 11906, MARGIN = 1134; // A4, 2 cm margins
const CONTENT_W = PAGE_W - 2 * MARGIN;
const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const borders = { top: border, bottom: border, left: border, right: border };

// Inline markdown: **bold**, *italic*, `code`.
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: "Consolas", ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

function table(rows) {
  const n = rows[0].length;
  const widths = Array(n).fill(Math.floor(CONTENT_W / n));
  widths[n - 1] = CONTENT_W - widths.slice(0, -1).reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((cells, r) => new TableRow({
      tableHeader: r === 0,
      children: cells.map((c, i) => new TableCell({
        borders,
        width: { size: widths[i], type: WidthType.DXA },
        shading: r === 0 ? { fill: "DCE6F1", type: ShadingType.CLEAR, color: "auto" } : undefined,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [new Paragraph({ children: runs(c, r === 0 ? { bold: true } : {}) })],
      })),
    })),
  });
}

// Result box closing each test case.
function resultBox() {
  const w1 = 3200, w2 = CONTENT_W - w1;
  const cell = (w, text, fill) => new TableCell({
    borders, width: { size: w, type: WidthType.DXA },
    shading: fill ? { fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    children: [new Paragraph({ children: runs(text) })],
  });
  return [
    new Paragraph({ spacing: { before: 120 }, children: [] }),
    new Table({
      width: { size: CONTENT_W, type: WidthType.DXA },
      columnWidths: [w1, w2],
      rows: [
        new TableRow({ children: [cell(w1, "**Resultado**", "F2F2F2"), cell(w2, "☐ OK     ☐ Falla     ☐ No aplica")] }),
        new TableRow({ children: [cell(w1, "**Fecha / quién**", "F2F2F2"), cell(w2, "")] }),
        new TableRow({ children: [cell(w1, "**Observaciones**", "F2F2F2"), cell(w2, "")] }),
      ],
    }),
  ];
}

const children = [];
let inCase = false;
let listKind = null; // current list paragraph being built
let pending = null;  // {kind, level, text}

function flush() {
  if (!pending) return;
  const { kind, level, text } = pending;
  if (kind === "p") children.push(new Paragraph({ spacing: { after: 120 }, children: runs(text) }));
  else children.push(new Paragraph({
    numbering: { reference: kind === "ol" ? `ol${numCounter}` : "bullets", level },
    spacing: { after: 60 },
    children: runs(text),
  }));
  pending = null;
}
let numCounter = 0;
let prevWasOl = false;
const numberingConfigs = [];
function newOl() {
  numCounter += 1;
  numberingConfigs.push({
    reference: `ol${numCounter}`,
    levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 567, hanging: 340 } } } },
    { level: 1, format: LevelFormat.LOWER_LETTER, text: "%2)", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 1134, hanging: 340 } } } }],
  });
}
function closeCase() {
  flush();
  if (inCase) children.push(...resultBox());
  inCase = false;
}

let i = 0;
let title = "";
while (i < lines.length) {
  const raw = lines[i];
  const line = raw.trimEnd();
  if (line.startsWith("# ")) { title = line.slice(2); i++; continue; }
  if (line.startsWith("## ")) {
    closeCase();
    const text = line.slice(3);
    if (text.startsWith("Nivel 1")) children.push(new Paragraph({ children: [new PageBreak()] }));
    children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] }));
    prevWasOl = false; i++; continue;
  }
  if (line.startsWith("### ")) {
    closeCase();
    children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(line.slice(4))] }));
    inCase = true; prevWasOl = false; i++; continue;
  }
  if (line === "---") { flush(); i++; continue; }
  if (line.trim().startsWith("|")) {
    flush();
    const rows = [];
    while (i < lines.length && lines[i].trim().startsWith("|")) {
      const cells = lines[i].trim().slice(1, -1).split("|").map((c) => c.trim());
      if (!cells.every((c) => /^-+$/.test(c))) rows.push(cells);
      i++;
    }
    const isLog = rows[0][0] === "Caso";
    if (isLog) for (let k = 0; k < 14; k++) rows.push(rows[0].map(() => ""));
    children.push(table(rows));
    children.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
    continue;
  }
  if (line.trim() === "") { flush(); prevWasOl = prevWasOl && pending === null; i++; continue; }
  const ol = line.match(/^(\s*)(\d+)\.\s+(.*)$/);
  const ul = line.match(/^(\s*)[-*]\s+(.*)$/);
  if (ol) {
    flush();
    const level = ol[1].length >= 3 ? 1 : 0;
    if (level === 0 && ol[2] === "1") newOl();
    pending = { kind: "ol", level, text: ol[3] };
    prevWasOl = true; i++; continue;
  }
  if (ul) {
    flush();
    const level = ul[1].length >= 2 ? 1 : 0;
    pending = { kind: "ul", level, text: ul[2] };
    i++; continue;
  }
  // Continuation of the previous paragraph or list item.
  if (pending && /^\s+/.test(raw)) { pending.text += " " + line.trim(); i++; continue; }
  if (pending && pending.kind === "p") { pending.text += " " + line.trim(); i++; continue; }
  flush();
  pending = { kind: "p", level: 0, text: line.trim() };
  i++;
}
closeCase();

const intro = [
  new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun(title)] }),
  new Paragraph({ spacing: { after: 240 }, children: [new TextRun({ text: "Gestión de seguros · Odoo 19 · versión del módulo 19.0.2.0.4", color: "595959" })] }),
  new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Contenido")] }),
  new TableOfContents("Contenido", { hyperlink: true, headingStyleRange: "1-2" }),
  new Paragraph({ children: [new TextRun({ text: "Si el índice aparece vacío, actualícelo en Word (clic derecho › Actualizar campo).", italics: true, color: "7F7F7F", size: 18 })] }),
  new Paragraph({ children: [new PageBreak()] }),
];

const doc = new Document({
  creator: "Zinapsia",
  title,
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", run: { font: FONT, size: 40, bold: true, color: ACCENT },
        paragraph: { spacing: { before: 0, after: 120 }, keepNext: true } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 30, bold: true, color: ACCENT },
        paragraph: { spacing: { before: 360, after: 160 }, keepNext: true, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, bold: true, color: "262626" },
        paragraph: { spacing: { before: 280, after: 100 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 567, hanging: 284 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 1134, hanging: 284 } } } },
      ] },
      ...numberingConfigs,
    ],
  },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
      children: [new TextRun({ text: "Casos de prueba manual — Gestión de seguros", color: "7F7F7F", size: 16 })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "Página ", size: 16, color: "7F7F7F" }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "7F7F7F" })] })] }) },
    children: [...intro, ...children],
  }],
});

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(out, buf); console.log("written", out); });
