const {
  Document, Packer, Paragraph, TextRun, AlignmentType,
} = require('docx');
const fs = require('fs');

function titlePara(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 360 },
    children: [new TextRun({ text, bold: true, size: 32 })],
  });
}

function preamblePara(text) {
  return new Paragraph({
    spacing: { after: 320 },
    children: [new TextRun({ text, size: 22 })],
  });
}

function articleHeading(text) {
  return new Paragraph({
    spacing: { before: 280, after: 120 },
    children: [new TextRun({ text, bold: true, size: 22 })],
  });
}

function bodyLine(text, indent = 240) {
  return new Paragraph({
    spacing: { after: 80 },
    indent: { left: indent },
    children: [new TextRun({ text, size: 22 })],
  });
}

function plainLine(text) {
  return new Paragraph({
    spacing: { after: 80 },
    children: [new TextRun({ text, size: 22 })],
  });
}

function sectionNote(text) {
  return new Paragraph({
    spacing: { before: 200, after: 200 },
    children: [new TextRun({ text, size: 20, italics: true, color: '555555' })],
  });
}

function buildArticles(articles) {
  const paras = [];
  articles.forEach((a) => {
    paras.push(articleHeading(a.heading));
    a.lines.forEach((line) => paras.push(bodyLine(line)));
  });
  return paras;
}

function signatureBlock(otsuTitle) {
  return [
    plainLine(''),
    plainLine('本契約の成立を証するため、本書2通を作成し、甲乙記名押印の上、各自1通を保有する。甲及び乙の合意により電磁的記録に対する電子署名により本契約締結の証とする場合は、本書の電磁的記録を作成し、それぞれ電子署名の上、各自その電磁的記録を保有する。'),
    plainLine(''),
    plainLine('20●●年●●月●●日'),
    plainLine(''),
    plainLine('（甲）'),
    bodyLine('住　所：東京都●●区●●'),
    bodyLine('会社名：AIM株式会社'),
    bodyLine('代表者：代表取締役　●●　　　　　　　　　　印'),
    plainLine(''),
    plainLine(`（乙）${otsuTitle ? '　' + otsuTitle : ''}`),
    bodyLine('住　所：●●'),
    bodyLine('氏名又は名称：●●'),
    bodyLine('（法人の場合）代表者：●●　　　　　　　　　印'),
  ];
}

async function writeDoc(filename, children) {
  const doc = new Document({
    sections: [
      { properties: { page: { size: { width: 11906, height: 16838 } } }, children },
    ],
  });
  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync(filename, buf);
  console.log('wrote', filename);
}

module.exports = {
  titlePara, preamblePara, articleHeading, bodyLine, plainLine, sectionNote,
  buildArticles, signatureBlock, writeDoc,
};
