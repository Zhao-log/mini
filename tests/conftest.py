"""
测试入口: 确保 src 包能被正确 import.
"""

import os
import sys

# 把项目根目录加进 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
