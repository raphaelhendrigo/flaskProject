import fs from 'node:fs/promises';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';
const [input, output] = process.argv.slice(2);
const {edition,date,events} = JSON.parse(await fs.readFile(input,'utf8'));
const wb = Workbook.create();
const sheet = wb.worksheets.add('Conferência DOC');
const grid = sheet.getRange('A1:K1');
grid.merge();
grid.values = [[`Atos de pessoal  |  Diário Oficial da Cidade de São Paulo  •  ${date}`]];
grid.format.fill = '#193653'; grid.format.font.color = '#FFFFFF'; grid.format.font.bold = true;
grid.format.font.size = 15; grid.format.rowHeight = 32;
const intro = sheet.getRange('A2:K2'); intro.merge();
intro.values = [[`Edição ${edition}  •  Amarelo identifica o nome e os campos alterados na data. Consulte o ato e registre a conferência.`]];
intro.format.fill = '#DCEAF3'; intro.format.rowHeight = 24;
const cols = ['Nome','Classificação','Ato publicado','Período ou vigência','Órgão do cadastro','Evidência e efeito no cadastro','Documento SEI','Página','Célula de origem','Revisão humana','Fonte oficial'];
const header = sheet.getRange('A4:K4'); header.values=[cols];header.format.fill='#20546B';header.format.font.color='#FFFFFF';header.format.font.bold=true;header.format.rowHeight=25;
for (const [i,width] of [32,24,37,34,37,69,18,12,18,24,52].entries()){
  sheet.getRangeByIndexes(0,i,4+events.length,1).format.columnWidth=width;
}
for (const [i,e] of events.entries()){
  const r=sheet.getRangeByIndexes(i+4,0,1,11);
  r.values=[[e.nome,e.categoria,e.tipo,e.periodo,e.org,e.det,e.doc,e.pagina,'Prefeitura!E'+e.row,'Pendente',e.fonte || '']];
  r.format.wrapText=true;r.format.rowHeight=62;r.format.verticalAlignment='center';
  if(i%2===0) r.format.fill='#F0F5F8';
  if(e.categoria!=='Para verificar')sheet.getRangeByIndexes(i+4,0,1,1).format.fill='#FFFF00';
}
sheet.freezePanes.freezeRows(4);
await (await SpreadsheetFile.exportXlsx(wb)).save(output);
