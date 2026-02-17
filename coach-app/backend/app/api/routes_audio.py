from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.chat import AudioTranscribeResponse
from app.services.openrouter_client import OpenRouterClient

router = APIRouter()


@router.post('/transcribe', response_model=AudioTranscribeResponse)
async def transcribe_audio(file: UploadFile = File(...)) -> AudioTranscribeResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail='音频文件不能为空')

    suffix = file.filename.split('.')[-1].lower() if '.' in file.filename else 'wav'
    if suffix not in {'wav', 'mp3', 'm4a', 'aac', 'ogg', 'flac'}:
        suffix = 'wav'

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail='音频文件内容为空')

    client = OpenRouterClient()
    text = client.transcribe_audio(raw, fmt=suffix)
    return AudioTranscribeResponse(text=text.strip())
