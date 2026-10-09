"""FastAPI 应用实现。

应用工厂位于 ``backend.app.main``。这里刻意不导入全局 ``app``，以免 Alembic
仅加载模型元数据时触发建库和种子副作用。
"""
