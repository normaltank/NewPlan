"""Developer helper; writes only distribution templates and small test fixtures."""
from pathlib import Path
from openpyxl import Workbook
from reporting import sheet
ROOT = Path(__file__).resolve().parent
(ROOT/'templates').mkdir(exist_ok=True)
book=Workbook();book.remove(book.active)
sheet(book,'输入数据',['学校','学院','师资url','教师url'],[])
book.save(ROOT/'templates'/'输入模板.xlsx')
(ROOT/'templates'/'输入模板.tsv').write_text('学校\t学院\t师资url\t教师url\n',encoding='utf-8-sig')
fixture=ROOT/'tests'/'fixtures'/'plain.xls'
if not fixture.exists():
    import xlwt
    fixture.parent.mkdir(parents=True,exist_ok=True)
    book=xlwt.Workbook();ws=book.add_sheet('名单')
    rows=[['学校','学院','师资url','教师url'],['测试大学','测试学院','https://example.edu.cn/faculty/list.htm','https://example.edu.cn/a'],['测试大学','测试学院','https://example.edu.cn/faculty/list.htm','https://example.edu.cn/b']]
    for r,row in enumerate(rows):
        for c,value in enumerate(row):
            ws.write(r,c,value)
    book.save(str(fixture))
