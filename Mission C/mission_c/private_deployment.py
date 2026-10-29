"""Server-owned portable private deployment metadata; credentials load only on start."""
import json
from pathlib import Path


class PrivateDeployment:
    def __init__(self, config):
        self.config = Path(config).resolve()
        try:
            value = json.loads(self.config.read_text(encoding='utf-8-sig'))
            if set(value) != {'profile','key_file'} or value['profile'] != 'deepseek-private-v1':
                raise ValueError()
            relative = Path(value['key_file'])
            self.key_path = (self.config.parent/relative).resolve()
            if relative.is_absolute() or not self.key_path.is_relative_to(self.config.parent) or self.key_path == self.config:
                raise ValueError()
        except (OSError, ValueError, TypeError):
            raise ValueError('私人部署配置无效；请联系分发者') from None

    def load_key(self):
        try:
            key = self.key_path.read_text(encoding='utf-8').strip()
            if not 8 <= len(key) <= 512 or not key.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in key):
                raise ValueError()
            return key
        except (OSError, ValueError):
            raise ValueError('私人部署凭据缺失或无效；请联系分发者') from None
