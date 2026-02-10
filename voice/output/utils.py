import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # 加入项目根目录到模块查找路径
# utils.py
from flask import request, jsonify
from functools import wraps
from system.config import config  # 使用统一配置系统
DEFAULT_LANGUAGE = config.tts.default_language # 统一配置


def getenv_bool(key: str, default: bool = False) -> bool:
    """从环境变量获取布尔值"""
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')

API_KEY = config.tts.api_key
REQUIRE_API_KEY = config.tts.require_api_key
DETAILED_ERROR_LOGGING = getenv_bool('DETAILED_ERROR_LOGGING', True)

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not REQUIRE_API_KEY:
            return f(*args, **kwargs)
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid API key"}), 401
        token = auth_header.split('Bearer ')[1]
        if token != API_KEY:
            return jsonify({"error": "Invalid API key"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Mapping of audio format to MIME type
AUDIO_FORMAT_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/L16"
}
