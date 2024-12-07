import asyncio
from tempfile import NamedTemporaryFile
from fastapi import BackgroundTasks, FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pytubefix import YouTube, Playlist
from pytubefix.exceptions import VideoUnavailable,AgeRestrictedError,VideoPrivate,RegexMatchError
import os
from pathlib import Path


def download_single_video(yt, output_path="sounds"):
    """Tek bir videoyu indirmek için yardımcı fonksiyon"""
    try:
        stream = yt.streams.get_audio_only()
        audio_file_name = f"{yt.title}.wav"
        stream.download(filename=audio_file_name, output_path=output_path)
        print(f"'{yt.title}' başarıyla indirildi")
        return {"id": yt.video_id, "title": yt.title,"success" : True}
    except (AgeRestrictedError, VideoPrivate, VideoUnavailable, RegexMatchError) as e:
        handle_error(e, yt.watch_url if hasattr(yt, 'watch_url') else "")
        return {"id": yt.video_id, "title": yt.title,"success": False}

def handle_error(error, link=""):
    """Hata mesajlarını yönetmek için yardımcı fonksiyon"""
    error_messages = {
        AgeRestrictedError: "Video yaş kısıtlamalıdır.",
        VideoPrivate: "Video gizlidir",
        VideoUnavailable: f"{link} : {str(error)}",
        RegexMatchError: "Yanlış formatta link girdiniz. Lütfen tekrar deneyiniz."
    }
    print(error_messages.get(type(error), f"Beklenmeyen hata: {str(error)}"))

def download(link, output_path="sounds"):
    """Ana indirme fonksiyonu"""
    music_list = []
    unavailable_music_list = []
    try:
        if "list" in link:
            playlist = Playlist(link)
            for video_link in playlist:
                yt = YouTube(
                    video_link,
                    use_oauth=False,
                    allow_oauth_cache=True
                )
                result = download_single_video(yt, output_path)
                if result["success"] == True:
                    music_list.append(result)
                else:
                    unavailable_music_list.append(result)
        else:
            yt = YouTube(
                link,
                use_oauth=False,
                allow_oauth_cache=True
            )
            result = download_single_video(yt, output_path)
            if result["success"] == True:
                music_list.append(result)
            else:
                unavailable_music_list.append(result)
                
    except Exception as e:
        print(f"Beklenmeyen bir hata oluştu: {str(e)}")
    
    return music_list,unavailable_music_list

# Geçici dosyalar için klasör oluştur
TEMP_DIR = Path("temp_downloads")
TEMP_DIR.mkdir(exist_ok=True)
app = FastAPI()




# Static dosyaları ve template'leri ayarla
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "music_list": []})

@app.post("/download")
async def get_music_list(request: Request, link: str = Form(...)):
    try:
        # Verilen download fonksiyonunu kullan
        music_list,unavailable_music_list = download(link)
        print(music_list,"--------",unavailable_music_list)
        return templates.TemplateResponse("index.html", {
            "request": request,
            "music_list": music_list,
            "unavailable_music_list" : unavailable_music_list,
            "success": True
        })
    except Exception as e:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": str(e),
            "music_list": [],
            "unavailable_music_list" : unavailable_music_list,
            "success": False
        })


async def cleanup_file(path: Path):
    try:
        await asyncio.sleep(1)  # Dosyanın tamamen gönderilmesi için kısa bir bekleme
        if path.exists():
            path.unlink()
    except Exception as e:
        print(f"Cleanup error: {e}")

@app.get("/download/{video_id}")
async def download_file(video_id: str, background_tasks: BackgroundTasks):
    try:
        # YouTube nesnesini oluştur
        yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
        stream = yt.streams.get_audio_only()
        
        # Güvenli dosya adı oluştur
        safe_filename = "".join(x for x in yt.title if x.isalnum() or x in [' ', '-', '_']).rstrip()
        temp_path = TEMP_DIR / f"{safe_filename}.mp3"
        
        # Dosyayı indir
        stream.download(output_path=TEMP_DIR, filename=temp_path.name)
        
        # Cleanup'ı background task olarak ekle
        background_tasks.add_task(cleanup_file, temp_path)
        
        return FileResponse(
            path=temp_path,
            filename=f"{safe_filename}.mp3",
            media_type='audio/mp3'
        )
        
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )