"""Three current image originals only; local OCR/Docling with network forbidden."""
import os
from pathlib import Path
import sys

MODEL_ROOT = Path(r"D:\Agent Workspace\Intern\MyPlan\OpenSource\experiments\tool-comparison-20261018")
os.environ.update(HF_HOME=str(MODEL_ROOT / ".cache/huggingface"), HF_HUB_OFFLINE="1",
                  TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", OMP_NUM_THREADS="4")
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import socket
import time

def forbid_network(*args, **kwargs):
    raise OSError("Network forbidden in current-image offline comparison")
socket.socket.connect = forbid_network
socket.create_connection = forbid_network

HERE = Path(__file__).resolve().parent
OUT = Path(r"D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C\outputs\diverse-pages-20261027")
IMAGES = [("n11_chnu_zhanghongyan", "image-original-2.jpg"),
          ("n11_chnu_zhanghongyan", "image-original-3.jpg"),
          ("n12_chnu_baoxiangzhi", "image-original-1.png")]

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("method", choices=["rapidocr", "docling"])
    args = parser.parse_args()
    converter = None
    for sid, file in IMAGES:
        folder = OUT / args.method / sid / Path(file).stem
        folder.mkdir(parents=True, exist_ok=True)
        if (folder / "result.json").exists() or (folder / "attempt.json").exists():
            continue
        source = OUT / "cohort" / sid / file
        row = {"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "started_at": datetime.now(timezone.utc).isoformat(), "network": "forbidden",
               "method": args.method, "status": "attempt_unknown"}
        save(folder / "attempt.json", row)
        started = time.monotonic()
        try:
            if args.method == "rapidocr":
                sys.path.insert(0, str(HERE.parents[1] / "Mission C"))
                from mission_c.ocr_media import read_image
                ocr = read_image(source.read_bytes(), folder, source_url="saved_current_original")
                row.update(status=ocr["status"], low_confidence_lines=ocr["low_confidence_lines"],
                           versions={p: importlib.metadata.version(p) for p in ["rapidocr-onnxruntime", "onnxruntime"]})
            else:
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
                from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
                from docling.document_converter import DocumentConverter, ImageFormatOption
                if converter is None:
                    options = PdfPipelineOptions(artifacts_path=MODEL_ROOT / "models")
                    options.do_ocr = True
                    options.do_table_structure = True
                    options.ocr_options = RapidOcrOptions(lang=["ch"], backend="onnxruntime", force_full_page_ocr=True)
                    options.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU)
                    options.document_timeout = 120
                    save(OUT / "docling/config.json", options.model_dump(mode="json"))
                    converter = DocumentConverter(format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=options)})
                result = converter.convert(source, raises_on_error=False)
                doc = result.document
                doc.save_as_json(folder / "document.json")
                doc.save_as_markdown(folder / "document.md")
                row.update(status=str(result.status), errors=[str(x) for x in result.errors],
                           tables=len(doc.tables), texts=len(doc.texts), pages=len(doc.pages),
                           table_rows=[table.export_to_dataframe(doc=doc).fillna("").astype(str).values.tolist() for table in doc.tables],
                           versions={p: importlib.metadata.version(p) for p in ["docling", "docling-core", "rapidocr", "onnxruntime"]})
        except Exception as error:
            row.update(status="failed", error_type=type(error).__name__, error=str(error)[:1000])
        row.update(finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=round(time.monotonic()-started, 3))
        save(folder / "result.json", row)
        print(json.dumps({"id": sid, "image": file, "method": args.method, "status": row["status"],
                          "tables": row.get("tables"), "error": row.get("error")}, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
