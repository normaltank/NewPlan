"""Finite per-run resource limits; opt in without changing desktop defaults."""
from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path


class LimitExceeded(ValueError):
    def __init__(self, kind, limit, observed, message):
        super().__init__(message)
        self.event = {'kind': kind, 'limit': limit, 'observed': observed, 'reason': message}


@dataclass(frozen=True)
class RunLimits:
    files_per_batch: int = 200
    data_rows_per_batch: int = 250000
    input_file_bytes: int = 64 * 1024 * 1024
    xlsx_expanded_bytes: int = 256 * 1024 * 1024
    sheet_cells: int = 4000000
    merged_cells: int = 500000
    source_pages_per_college: int = 1000
    api_calls_per_batch: int = 20000
    model_input_chars: int = 1000000
    model_output_tokens: int = 8192
    client_pages: int = 1000
    client_observation_seconds: int = 600

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) is not int or value <= 0:
                raise ValueError(f'{name} 必须是有限正整数')

    def as_dict(self):
        return asdict(self)

    @classmethod
    def load(cls, value):
        """Accept a limits object, a JSON path, or a partial mapping of overrides."""
        if isinstance(value, cls):
            return value
        if isinstance(value, (str, Path)):
            value = json.loads(Path(value).read_text('utf-8-sig'))
        if not isinstance(value, dict):
            raise ValueError('运行上限配置须为JSON对象')
        unknown = set(value) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError('未知上限配置：' + ', '.join(sorted(unknown)))
        return cls(**value)


DESKTOP_LIMITS = RunLimits(data_rows_per_batch=50000, input_file_bytes=10*1024*1024,
    xlsx_expanded_bytes=100*1024*1024, sheet_cells=2000000, merged_cells=50000,
    source_pages_per_college=200, api_calls_per_batch=200, model_input_chars=220000,
    model_output_tokens=5500, client_pages=30, client_observation_seconds=45)
