"""
Python SDK JSON provider callback registration example.
Python SDK JSON provider callback 注册示例。
"""

from __future__ import annotations

def main() -> None:
    """Run the packaged real SQLite host demonstration; return nothing.
    运行包内真实 SQLite 宿主演示；无返回值。
    """
    from luaskills.examples.sqlite_demo import main as sqlite_main
    sqlite_main()


if __name__ == "__main__":
    main()
