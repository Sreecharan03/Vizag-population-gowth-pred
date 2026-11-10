"""Use the installed Word renderer to paginate and export the report."""
from pathlib import Path
import win32com.client
import fitz

root=Path(__file__).resolve().parents[1]/'results'/'project_report'
source=root/'Vizag_GeoAI_Project_Report_Reviewed.docx'
pdf=root/'Vizag_GeoAI_Project_Report_Reviewed.pdf'
if pdf.exists():raise FileExistsError(pdf)
word=win32com.client.DispatchEx('Word.Application')
word.Visible=False
word.DisplayAlerts=0
try:
    document=word.Documents.Open(str(source),ReadOnly=False,AddToRecentFiles=False)
    document.Fields.Update()
    for toc in document.TablesOfContents:toc.Update()
    document.Repaginate()
    document.Save()
    document.ExportAsFixedFormat(str(pdf),17)
    print('Word pages:',document.ComputeStatistics(2))
    document.Close(False)
finally:
    word.Quit()
with fitz.open(pdf) as pages:
    for i,page in enumerate(pages):
        text=page.get_text()
        print(f'Page {i+1}: {len(text)} chars; {text[:65]!r}')
        if 'Figure 7.1.' in text:
            page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(root/f'architecture_page_{i+1}.png')
    print('PDF page count:',len(pages))
