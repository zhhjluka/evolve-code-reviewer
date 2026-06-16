"""共享 fixtures"""
import pytest
from pathlib import Path
import tempfile
import sys

# 确保 src 在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def tmp_py_file():
    """创建临时 Python 文件，测试结束后自动删除"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        filepath = f.name
    yield filepath
    Path(filepath).unlink(missing_ok=True)


@pytest.fixture
def write_code(tmp_py_file):
    """向临时文件写入代码的辅助函数"""

    def _write(source_code: str) -> str:
        Path(tmp_py_file).write_text(source_code)
        return tmp_py_file

    return _write


@pytest.fixture
def gate_config():
    """标准门控配置"""
    from cra.gate import GateConfig
    return GateConfig(
        cyclomatic_threshold=15,
        cognitive_threshold=20,
        max_function_lines=80,
        max_nesting_depth=4,
        max_parameters=5,
    )
