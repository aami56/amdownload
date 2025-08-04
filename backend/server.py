from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime
import asyncio
import json
import yt_dlp
import aiofiles
import threading
from concurrent.futures import ThreadPoolExecutor
import subprocess
import time
import re
import shutil

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create downloads directory
DOWNLOADS_DIR = ROOT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Create the main app
app = FastAPI()

# Mount static files for serving downloads
app.mount("/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Global variables for tracking downloads
active_downloads = {}
download_queue = []
download_stats = {
    "total_downloads": 0,
    "active_downloads": 0,
    "done_downloads": 0,
    "total_size": 0,
    "average_speed": 0
}

# WebSocket connections for real-time updates
websocket_connections = []

class VideoInfo(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    title: str = ""
    thumbnail: str = ""
    duration: Optional[int] = None
    uploader: str = ""
    view_count: Optional[int] = None
    upload_date: str = ""
    formats: List[Dict] = []
    status: str = "pending"  # pending, downloading, completed, failed
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    file_path: str = ""
    file_size: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

class DownloadRequest(BaseModel):
    url: str
    quality: str = "best"
    format: str = "mp4"
    filename_template: str = "%(title)s.%(ext)s"
    max_downloads: int = 3

class PlaylistRequest(BaseModel):
    url: str
    quality: str = "best"
    format: str = "mp4"
    max_videos: int = 50

class BulkDownloadRequest(BaseModel):
    urls: List[str]
    quality: str = "best"
    format: str = "mp4"

def get_video_info(url: str) -> Dict[str, Any]:
    """Extract video information using yt-dlp"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if 'entries' in info:  # Playlist
                return {
                    'type': 'playlist',
                    'title': info.get('title', 'Unknown Playlist'),
                    'entries': [{
                        'id': entry.get('id', ''),
                        'title': entry.get('title', 'Unknown'),
                        'url': entry.get('url', ''),
                        'thumbnail': entry.get('thumbnail', ''),
                        'duration': entry.get('duration', 0),
                        'uploader': entry.get('uploader', ''),
                        'view_count': entry.get('view_count', 0),
                    } for entry in info['entries'][:50]]  # Limit to 50 videos
                }
            else:  # Single video
                return {
                    'type': 'video',
                    'id': info.get('id', ''),
                    'title': info.get('title', 'Unknown'),
                    'thumbnail': info.get('thumbnail', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', ''),
                    'view_count': info.get('view_count', 0),
                    'upload_date': info.get('upload_date', ''),
                    'formats': [
                        {
                            'format_id': f.get('format_id', ''),
                            'ext': f.get('ext', ''),
                            'quality': f.get('quality', ''),
                            'filesize': f.get('filesize', 0),
                            'height': f.get('height', 0),
                            'width': f.get('width', 0),
                        } for f in info.get('formats', [])
                    ]
                }
    except Exception as e:
        logging.error(f"Error extracting info from {url}: {e}")
        raise HTTPException(status_code=400, detail=f"Could not extract video info: {str(e)}")

class DownloadProgressHook:
    def __init__(self, video_id: str):
        self.video_id = video_id
        
    def __call__(self, d):
        if self.video_id in active_downloads:
            video_info = active_downloads[self.video_id]
            
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes', d.get('total_bytes_estimate', 0))
                
                if total > 0:
                    progress = (downloaded / total) * 100
                    video_info.progress = round(progress, 1)
                
                video_info.speed = d.get('speed_str', '')
                video_info.eta = d.get('eta_str', '')
                video_info.status = 'downloading'
                
                # Update file size
                if total > 0:
                    video_info.file_size = total
                    
            elif d['status'] == 'finished':
                video_info.progress = 100.0
                video_info.status = 'completed'
                video_info.file_path = d['filename']
                
                # Update global stats
                download_stats['done_downloads'] += 1
                download_stats['active_downloads'] = max(0, download_stats['active_downloads'] - 1)
                download_stats['total_size'] += video_info.file_size
            
            # Broadcast update to all connected WebSockets
            broadcast_update({
                'type': 'download_progress',
                'video_id': self.video_id,
                'data': video_info.dict(),
                'stats': download_stats
            })

def download_video_thread(video_id: str, url: str, options: Dict):
    """Download video in a separate thread"""
    try:
        progress_hook = DownloadProgressHook(video_id)
        
        ydl_opts = {
            'outtmpl': str(DOWNLOADS_DIR / options.get('filename_template', '%(title)s.%(ext)s')),
            'format': f"best[height<={options.get('quality', 'best')}]/best",
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
        }
        
        # Handle format preference
        if options.get('format') == 'mp3':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        elif options.get('format') == 'mp4':
            ydl_opts['format'] = 'best[ext=mp4]/best'
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
    except Exception as e:
        logging.error(f"Download failed for {video_id}: {e}")
        if video_id in active_downloads:
            active_downloads[video_id].status = 'failed'
            broadcast_update({
                'type': 'download_error',
                'video_id': video_id,
                'error': str(e)
            })

def broadcast_update(message: Dict):
    """Broadcast update to all connected WebSocket clients"""
    for connection in websocket_connections[:]:
        try:
            asyncio.create_task(connection.send_text(json.dumps(message)))
        except:
            websocket_connections.remove(connection)

# API Endpoints
@api_router.get("/")
async def root():
    return {"message": "StreamVault Video Downloader API"}

@api_router.get("/stats")
async def get_stats():
    """Get download statistics"""
    return download_stats

@api_router.post("/analyze")
async def analyze_url(request: dict):
    """Analyze a URL to get video/playlist information"""
    url = request.get('url')
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    try:
        info = get_video_info(url)
        return info
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.post("/download")
async def start_download(request: DownloadRequest):
    """Start a single video download"""
    try:
        # Get video info first
        info = get_video_info(request.url)
        
        if info['type'] != 'video':
            raise HTTPException(status_code=400, detail="URL must be a single video")
        
        # Create video info object
        video_id = str(uuid.uuid4())
        video_info = VideoInfo(
            id=video_id,
            url=request.url,
            title=info['title'],
            thumbnail=info['thumbnail'],
            duration=info['duration'],
            uploader=info['uploader'],
            view_count=info['view_count'],
            upload_date=info['upload_date'],
            formats=info['formats'],
            status="pending"
        )
        
        # Add to active downloads
        active_downloads[video_id] = video_info
        
        # Update stats
        download_stats['total_downloads'] += 1
        download_stats['active_downloads'] += 1
        
        # Store in database
        await db.downloads.insert_one(video_info.dict())
        
        # Start download in thread
        options = {
            'quality': request.quality,
            'format': request.format,
            'filename_template': request.filename_template
        }
        
        thread = threading.Thread(
            target=download_video_thread,
            args=(video_id, request.url, options)
        )
        thread.start()
        
        return {"video_id": video_id, "status": "started", "info": video_info.dict()}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.post("/download/bulk")
async def bulk_download(request: BulkDownloadRequest):
    """Start bulk downloads"""
    results = []
    
    for url in request.urls:
        try:
            download_req = DownloadRequest(
                url=url,
                quality=request.quality,
                format=request.format
            )
            result = await start_download(download_req)
            results.append(result)
        except Exception as e:
            results.append({"url": url, "error": str(e)})
    
    return {"results": results}

@api_router.post("/download/playlist")
async def download_playlist(request: PlaylistRequest):
    """Download playlist/channel videos"""
    try:
        info = get_video_info(request.url)
        
        if info['type'] != 'playlist':
            raise HTTPException(status_code=400, detail="URL must be a playlist or channel")
        
        results = []
        for entry in info['entries'][:request.max_videos]:
            try:
                download_req = DownloadRequest(
                    url=entry['url'],
                    quality=request.quality,
                    format=request.format
                )
                result = await start_download(download_req)
                results.append(result)
            except Exception as e:
                results.append({"url": entry['url'], "error": str(e)})
        
        return {
            "playlist_title": info['title'],
            "total_videos": len(info['entries']),
            "downloading": len(results),
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.get("/downloads")
async def get_downloads():
    """Get all downloads from database"""
    try:
        downloads = await db.downloads.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
        # Process downloads for JSON serialization
        processed_downloads = []
        
        for download in downloads:
            # Convert datetime to string for JSON serialization
            if 'created_at' in download and download['created_at']:
                if hasattr(download['created_at'], 'isoformat'):
                    download['created_at'] = download['created_at'].isoformat()
            
            # Merge with active downloads for real-time status
            if download['id'] in active_downloads:
                active_data = active_downloads[download['id']].dict()
                # Convert datetime to string for JSON serialization
                if 'created_at' in active_data and active_data['created_at']:
                    if hasattr(active_data['created_at'], 'isoformat'):
                        active_data['created_at'] = active_data['created_at'].isoformat()
                download.update(active_data)
            
            processed_downloads.append(download)
            
        return processed_downloads
    except Exception as e:
        logging.error(f"Error getting downloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/downloads/{video_id}")
async def delete_download(video_id: str):
    """Delete a download record and file"""
    try:
        # Remove from database
        await db.downloads.delete_one({"id": video_id})
        
        # Remove from active downloads
        if video_id in active_downloads:
            video_info = active_downloads[video_id]
            # Try to delete file
            try:
                if video_info.file_path and os.path.exists(video_info.file_path):
                    os.remove(video_info.file_path)
            except Exception as e:
                logging.error(f"Could not delete file: {e}")
            
            del active_downloads[video_id]
        
        return {"message": "Download deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.delete("/downloads")
async def clear_history():
    """Clear download history"""
    try:
        await db.downloads.delete_many({})
        
        # Clear active downloads
        for video_id in list(active_downloads.keys()):
            video_info = active_downloads[video_id]
            if video_info.status in ['completed', 'failed']:
                del active_downloads[video_id]
        
        # Reset stats
        download_stats.update({
            "total_downloads": len(active_downloads),
            "active_downloads": len([v for v in active_downloads.values() if v.status == 'downloading']),
            "done_downloads": 0,
            "total_size": sum(v.file_size for v in active_downloads.values() if v.status == 'completed'),
            "average_speed": 0
        })
        
        return {"message": "History cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.get("/download/{video_id}/file")
async def download_file(video_id: str):
    """Download the actual video file"""
    if video_id in active_downloads:
        video_info = active_downloads[video_id]
        if video_info.status == 'completed' and video_info.file_path:
            if os.path.exists(video_info.file_path):
                return FileResponse(
                    video_info.file_path,
                    media_type='application/octet-stream',
                    filename=os.path.basename(video_info.file_path)
                )
    
    raise HTTPException(status_code=404, detail="File not found")

@api_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    websocket_connections.append(websocket)
    
    try:
        while True:
            # Send periodic updates
            active_downloads_dict = {}
            for k, v in active_downloads.items():
                video_dict = v.dict()
                # Convert datetime to string for JSON serialization
                if 'created_at' in video_dict and video_dict['created_at']:
                    if hasattr(video_dict['created_at'], 'isoformat'):
                        video_dict['created_at'] = video_dict['created_at'].isoformat()
                active_downloads_dict[k] = video_dict
                
            try:
                await websocket.send_text(json.dumps({
                    'type': 'stats_update',
                    'stats': download_stats,
                    'active_downloads': active_downloads_dict
                }))
            except Exception as send_error:
                logging.error(f"WebSocket send error: {send_error}")
                break
                
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
    finally:
        if websocket in websocket_connections:
            websocket_connections.remove(websocket)

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()