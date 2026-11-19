"""Preserva a estrutura Excel original ao incorporar a folha de conferência."""
import json,re,sys,copy
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as ET
from datetime import datetime

base, resumo, payload, destino = sys.argv[1:]
b=ZipFile(base); s=ZipFile(resumo)
ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
def tag(k): return '{'+ns+'}'+k
def xml(z,p): return ET.fromstring(z.read(p))
def pack(x): return ET.tostring(x,encoding='UTF-8',xml_declaration=True,standalone=True)
def add(root, child):
    root.append(child);root.set('count',str(len(root)));return len(root)-1
def inline(c,value):
    for ch in list(c): c.remove(ch)
    c.set('t','inlineStr'); ET.SubElement(ET.SubElement(c,tag('is')),tag('t')).text=value
styles=xml(b,'xl/styles.xml'); src=xml(s,'xl/styles.xml')
offset={}
for k in ('fonts','fills','borders'):
    dst=styles.find(tag(k));offset[k]=len(dst)
    for el in src.find(tag(k)): add(dst,copy.deepcopy(el))
xfs=styles.find(tag('cellXfs')); start=len(xfs)
for xf in src.find(tag('cellXfs')):
    xf=copy.deepcopy(xf)
    for k,f in [('fontId','fonts'),('fillId','fills'),('borderId','borders')]:xf.set(k,str(offset[f]+int(xf.get(k,0))))
    xf.set('xfId','0');add(xfs,xf)
sheet=xml(s,'xl/worksheets/sheet1.xml')
ss=xml(s,'xl/sharedStrings.xml') if 'xl/sharedStrings.xml' in s.namelist() else []
for cell in sheet.iter(tag('c')):
    cell.set('s',str(start+int(cell.get('s',0))))
    if cell.get('t')=='s':
        val=ss[int(cell.findtext(tag('v')))];inline(cell,''.join(t.text or '' for t in val.iter(tag('t'))))
for v in sheet.iter(tag('sheetView')):v.set('tabSelected','1')
yellow=ET.fromstring(f'<fill xmlns="{ns}"><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/><bgColor indexed="64"/></patternFill></fill>')
fillid=add(styles.find(tag('fills')),yellow)
pref=xml(b,'xl/worksheets/sheet1.xml'); original_strings=xml(b,'xl/sharedStrings.xml'); fills={}
def mark(address,value=None,date=False,highlight=True):
    cell=pref.find(f'.//{tag("c")}[@r="{address}"]')
    if cell is None:
        row=pref.find(f'.//{tag("row")}[@r="{re.search(r"[0-9]+",address)[0]}"]')
        col=lambda a: sum((ord(c)-64)*26**j for j,c in enumerate(re.match(r'[A-Z]+',a)[0][::-1]))
        cell=ET.Element(tag('c'),r=address)
        idx=next((i for i,c in enumerate(row) if col(c.get('r'))>col(address)),len(row));row.insert(idx,cell)
    key=(cell.get('s','0'),date,highlight)
    if key not in fills:
        xf=copy.deepcopy(xfs[int(key[0])])
        if highlight: xf.set('fillId',str(fillid));xf.set('applyFill','1')
        if date:xf.set('numFmtId','14');xf.set('applyNumberFormat','1')
        fills[key]=add(xfs,xf)
    cell.set('s',str(fills[key]))
    if value is None:return
    if value=='':
        for ch in list(cell):cell.remove(ch)
        cell.attrib.pop('t',None);return
    if date:
        for ch in list(cell):cell.remove(ch)
        cell.set('t','n');ET.SubElement(cell,tag('v')).text=str((datetime.strptime(value,'%d/%m/%Y')-datetime(1899,12,30)).days)
    else:inline(cell,value)
data=json.loads(Path(payload).read_text())
def write_delta(addr, value, highlight):
    if not re.fullmatch(r'[DEFGHIM][2-9][0-9]*|[DEFGHIM]1[0-9]+',addr):
        raise ValueError("Endereço de alteração inválido")
    is_date = addr.startswith('I') and isinstance(value,str) and bool(re.fullmatch(r'\d{2}/\d{2}/\d{4}',value))
    mark(addr,value,date=is_date,highlight=highlight)

for addr,value in data.get('previous_values',{}).items():
    write_delta(addr,value,False)
for ev in data['events']:
    changes=ev['alteracoes']
    if not changes or ev.get('categoria')=='Para verificar':
        raise ValueError("O relatório aceita apenas alterações efetivas")
    for col,value in changes.items():
        if col not in ('D','E','F','G','H','I','M'):raise ValueError(col)
        write_delta(f"{col}{ev['row']}",value,True)
    if 'E' not in changes:
        mark(f"E{ev['row']}")
for v in pref.iter(tag('sheetView')):v.attrib.pop('tabSelected',None)
wb=xml(b,'xl/workbook.xml');rels=xml(b,'xl/_rels/workbook.xml.rels');ct=xml(b,'[Content_Types].xml')
for r in list(rels):
 if r.get('Type','').endswith('/vbaProject'):rels.remove(r)
for r in list(ct):
 if r.get('PartName')=='/xl/vbaProject.bin':ct.remove(r)
 if r.get('PartName')=='/xl/workbook.xml':r.set('ContentType','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
sheets=wb.find(tag('sheets'));sid=max(int(v.get('sheetId')) for v in sheets)+1
rid='rIdConferenciaDOC';file='worksheets/sheetConferencia.xml'
ET.SubElement(sheets,tag('sheet'),name='Conferência DOC',sheetId=str(sid),attrib={'{'+rel+'}id':rid})
ET.SubElement(rels,rels[0].tag,Id=rid,Type=rel+'/worksheet',Target=file)
ET.SubElement(ct,ct[-1].tag,PartName='/xl/'+file,ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
for v in wb.iter(tag('workbookView')):v.set('activeTab',str(len(sheets)-1))
edited={p:pack(x) for p,x in [('xl/workbook.xml',wb),('xl/_rels/workbook.xml.rels',rels),('xl/styles.xml',styles),('xl/worksheets/sheet1.xml',pref),('[Content_Types].xml',ct)]}
with ZipFile(destino,'w',ZIP_DEFLATED) as out:
 for p in b.namelist():
    if p!='xl/vbaProject.bin':out.writestr(p,edited[p] if p in edited else b.read(p))
 out.writestr('xl/'+file,pack(sheet))
