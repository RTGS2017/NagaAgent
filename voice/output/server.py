import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # 加入项目根目录到模块查找路径
from nagaagent_core.api import Flask, request, send_file, jsonify
from voice.output.tts_handler import generate_speech
from voice.output.utils import require_api_key, AUDIO_FORMAT_MIME_TYPES
from system.config import config

app = Flask(__name__)

@app.route('/v1/audio/speech', methods=['POST'])
@require_api_key
def text_to_speech():
    try:
        data = request.json
        if not data or 'input' not in data:
            return jsonify({"error": "Missing 'input' in request body"}), 400

        text = data.get('input')
        voice = data.get('voice', config.tts.default_voice)
        response_format = data.get('response_format', 'mp3')
        speed = float(data.get('speed', config.tts.default_speed))
        
        mime_type = AUDIO_FORMAT_MIME_TYPES.get(response_format, "audio/mpeg")
        output_file_path = generate_speech(text, voice, response_format, speed)
        return send_file(output_file_path, mimetype=mime_type, as_attachment=True, download_name="speech.mp3")
    except Exception as e:
        with open('voice_server_error.log', 'a') as f:
            f.write(f"Error at {__name__}: {str(e)}\n")
            import traceback
            traceback.print_exc(file=f)
        return jsonify({"error": "An internal server error occurred."}), 500

if __name__ == '__main__':
    from gevent.pywsgi import WSGIServer
    http_server = WSGIServer(('0.0.0.0', config.tts.port), app)
    http_server.serve_forever()
