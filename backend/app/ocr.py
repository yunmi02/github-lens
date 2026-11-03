import importlib.util
import threading
from pathlib import Path
from PIL import Image, ImageOps
from .config import settings
from .github import ServiceError

_engine = None
_lock = threading.Lock()


def ocr_status():
    return {'provider': settings.ocr_provider, 'installed': importlib.util.find_spec('paddleocr') is not None and importlib.util.find_spec('paddle') is not None, 'loaded': _engine is not None}


def read_image(path: str):
    global _engine
    if settings.ocr_provider != 'paddle' or not ocr_status()['installed']:
        raise ServiceError('PaddleOCR 尚未安装。请运行 scripts/setup.ps1 -WithOcr，或先手动填写项目链接。')
    with _lock:
        try:
            if _engine is None:
                from paddleocr import PaddleOCR
                options = dict(device='cpu', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
                if settings.ocr_lang == 'ch':
                    options.update(text_detection_model_name='PP-OCRv5_mobile_det', text_recognition_model_name='PP-OCRv5_mobile_rec')
                else:
                    options['lang'] = settings.ocr_lang
                _engine = PaddleOCR(**options)
            lines, regions = [], []
            with Image.open(path) as original:
                image = ImageOps.exif_transpose(original).convert('RGB')
                width, height = image.size
                step, tile_height = 1800, 2000
                import numpy as np
                for top in range(0, height, step):
                    crop = image.crop((0, top, width, min(top + tile_height, height)))
                    scale = min(1.0, 1800 / width)
                    if scale < 1:
                        crop = crop.resize((int(width * scale), int(crop.height * scale)))
                    for result in _engine.predict(np.asarray(crop)):
                        data = result.json
                        if callable(data):
                            data = data()
                        if isinstance(data, str):
                            import json
                            data = json.loads(data)
                        data = data.get('res', data)
                        for text, score, box in zip(data.get('rec_texts', []), data.get('rec_scores', []), data.get('rec_polys', [])):
                            if score < 0.3:
                                continue
                            points = [[round(float(p[0]) / scale), round(float(p[1]) / scale + top)] for p in box]
                            if any(text == r['text'] and abs(points[0][1] - r['box'][0][1]) < 25 for r in regions[-30:]):
                                continue
                            lines.append(text)
                            regions.append({'text': text, 'score': round(float(score), 3), 'box': points})
                    if top + tile_height >= height:
                        break
            return '\n'.join(lines), regions
        except ServiceError:
            raise
        except Exception as exc:
            # Model download errors must be visible, not replaced with fabricated OCR text.
            raise ServiceError(f'PaddleOCR 识别失败（{type(exc).__name__}），请检查模型下载及运行依赖；可手动填写链接。') from exc
