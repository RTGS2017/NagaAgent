import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # 加入项目根目录到模块查找路径
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from voice.output.tts_handler import _generate_audio
from voice.output.utils import require_api_key, AUDIO_FORMAT_MIME_TYPES
from system.config import config

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

@app.post('/v1/audio/speech')
@require_api_key
async def text_to_speech(request: Request):
    try:
        data = await request.json()
        if not data or 'input' not in data:
            return JSONResponse({"error": "Missing 'input' in request body"}, status_code=400)

        text = data.get('input')
        voice = data.get('voice', config.tts.default_voice)
        response_format = data.get('response_format', 'mp3')
        speed = float(data.get('speed', config.tts.default_speed))

        mime_type = AUDIO_FORMAT_MIME_TYPES.get(response_format, "audio/mpeg")
        output_file_path = await _generate_audio(text, voice, response_format, speed)
        return FileResponse(output_file_path, media_type=mime_type, filename="speech.mp3")
    except Exception as e:
        with open('voice_server_error.log', 'a') as f:
            f.write(f"Error at {__name__}: {str(e)}\n")
            import traceback
            traceback.print_exc(file=f)
        return JSONResponse({"error": "An internal server error occurred."}, status_code=500)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=config.tts.port)
