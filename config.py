"""全局配置"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === 路径 ===
ROOT = Path(__file__).parent
DATA_INPUT = ROOT / 'data' / 'input'
DATA_OUTPUT = ROOT / 'data' / 'output'
TEMPLATE_DIR = ROOT / 'templates'

# === LLM ===
LLM_API_KEY = os.getenv('LLM_API_KEY')
LLM_BASE_URL = os.getenv('LLM_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
LLM_MODEL = os.getenv('LLM_MODEL', 'qwen-plus')

# === 并发与限流 ===
LLM_CONCURRENCY_PROFILE = 15
LLM_CONCURRENCY_POST = 8
LLM_CONCURRENCY_REPLY = 8
LLM_CONCURRENCY_SCORE = 8
LLM_TIMEOUT = 120
LLM_MAX_RETRIES = 2

# === 数据筛选 ===
FILTER_MIN_ACTIVE_DIMS = 4
FILTER_MIN_TOTAL_ACTIONS = 30
FILTER_MIN_UNIQUE_TITLES = 15
FILTER_MIN_PROFILE_LEN = 100

# === Persona 限制 ===
PROFILE_LLM_INPUT_MAX = 3000
PROFILE_RAW_KEEP_LEN = 1200
PERSONA_VOICE_SAMPLES = 8

# === Demo 输出 ===
DEMO_PERSONA_COUNT = 7

# 确保输出目录存在
DATA_OUTPUT.mkdir(parents=True, exist_ok=True)
