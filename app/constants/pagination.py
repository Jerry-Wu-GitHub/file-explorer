"""分页、排序相关的默认常量。"""

# 默认每页条目数量
DEFAULT_PAGE_SIZE: int = 50

# 每页条目数量上限
MAX_PAGE_SIZE: int = 200

# 默认页码
DEFAULT_PAGE: int = 1

# 默认排序：字段名,asc|desc
DEFAULT_SORT: str = "name,asc"

# 目录列表支持的排序字段（对应文件系统条目元数据字段）
SORTABLE_FIELDS: frozenset[str] = frozenset(
    {"name", "size", "modifiedAt", "createdAt", "accessedAt"}
)

# 目录列表支持的过滤类型
SUPPORTED_FILTER_TYPES: frozenset[str] = frozenset({"all", "file", "directory"})

# 搜索时最多遍历的条目数量，防止超大目录拖垮服务
SEARCH_MAX_ENTRIES: int = 100_000

# 搜索时最多遍历的目录层级
SEARCH_MAX_DEPTH: int = 64
