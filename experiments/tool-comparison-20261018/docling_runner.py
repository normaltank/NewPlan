"""Pinned local Docling arm with experiment-owned models and outputs."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ['HF_HOME']=str(ROOT/'.cache/huggingface')
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['OMP_NUM_THREADS']='4'
import importlib.metadata
import json
import time
import traceback
from datetime import datetime, timezone

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
from docling.document_converter import DocumentConverter, PdfFormatOption, ImageFormatOption
from docling.utils.model_downloader import download_models

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf8')

def main():
    dest=ROOT/'results/docling'
    dest.mkdir(parents=True,exist_ok=True)
    print('Downloading only layout, table and Chinese OCR models into this experiment.',flush=True)
    started=time.monotonic()
    download_models(output_dir=ROOT/'models',with_layout=True,with_tableformer=True,
        with_code_formula=False,with_picture_classifier=False,with_rapidocr=True,
        rapidocr_models=['onnxruntime:ch'],progress=True)
    save(dest/'setup.json',{'model_download_seconds':time.monotonic()-started,
        'versions':{p:importlib.metadata.version(p) for p in ['docling','docling-core','docling-ibm-models','rapidocr','onnxruntime','torch','transformers']},
        'model_directory':str(ROOT/'models')})
    options=PdfPipelineOptions(artifacts_path=ROOT/'models')
    options.do_ocr=True
    options.do_table_structure=True
    options.ocr_options=RapidOcrOptions(lang=['ch'],backend='onnxruntime',force_full_page_ocr=False)
    options.accelerator_options=AcceleratorOptions(num_threads=4,device=AcceleratorDevice.CPU)
    options.document_timeout=240
    image_options=options.model_copy(deep=True)
    image_options.ocr_options.force_full_page_ocr=True
    save(dest/'config.json',{'pdf':options.model_dump(mode='json'),'image':image_options.model_dump(mode='json')})
    converter=DocumentConverter(format_options={
        InputFormat.PDF:PdfFormatOption(pipeline_options=options),
        InputFormat.IMAGE:ImageFormatOption(pipeline_options=image_options)})
    documents=json.loads((ROOT/'documents.json').read_text(encoding='utf8'))
    for item in documents:
        output=dest/(item['id']+'.json')
        if output.exists():continue
        start=time.monotonic()
        record={'id':item['id'],'source':item['source'],'timestamp':datetime.now(timezone.utc).isoformat()}
        try:
            result=converter.convert(item['source'],raises_on_error=False)
            record.update(status=str(result.status),errors=[str(e) for e in result.errors])
            doc=result.document
            doc.save_as_json(dest/(item['id']+'-document.json'))
            doc.save_as_markdown(dest/(item['id']+'.md'))
            record.update(tables=len(doc.tables),texts=len(doc.texts),pages=len(doc.pages),
                confidence=result.confidence.model_dump(mode='json') if result.confidence else None)
            record['table_rows']=[table.export_to_dataframe(doc=doc).fillna('').astype(str).values.tolist() for table in doc.tables]
        except Exception as exc:
            record.update(status='error',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
        record['elapsed_seconds']=round(time.monotonic()-start,3)
        save(output,record)
        print(json.dumps(record,ensure_ascii=False,default=str)[:450],flush=True)

if __name__=='__main__':main()
