
from datetime import datetime


def parse_date_time(date_time_string: str) -> datetime:
    return datetime.fromisoformat(date_time_string.replace("Z", "+00:00"))


def to_ns_time_value(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)