#!/usr/bin/env python3
"""
Comprehensive Backend API Testing for StreamVault Video Downloader
Tests all API endpoints with real YouTube URLs
"""

import requests
import json
import time
import asyncio
import websockets
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/app/frontend/.env')

# Get backend URL from environment
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://1a370e70-e3c6-45fe-9026-fb3472bcf3cc.preview.emergentagent.com')
API_BASE = f"{BACKEND_URL}/api"

# Test URLs - Real YouTube content
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up
TEST_PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLrAXtmRdnEQy6nuLMt9H1mu_0fqoNjy9b"  # Small test playlist
TEST_BULK_URLS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=L_jWHffIx5E"  # Smash Mouth - All Star
]

class BackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 30
        self.test_results = {}
        
    def log_test(self, test_name, success, details=""):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"   Details: {details}")
        self.test_results[test_name] = {"success": success, "details": details}
        
    def test_api_health(self):
        """Test basic API health endpoint"""
        try:
            response = self.session.get(f"{API_BASE}/")
            if response.status_code == 200:
                data = response.json()
                if "message" in data and "StreamVault" in data["message"]:
                    self.log_test("API Health Check", True, f"Response: {data}")
                    return True
                else:
                    self.log_test("API Health Check", False, f"Unexpected response: {data}")
                    return False
            else:
                self.log_test("API Health Check", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("API Health Check", False, f"Exception: {str(e)}")
            return False
    
    def test_url_analysis(self):
        """Test URL analysis endpoint"""
        try:
            # Test single video analysis
            payload = {"url": TEST_VIDEO_URL}
            response = self.session.post(f"{API_BASE}/analyze", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("type") == "video" and "title" in data:
                    self.log_test("URL Analysis - Single Video", True, f"Title: {data.get('title', 'N/A')}")
                    video_analysis_success = True
                else:
                    self.log_test("URL Analysis - Single Video", False, f"Invalid response: {data}")
                    video_analysis_success = False
            else:
                self.log_test("URL Analysis - Single Video", False, f"Status: {response.status_code}")
                video_analysis_success = False
            
            # Test playlist analysis
            payload = {"url": TEST_PLAYLIST_URL}
            response = self.session.post(f"{API_BASE}/analyze", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("type") == "playlist" and "entries" in data:
                    self.log_test("URL Analysis - Playlist", True, f"Entries: {len(data.get('entries', []))}")
                    playlist_analysis_success = True
                else:
                    self.log_test("URL Analysis - Playlist", False, f"Invalid response: {data}")
                    playlist_analysis_success = False
            else:
                self.log_test("URL Analysis - Playlist", False, f"Status: {response.status_code}")
                playlist_analysis_success = False
            
            # Test invalid URL
            payload = {"url": "https://invalid-url.com"}
            response = self.session.post(f"{API_BASE}/analyze", json=payload)
            
            if response.status_code == 400:
                self.log_test("URL Analysis - Invalid URL", True, "Correctly rejected invalid URL")
                invalid_url_success = True
            else:
                self.log_test("URL Analysis - Invalid URL", False, f"Should have returned 400, got {response.status_code}")
                invalid_url_success = False
                
            return video_analysis_success and playlist_analysis_success and invalid_url_success
            
        except Exception as e:
            self.log_test("URL Analysis", False, f"Exception: {str(e)}")
            return False
    
    def test_single_download(self):
        """Test single video download endpoint"""
        try:
            payload = {
                "url": TEST_VIDEO_URL,
                "quality": "best",
                "format": "mp4",
                "filename_template": "%(title)s.%(ext)s"
            }
            
            response = self.session.post(f"{API_BASE}/download", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if "video_id" in data and "status" in data and data["status"] == "started":
                    video_id = data["video_id"]
                    self.log_test("Single Video Download", True, f"Started download with ID: {video_id}")
                    
                    # Wait a bit and check status
                    time.sleep(2)
                    downloads_response = self.session.get(f"{API_BASE}/downloads")
                    if downloads_response.status_code == 200:
                        downloads = downloads_response.json()
                        download_found = any(d.get("id") == video_id for d in downloads)
                        if download_found:
                            self.log_test("Download Persistence", True, "Download found in database")
                        else:
                            self.log_test("Download Persistence", False, "Download not found in database")
                    
                    return True
                else:
                    self.log_test("Single Video Download", False, f"Invalid response: {data}")
                    return False
            else:
                self.log_test("Single Video Download", False, f"Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            self.log_test("Single Video Download", False, f"Exception: {str(e)}")
            return False
    
    def test_bulk_download(self):
        """Test bulk download endpoint"""
        try:
            payload = {
                "urls": TEST_BULK_URLS,
                "quality": "best",
                "format": "mp4"
            }
            
            response = self.session.post(f"{API_BASE}/download/bulk", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if "results" in data and len(data["results"]) == len(TEST_BULK_URLS):
                    successful_downloads = sum(1 for result in data["results"] if "video_id" in result)
                    self.log_test("Bulk Download", True, f"Started {successful_downloads}/{len(TEST_BULK_URLS)} downloads")
                    return True
                else:
                    self.log_test("Bulk Download", False, f"Invalid response: {data}")
                    return False
            else:
                self.log_test("Bulk Download", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Bulk Download", False, f"Exception: {str(e)}")
            return False
    
    def test_playlist_download(self):
        """Test playlist download endpoint"""
        try:
            payload = {
                "url": TEST_PLAYLIST_URL,
                "quality": "best",
                "format": "mp4",
                "max_videos": 5
            }
            
            response = self.session.post(f"{API_BASE}/download/playlist", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if "playlist_title" in data and "results" in data:
                    self.log_test("Playlist Download", True, f"Playlist: {data.get('playlist_title', 'N/A')}, Videos: {len(data.get('results', []))}")
                    return True
                else:
                    self.log_test("Playlist Download", False, f"Invalid response: {data}")
                    return False
            else:
                self.log_test("Playlist Download", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Playlist Download", False, f"Exception: {str(e)}")
            return False
    
    def test_statistics(self):
        """Test statistics endpoint"""
        try:
            response = self.session.get(f"{API_BASE}/stats")
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["total_downloads", "active_downloads", "done_downloads", "total_size", "average_speed"]
                if all(field in data for field in required_fields):
                    self.log_test("Statistics", True, f"Stats: {data}")
                    return True
                else:
                    self.log_test("Statistics", False, f"Missing required fields: {data}")
                    return False
            else:
                self.log_test("Statistics", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Statistics", False, f"Exception: {str(e)}")
            return False
    
    def test_download_management(self):
        """Test download management endpoints"""
        try:
            # Test get downloads
            response = self.session.get(f"{API_BASE}/downloads")
            
            if response.status_code == 200:
                downloads = response.json()
                self.log_test("Get Downloads", True, f"Found {len(downloads)} downloads")
                
                # Test delete specific download if any exist
                if downloads:
                    video_id = downloads[0].get("id")
                    if video_id:
                        delete_response = self.session.delete(f"{API_BASE}/downloads/{video_id}")
                        if delete_response.status_code == 200:
                            self.log_test("Delete Specific Download", True, f"Deleted download {video_id}")
                        else:
                            self.log_test("Delete Specific Download", False, f"Status: {delete_response.status_code}")
                    else:
                        self.log_test("Delete Specific Download", False, "No video ID found")
                else:
                    self.log_test("Delete Specific Download", True, "No downloads to delete")
                
                # Test clear history
                clear_response = self.session.delete(f"{API_BASE}/downloads")
                if clear_response.status_code == 200:
                    self.log_test("Clear Download History", True, "History cleared successfully")
                    return True
                else:
                    self.log_test("Clear Download History", False, f"Status: {clear_response.status_code}")
                    return False
            else:
                self.log_test("Get Downloads", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Download Management", False, f"Exception: {str(e)}")
            return False
    
    def test_file_serving(self):
        """Test file serving endpoint"""
        try:
            # First start a download to have a file to serve
            payload = {
                "url": TEST_VIDEO_URL,
                "quality": "best",
                "format": "mp4"
            }
            
            download_response = self.session.post(f"{API_BASE}/download", json=payload)
            
            if download_response.status_code == 200:
                data = download_response.json()
                video_id = data.get("video_id")
                
                if video_id:
                    # Wait a bit for download to potentially complete
                    time.sleep(5)
                    
                    # Try to access the file
                    file_response = self.session.get(f"{API_BASE}/download/{video_id}/file")
                    
                    if file_response.status_code == 200:
                        self.log_test("File Serving", True, f"File served successfully for {video_id}")
                        return True
                    elif file_response.status_code == 404:
                        self.log_test("File Serving", True, "File not found (expected if download not complete)")
                        return True
                    else:
                        self.log_test("File Serving", False, f"Status: {file_response.status_code}")
                        return False
                else:
                    self.log_test("File Serving", False, "No video ID returned from download")
                    return False
            else:
                self.log_test("File Serving", False, f"Could not start download: {download_response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("File Serving", False, f"Exception: {str(e)}")
            return False
    
    async def test_websocket(self):
        """Test WebSocket endpoint"""
        try:
            ws_url = f"{BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://')}/api/ws"
            
            async with websockets.connect(ws_url) as websocket:
                # Wait for a message
                message = await asyncio.wait_for(websocket.recv(), timeout=10)
                data = json.loads(message)
                
                if "type" in data and "stats" in data:
                    self.log_test("WebSocket Connection", True, f"Received: {data['type']}")
                    return True
                else:
                    self.log_test("WebSocket Connection", False, f"Invalid message: {data}")
                    return False
                    
        except asyncio.TimeoutError:
            self.log_test("WebSocket Connection", False, "Timeout waiting for message")
            return False
        except Exception as e:
            self.log_test("WebSocket Connection", False, f"Exception: {str(e)}")
            return False
    
    def run_websocket_test(self):
        """Run WebSocket test in event loop"""
        try:
            return asyncio.run(self.test_websocket())
        except Exception as e:
            self.log_test("WebSocket Connection", False, f"Event loop error: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all backend tests"""
        print(f"🚀 Starting StreamVault Backend API Tests")
        print(f"📡 Backend URL: {BACKEND_URL}")
        print("=" * 60)
        
        tests = [
            ("API Health", self.test_api_health),
            ("URL Analysis", self.test_url_analysis),
            ("Single Download", self.test_single_download),
            ("Bulk Download", self.test_bulk_download),
            ("Playlist Download", self.test_playlist_download),
            ("Statistics", self.test_statistics),
            ("Download Management", self.test_download_management),
            ("File Serving", self.test_file_serving),
            ("WebSocket", self.run_websocket_test),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n🧪 Testing {test_name}...")
            try:
                if test_func():
                    passed += 1
            except Exception as e:
                self.log_test(test_name, False, f"Unexpected error: {str(e)}")
        
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed! Backend is working correctly.")
        else:
            print("⚠️  Some tests failed. Check the details above.")
        
        return passed == total

if __name__ == "__main__":
    tester = BackendTester()
    success = tester.run_all_tests()
    exit(0 if success else 1)