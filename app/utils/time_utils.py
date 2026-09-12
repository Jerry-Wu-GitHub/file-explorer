"""时间转换工具。

本模块提供将 :class:`datetime.datetime` 转换为 Unix 时间戳的函数，
统一处理带时区与不带时区两种输入。
"""

from datetime import datetime, timezone


def datetime_to_timestamp(value: datetime) -> float:
    """将 :class:`datetime` 转换为 Unix 时间戳（秒）。

    naive datetime（无时区信息）视为 UTC，避免依赖运行环境的本地
    时区导致跨平台结果不一致。

    Args:
        value: 待转换的时间对象。

    Returns:
        对应的 Unix 时间戳，单位秒。
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


__all__ = ["datetime_to_timestamp"]
