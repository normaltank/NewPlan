"""CPU OCR with immutable image bytes, boxes and confidence for human review."""
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

_engine = None


def read_image(data: bytes, folder: Path, source_url: str = '') -> dict:
    global _engine
    folder.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        if width * height > 40_000_000:
            raise ValueError('Image exceeds 40 megapixels')
        fmt = image.format or ''
        ext = {'JPEG': 'jpg', 'PNG': 'png', 'GIF': 'gif', 'WEBP': 'webp', 'BMP': 'bmp', 'TIFF': 'tiff'}.get(fmt)
        if not ext:
            raise ValueError('Unsupported raster image')
        image.verify()
    path = folder / ('source.' + ext)
    path.write_bytes(data)
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
    result, elapsed = _engine(data)
    lines = [{'box': [[float(x), float(y)] for x, y in box], 'text': str(text),
              'confidence': float(score)} for box, text, score in (result or [])]
    text = '\n'.join(line['text'] for line in lines)
    record = {'source_url': source_url, 'source_file': path.name,
              'sha256': hashlib.sha256(data).hexdigest(), 'width': width, 'height': height,
              'engine': 'rapidocr-onnxruntime', 'text': text, 'lines': lines,
              'low_confidence_lines': sum(line['confidence'] < .85 for line in lines),
              'status': 'ocr_candidate' if text else 'no_text_detected',
              'retrieved_at': datetime.now(timezone.utc).isoformat(), 'review_required': True}
    (folder / 'ocr.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'ocr.txt').write_text(text, encoding='utf-8')
    return record


def read_pdf(data: bytes, folder: Path, max_pages=50) -> dict:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) > max_pages:
        raise ValueError('PDF page limit exceeded')
    pages = []
    rendered = None
    try:
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ''
            import pypdfium2 as pdfium
            if rendered is None:
                rendered = pdfium.PdfDocument(data)
            pdf_page = rendered[index]
            width,height=pdf_page.get_size()
            image_coverage=0
            for obj in pdf_page.get_objects():
                if obj.type==3:
                    left,bottom,right,top=obj.get_pos()
                    area=max(0,min(width,right)-max(0,left))*max(0,min(height,top)-max(0,bottom))
                    image_coverage=max(image_coverage,area/(width*height))
            hybrid=len(text.strip())>=40 and image_coverage>.35
            if len(text.strip()) >= 40 and not hybrid:
                pages.append({'page': index + 1, 'text': text, 'method': 'text_layer'})
                pdf_page.close()
            else:
                bitmap = pdf_page.render(scale=2)
                image = bitmap.to_pil()
                buf = io.BytesIO()
                image.save(buf, format='PNG')
                image.close()
                bitmap.close()
                pdf_page.close()
                result = read_image(buf.getvalue(), folder / f'page-{index+1:03d}')
                if hybrid:
                    result['native_text']=text
                    result['ocr_text']=result['text']
                    result['text']=text+'\n\n[混合页面 OCR 全文补充]\n'+result['text']
                pages.append({'page': index + 1, 'method': 'hybrid_ocr' if hybrid else 'local_ocr',
                              'largest_image_coverage':round(image_coverage,4), **result})
    finally:
        if rendered is not None:
            rendered.close()
    result = {'pages': pages, 'ocr_pages': sum(p['method'] in ('local_ocr','hybrid_ocr') for p in pages),
              'text': '\n\n'.join(f"[page {p['page']}]\n{p['text']}" for p in pages)}
    (folder / 'pdf-text.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
