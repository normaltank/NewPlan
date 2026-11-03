"""Server-only download adapter; reconciliation remains in audit/reporting."""
import zipfile
from reporting import college_summary_rows, new_book, sheet


def export_download(out, results):
    # Keep college rows before file rejections; shared reporting keeps each file separate.
    normal = [r for r in results if r.get('record_type') != 'input_file']
    rows = college_summary_rows(sorted(results, key=lambda r: r.get('record_type') == 'input_file'))
    book = new_book()
    sheet(book, '核验汇总', ['学校', '学院', '核验结果', '特殊情况说明'], rows)
    summary = out/'server-summary.xlsx'
    book.save(summary)
    errors = {(r[0], r[1]) for r in rows if r[2] == '错误'}
    with zipfile.ZipFile(out/'results.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(summary, '核验汇总.xlsx')
        archive.writestr('更新链接/', '')
        for result in normal:
            if result['complete'] and (result['school'], result['college']) in errors:
                name = result['corrected_filename']
                archive.write(out/'corrected'/name, '更新链接/'+name)
