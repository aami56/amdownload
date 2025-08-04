import React, { useState, useEffect } from 'react';
import './App.css';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [activeTab, setActiveTab] = useState('single');
  const [url, setUrl] = useState('');
  const [bulkUrls, setBulkUrls] = useState('');
  const [playlistUrl, setPlaylistUrl] = useState('');
  const [quality, setQuality] = useState('best');
  const [format, setFormat] = useState('mp4');
  const [maxDownloads, setMaxDownloads] = useState(3);
  const [filenameRule, setFilenameRule] = useState('%(title)s.%(ext)s');
  const [proxy, setProxy] = useState('');
  
  const [downloads, setDownloads] = useState([]);
  const [stats, setStats] = useState({
    total_downloads: 0,
    active_downloads: 0,
    done_downloads: 0,
    total_size: 0,
    average_speed: 0
  });
  const [settings, setSettings] = useState({
    autoStart: true,
    parallelDownloads: true,
    notifications: true,
    autoOrganize: false,
    autoRetry: true,
    extractSubtitles: false
  });
  
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [playlistInfo, setPlaylistInfo] = useState(null);

  // WebSocket connection for real-time updates
  useEffect(() => {
    const wsUrl = BACKEND_URL.replace('http', 'ws') + '/api/ws';
    const ws = new WebSocket(wsUrl);
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'stats_update') {
        setStats(data.stats);
        if (data.active_downloads) {
          setDownloads(prev => {
            const updated = { ...data.active_downloads };
            return Object.values(updated);
          });
        }
      }
    };
    
    ws.onclose = () => {
      console.log('WebSocket connection closed');
    };
    
    return () => ws.close();
  }, []);

  // Load downloads and stats on component mount
  useEffect(() => {
    loadDownloads();
    loadStats();
  }, []);

  const loadDownloads = async () => {
    try {
      const response = await axios.get(`${API}/downloads`);
      setDownloads(response.data);
    } catch (error) {
      console.error('Error loading downloads:', error);
    }
  };

  const loadStats = async () => {
    try {
      const response = await axios.get(`${API}/stats`);
      setStats(response.data);
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  };

  const handleSingleDownload = async () => {
    if (!url.trim()) return;
    
    setLoading(true);
    try {
      const response = await axios.post(`${API}/download`, {
        url: url.trim(),
        quality,
        format,
        filename_template: filenameRule
      });
      
      setUrl('');
      await loadDownloads();
      await loadStats();
    } catch (error) {
      alert('Error starting download: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  // Auto-download handler when URL is entered and auto-start is enabled
  const handleUrlChange = async (newUrl) => {
    setUrl(newUrl);
    if (settings.autoStart && newUrl.trim() && (newUrl.includes('youtube.com') || newUrl.includes('youtu.be'))) {
      // Small delay to ensure URL is set
      setTimeout(async () => {
        setLoading(true);
        try {
          const response = await axios.post(`${API}/download`, {
            url: newUrl.trim(),
            quality,
            format,
            filename_template: filenameRule
          });
          
          setUrl('');
          await loadDownloads();
          await loadStats();
        } catch (error) {
          alert('Auto-download failed: ' + (error.response?.data?.detail || error.message));
        } finally {
          setLoading(false);
        }
      }, 500);
    }
  };

  const scheduleDownload = async (downloadId) => {
    const scheduleTime = prompt('Schedule download for (enter time in format HH:MM):');
    if (scheduleTime) {
      try {
        await axios.post(`${API}/schedule`, {
          video_id: downloadId,
          schedule_time: scheduleTime
        });
        alert(`Download scheduled successfully for ${scheduleTime}`);
        await loadDownloads();
      } catch (error) {
        alert('Error scheduling download: ' + (error.response?.data?.detail || error.message));
      }
    }
  };

  const handleBulkDownload = async () => {
    const urls = bulkUrls.split('\n').filter(u => u.trim()).map(u => u.trim());
    if (urls.length === 0) return;
    
    setLoading(true);
    try {
      await axios.post(`${API}/download/bulk`, {
        urls,
        quality,
        format
      });
      
      setBulkUrls('');
      await loadDownloads();
      await loadStats();
    } catch (error) {
      alert('Error starting bulk download: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const analyzePlaylist = async () => {
    if (!playlistUrl.trim()) return;
    
    setAnalyzing(true);
    try {
      const response = await axios.post(`${API}/analyze`, {
        url: playlistUrl.trim()
      });
      
      setPlaylistInfo(response.data);
    } catch (error) {
      alert('Error analyzing playlist: ' + (error.response?.data?.detail || error.message));
    } finally {
      setAnalyzing(false);
    }
  };

  const downloadPlaylist = async () => {
    if (!playlistUrl.trim()) return;
    
    setLoading(true);
    try {
      await axios.post(`${API}/download/playlist`, {
        url: playlistUrl.trim(),
        quality,
        format,
        max_videos: 50
      });
      
      setPlaylistUrl('');
      setPlaylistInfo(null);
      await loadDownloads();
      await loadStats();
    } catch (error) {
      alert('Error downloading playlist: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const deleteDownload = async (videoId) => {
    try {
      await axios.delete(`${API}/downloads/${videoId}`);
      await loadDownloads();
      await loadStats();
    } catch (error) {
      console.error('Error deleting download:', error);
    }
  };

  const clearHistory = async () => {
    if (window.confirm('Are you sure you want to clear all download history?')) {
      try {
        await axios.delete(`${API}/downloads`);
        await loadDownloads();
        await loadStats();
      } catch (error) {
        console.error('Error clearing history:', error);
      }
    }
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '--';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hrs > 0) {
      return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-blue-900 to-purple-800 text-white">
      <div className="container mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div className="flex items-center space-x-3">
            <div className="w-12 h-12 bg-green-500 rounded-lg flex items-center justify-center font-bold text-xl">
              SV
            </div>
            <div>
              <h1 className="text-2xl font-bold">StreamVault</h1>
              <p className="text-gray-300 text-sm">Professional Video Downloader</p>
            </div>
          </div>
          <div className="flex space-x-4">
            <div className="bg-white bg-opacity-10 rounded-lg px-4 py-2 text-center">
              <div className="text-sm text-gray-300">QUEUE</div>
              <div className="text-xl font-bold">{stats.total_downloads}</div>
            </div>
            <div className="bg-white bg-opacity-10 rounded-lg px-4 py-2 text-center">
              <div className="text-sm text-gray-300">ACTIVE</div>
              <div className="text-xl font-bold">{stats.active_downloads}</div>
            </div>
            <div className="bg-white bg-opacity-10 rounded-lg px-4 py-2 text-center">
              <div className="text-sm text-gray-300">DONE</div>
              <div className="text-xl font-bold">{stats.done_downloads}</div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Download Panel */}
          <div className="lg:col-span-2 space-y-6">
            {/* Tab Navigation */}
            <div className="bg-white bg-opacity-10 backdrop-blur-md rounded-xl p-6">
              <div className="flex space-x-2 mb-6">
                <button
                  onClick={() => setActiveTab('single')}
                  className={`px-6 py-2 rounded-lg transition-all ${
                    activeTab === 'single' 
                      ? 'bg-blue-600 text-white' 
                      : 'bg-white bg-opacity-20 hover:bg-opacity-30'
                  }`}
                >
                  Single Video
                </button>
                <button
                  onClick={() => setActiveTab('bulk')}
                  className={`px-6 py-2 rounded-lg transition-all ${
                    activeTab === 'bulk' 
                      ? 'bg-blue-600 text-white' 
                      : 'bg-white bg-opacity-20 hover:bg-opacity-30'
                  }`}
                >
                  Bulk Download
                </button>
                <button
                  onClick={() => setActiveTab('playlist')}
                  className={`px-6 py-2 rounded-lg transition-all ${
                    activeTab === 'playlist' 
                      ? 'bg-blue-600 text-white' 
                      : 'bg-white bg-opacity-20 hover:bg-opacity-30'
                  }`}
                >
                  Playlist/Channel
                </button>
              </div>

              {/* Single Video Tab */}
              {activeTab === 'single' && (
                <div className="space-y-4">
                  <div className="flex space-x-2">
                    <input
                      type="text"
                      placeholder="https://www.youtube.com/watch?v=..."
                      value={url}
                      onChange={(e) => handleUrlChange(e.target.value)}
                      className="flex-1 bg-white bg-opacity-20 rounded-lg px-4 py-3 border border-white border-opacity-30 focus:border-blue-400 focus:outline-none"
                    />
                    <button
                      onClick={() => navigator.clipboard.readText().then(handleUrlChange)}
                      disabled={loading}
                      className="bg-orange-500 hover:bg-orange-600 disabled:opacity-50 px-6 py-3 rounded-lg transition-all"
                    >
                      {loading ? 'Starting...' : 'Paste'}
                    </button>
                    {!settings.autoStart && (
                      <button
                        onClick={handleSingleDownload}
                        disabled={loading || !url.trim()}
                        className="bg-green-500 hover:bg-green-600 disabled:opacity-50 px-6 py-3 rounded-lg transition-all flex items-center space-x-2"
                      >
                        <span>⬇</span>
                        <span>{loading ? 'Starting...' : 'Download'}</span>
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Bulk Download Tab */}
              {activeTab === 'bulk' && (
                <div className="space-y-4">
                  <textarea
                    placeholder="Enter URLs (one per line)"
                    value={bulkUrls}
                    onChange={(e) => setBulkUrls(e.target.value)}
                    rows={6}
                    className="w-full bg-white bg-opacity-20 rounded-lg px-4 py-3 border border-white border-opacity-30 focus:border-blue-400 focus:outline-none resize-none"
                  />
                  <button
                    onClick={handleBulkDownload}
                    disabled={loading || !bulkUrls.trim()}
                    className="bg-green-500 hover:bg-green-600 disabled:opacity-50 px-6 py-3 rounded-lg transition-all"
                  >
                    {loading ? 'Starting Downloads...' : 'Start Bulk Download'}
                  </button>
                </div>
              )}

              {/* Playlist Tab */}
              {activeTab === 'playlist' && (
                <div className="space-y-4">
                  <div className="flex space-x-2">
                    <input
                      type="text"
                      placeholder="https://www.youtube.com/playlist?list=..."
                      value={playlistUrl}
                      onChange={(e) => setPlaylistUrl(e.target.value)}
                      className="flex-1 bg-white bg-opacity-20 rounded-lg px-4 py-3 border border-white border-opacity-30 focus:border-blue-400 focus:outline-none"
                    />
                    <button
                      onClick={analyzePlaylist}
                      disabled={analyzing || !playlistUrl.trim()}
                      className="bg-blue-500 hover:bg-blue-600 disabled:opacity-50 px-6 py-3 rounded-lg transition-all"
                    >
                      {analyzing ? 'Analyzing...' : 'Analyze Playlist/Channel'}
                    </button>
                  </div>
                  
                  {playlistInfo && (
                    <div className="bg-white bg-opacity-10 rounded-lg p-4">
                      <h3 className="font-semibold mb-2">{playlistInfo.title}</h3>
                      <p className="text-gray-300 mb-4">Found {playlistInfo.entries?.length} videos</p>
                      <button
                        onClick={downloadPlaylist}
                        disabled={loading}
                        className="bg-green-500 hover:bg-green-600 disabled:opacity-50 px-6 py-2 rounded-lg transition-all"
                      >
                        {loading ? 'Starting Downloads...' : 'Download All'}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Download Options */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
                <div>
                  <label className="block text-sm text-gray-300 mb-2">📹 Video Quality</label>
                  <select
                    value={quality}
                    onChange={(e) => setQuality(e.target.value)}
                    className="w-full bg-white bg-opacity-20 rounded-lg px-3 py-2 border border-white border-opacity-30 focus:border-blue-400 focus:outline-none"
                  >
                    <option value="best">Best Available</option>
                    <option value="1080">1080p</option>
                    <option value="720">720p</option>
                    <option value="480">480p</option>
                    <option value="360">360p</option>
                  </select>
                </div>
                
                <div>
                  <label className="block text-sm text-gray-300 mb-2">🎵 Format</label>
                  <select
                    value={format}
                    onChange={(e) => setFormat(e.target.value)}
                    className="w-full bg-white bg-opacity-20 rounded-lg px-3 py-2 border border-white border-opacity-30 focus:border-blue-400 focus:outline-none"
                  >
                    <option value="mp4">MP4 (Recommended)</option>
                    <option value="mp3">MP3 (Audio Only)</option>
                    <option value="mkv">MKV</option>
                    <option value="webm">WebM</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm text-gray-300 mb-2">💾 Save Location</label>
                  <div className="flex space-x-2">
                    <input
                      type="text"
                      value="Downloads/StreamVault"
                      readOnly
                      className="flex-1 bg-white bg-opacity-20 rounded-lg px-3 py-2 border border-white border-opacity-30 focus:outline-none"
                    />
                    <button className="bg-white bg-opacity-20 hover:bg-opacity-30 px-3 py-2 rounded-lg transition-all">
                      Browse
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-sm text-gray-300 mb-2">⚡ Max Downloads</label>
                  <input
                    type="number"
                    value={maxDownloads}
                    onChange={(e) => setMaxDownloads(parseInt(e.target.value))}
                    min={1}
                    max={10}
                    className="w-full bg-white bg-opacity-20 rounded-lg px-3 py-2 border border-white border-opacity-30 focus:border-blue-400 focus:outline-none"
                  />
                </div>
              </div>

              {/* Advanced Options */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-2">📝 Filename Rule</label>
                  <input
                    type="text"
                    value={filenameRule}
                    onChange={(e) => setFilenameRule(e.target.value)}
                    className="w-full bg-white bg-opacity-20 rounded-lg px-3 py-2 border border-white border-opacity-30 focus:border-blue-400 focus:outline-none"
                  />
                </div>
                
                <div>
                  <label className="block text-sm text-gray-300 mb-2">🌐 Proxy (Optional)</label>
                  <input
                    type="text"
                    placeholder="http://proxy:port"
                    value={proxy}
                    onChange={(e) => setProxy(e.target.value)}
                    className="w-full bg-white bg-opacity-20 rounded-lg px-3 py-2 border border-white border-opacity-30 focus:border-blue-400 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Downloads List */}
            <div className="bg-white bg-opacity-10 backdrop-blur-md rounded-xl p-6">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-xl font-bold">Videos</h2>
                <button
                  onClick={clearHistory}
                  className="bg-red-500 hover:bg-red-600 px-4 py-2 rounded-lg transition-all"
                >
                  Clear History
                </button>
              </div>

              <div className="space-y-4 max-h-96 overflow-y-auto">
                {downloads.length === 0 ? (
                  <div className="text-center text-gray-400 py-8">
                    No downloads yet. Start downloading some videos!
                  </div>
                ) : (
                  downloads.map((download) => (
                    <div key={download.id} className="bg-white bg-opacity-10 rounded-lg p-4">
                      <div className="flex items-center space-x-4">
                        {download.thumbnail && (
                          <img 
                            src={download.thumbnail} 
                            alt={download.title}
                            className="w-20 h-15 object-cover rounded-lg"
                          />
                        )}
                        <div className="flex-1 min-w-0">
                          <h3 className="font-semibold truncate">{download.title || 'Loading...'}</h3>
                          <p className="text-sm text-gray-300">
                            {download.uploader} • {formatDuration(download.duration)}
                          </p>
                          
                          {download.status === 'downloading' && (
                            <div className="mt-2">
                              <div className="flex justify-between text-sm text-gray-300 mb-1">
                                <span>{download.progress.toFixed(1)}%</span>
                                <span>{download.speed}</span>
                              </div>
                              <div className="w-full bg-gray-700 rounded-full h-2">
                                <div 
                                  className="bg-green-500 h-2 rounded-full transition-all" 
                                  style={{ width: `${download.progress}%` }}
                                />
                              </div>
                            </div>
                          )}
                          
                          {download.status === 'completed' && (
                            <div className="text-sm text-green-400 mt-1">
                              ✓ Ready for Download • {formatBytes(download.file_size)}
                            </div>
                          )}
                          
                          {download.status === 'failed' && (
                            <div className="text-sm text-red-400 mt-1">
                              ✗ Download Failed
                            </div>
                          )}
                        </div>
                        
                        <div className="flex space-x-2">
                          {download.status === 'completed' && (
                            <a
                              href={`${BACKEND_URL}/api/download/${download.id}/file`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="bg-green-500 hover:bg-green-600 px-3 py-2 rounded-lg transition-all text-sm"
                            >
                              Download
                            </a>
                          )}
                          <button 
                            onClick={() => scheduleDownload(download.id)}
                            className="bg-blue-500 hover:bg-blue-600 px-3 py-2 rounded-lg transition-all text-sm"
                          >
                            Schedule
                          </button>
                          <button
                            onClick={() => deleteDownload(download.id)}
                            className="bg-red-500 hover:bg-red-600 px-3 py-2 rounded-lg transition-all text-sm"
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Statistics */}
            <div className="bg-white bg-opacity-10 backdrop-blur-md rounded-xl p-6">
              <h3 className="text-lg font-bold mb-4">Statistics</h3>
              
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="bg-white bg-opacity-10 rounded-lg p-3 text-center">
                  <div className="text-sm text-gray-300">TOTAL</div>
                  <div className="text-2xl font-bold">{stats.total_downloads}</div>
                </div>
                <div className="bg-white bg-opacity-10 rounded-lg p-3 text-center">
                  <div className="text-sm text-gray-300">ACTIVE</div>
                  <div className="text-2xl font-bold">{stats.active_downloads}</div>
                </div>
                <div className="bg-white bg-opacity-10 rounded-lg p-3 text-center">
                  <div className="text-sm text-gray-300">TOTAL SIZE</div>
                  <div className="text-lg font-bold">{formatBytes(stats.total_size)}</div>
                </div>
                <div className="bg-white bg-opacity-10 rounded-lg p-3 text-center">
                  <div className="text-sm text-gray-300">AVG SPEED</div>
                  <div className="text-lg font-bold">0 MB/s</div>
                </div>
              </div>
              
              <div className="text-center text-green-400 text-sm">
                ⭐ StreamVault is ready
              </div>
            </div>

            {/* Quick Settings */}
            <div className="bg-white bg-opacity-10 backdrop-blur-md rounded-xl p-6">
              <h3 className="text-lg font-bold mb-4">Quick Settings</h3>
              
              <div className="space-y-3">
                {Object.entries(settings).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between">
                    <span className="text-sm">
                      {key.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase())}
                    </span>
                    <button
                      onClick={() => setSettings(prev => ({ ...prev, [key]: !value }))}
                      className={`w-12 h-6 rounded-full transition-all ${
                        value ? 'bg-green-500' : 'bg-gray-600'
                      }`}
                    >
                      <div className={`w-5 h-5 bg-white rounded-full transition-all ${
                        value ? 'translate-x-6' : 'translate-x-1'
                      }`} />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* Additional Features */}
            <div className="bg-white bg-opacity-10 backdrop-blur-md rounded-xl p-6">
              <h3 className="text-lg font-bold mb-4">Additional Features</h3>
              
              <div className="grid grid-cols-2 gap-3">
                <button className="bg-white bg-opacity-10 hover:bg-opacity-20 rounded-lg p-3 text-sm transition-all">
                  Schedule Downloads
                </button>
                <button className="bg-white bg-opacity-10 hover:bg-opacity-20 rounded-lg p-3 text-sm transition-all">
                  Format Converter
                </button>
                <button className="bg-white bg-opacity-10 hover:bg-opacity-20 rounded-lg p-3 text-sm transition-all">
                  Download History
                </button>
                <button className="bg-white bg-opacity-10 hover:bg-opacity-20 rounded-lg p-3 text-sm transition-all">
                  Bandwidth Limiter
                </button>
                <button className="bg-white bg-opacity-10 hover:bg-opacity-20 rounded-lg p-3 text-sm transition-all">
                  Metadata Editor
                </button>
                <button className="bg-white bg-opacity-10 hover:bg-opacity-20 rounded-lg p-3 text-sm transition-all">
                  Themes
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;