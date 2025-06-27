# MosaicMaster & Königstiger Integrated Platform

**Version**: 1.0.0  
**Description**: A comprehensive AI-powered platform combining advanced document processing, video manipulation, live streaming, and transcription services.

## 📋 Overview

MosaicMaster & Königstiger is a sophisticated multimedia processing platform that integrates multiple AI-powered services into a unified web application. The platform provides document translation, video processing, live stream management, transcription services, and advanced video playback capabilities.

## 🏗️ Application Architecture

### Main Entry Point
- **`main-integrated.py`**: Primary FastAPI application integrating all services
- **`config.py`**: Central configuration, logging, and utility functions

### Core Modules

#### 🌐 Web Interface (Frontend)
- **`static/index.html`**: Main MosaicMaster homepage with multi-functional widget
- **`video-player.html`**: Advanced video player with HLS support and GPU acceleration
- **`live-streams.html`**: Live stream management interface (Königstiger)
- **`static/videocutter.html`**: Video editing interface
- **JavaScript Modules**:
  - `static/js/videoeditor/`: Modular video editing components
  - `static/subtitles.js`: Subtitle handling
  - `static/tryitnow.js`: Main interface functionality

#### 🔧 Backend Services

##### 1. **Document Processing (`document_processor.py`)**
- **Purpose**: Multi-format document conversion and OCR
- **Features**:
  - Document conversion between formats (PDF, DOCX, DOC, ODT, TXT, RTF, PPT, PPTX, EPUB, MOBI)
  - OCR for images (JPG, JPEG, PNG, GIF)
  - Batch processing capabilities
  - External tool integration (Calibre, LibreOffice)
- **API Endpoints**: `/api/convert`, `/api/ocr`

##### 2. **Translation Service (`translator.py`)**
- **Purpose**: AI-powered document and text translation
- **Features**:
  - File-based translation with format preservation
  - URL content fetching and translation
  - Text chunking for large documents
  - AI summarization
  - 98+ language support
- **API Endpoint**: `/api/translate`

##### 3. **Video Processing (`video_processor.py`)**
- **Purpose**: Comprehensive video processing and conversion
- **Features**:
  - Multi-platform video downloads (YouTube, Twitter, Facebook, TikTok, Instagram, Twitch, Vimeo)
  - Format conversion and transcoding
  - Subtitle generation and translation
  - Audio extraction
  - Video effects and watermarking
  - Video merging and trimming
- **API Endpoints**: `/api/video/*`

##### 4. **Video Downloader (`videodownloader.py`)**
- **Purpose**: Platform-specific video downloading
- **Features**:
  - Multi-platform support with yt-dlp
  - Cookie management for authenticated access
  - Progress tracking
  - Audio-only downloads
  - Bot detection circumvention
- **Integration**: Used by video processor and live stream handler

##### 5. **Transcription Service (`transcriber.py`)**
- **Purpose**: Audio and video transcription with AI
- **Features**:
  - Whisper-based transcription
  - Speaker identification
  - Multiple output formats (SRT, VTT, TXT, DOCX, PDF)
  - Fast mode for real-time processing
  - Post-processing for accuracy improvement
- **API Endpoints**: `/api/transcribe`

##### 6. **Live Stream Handler (`live_stream_handler.py`)**
- **Purpose**: Live stream recording and processing (Königstiger)
- **Features**:
  - Live stream detection and validation
  - Recording with FFmpeg
  - HLS proxy streaming
  - Real-time transcription
  - Stream monitoring and automatic recovery
- **API Endpoints**: `/api/streams/*`

##### 7. **Text Reader Service (`text_reader_service.py`)**
- **Purpose**: Text-to-speech conversion with AI-powered audio generation
- **Features**:
  - Document text extraction (PDF, DOCX, DOC, ODT, TXT, RTF)
  - OCR for image-based text (JPG, JPEG, PNG, GIF)
  - URL content fetching and text extraction
  - Automatic language detection (Hungarian, English)
  - Text chunking for long documents
  - Google Text-to-Speech (gTTS) integration
  - Multi-part audio generation
  - Background processing with job tracking
- **API Endpoints**: `/api/text-reader/*`

##### 8. **Video Player Service (`video_player.py`)**
- **Purpose**: GPU-accelerated video playback optimization (LEOPARD engine)
- **Features**:
  - GPU acceleration with NVIDIA hardware
  - HLS stream generation
  - Multi-format support (AVI, MKV, MP4, WebM)
  - Stream copy for compatible formats
  - Thumbnail generation
  - Media stream analysis
- **Integration**: Optimized video processing for web playback

##### 9. **GPU Acceleration (`gpu_acceleration.py`)**
- **Purpose**: Hardware acceleration detection and optimization
- **Features**:
  - NVIDIA GPU detection and configuration
  - Hardware encoder selection (h264_nvenc)
  - Performance optimization for video processing

#### 🛠️ Utility Modules
- **`branding.py`**: Application branding and styling
- **`subtitle_module.py`**: Subtitle processing and conversion
- **`videocutter.py`**: Video editing and trimming functionality
- **`videoeditor.py`**: Advanced video editing features
- **`fixed_endpoint.py`**: API endpoint utilities

## 🚀 Features by Service

### MosaicMaster Core Features
1. **Document Translation & Conversion**
   - Translate documents into 98+ languages
   - Convert between multiple formats
   - OCR text extraction from images
   - Batch processing support

2. **Video Processing**
   - Download videos from major platforms
   - Convert between video formats
   - Extract audio (MP3, WAV, OGG)
   - Generate and translate subtitles
   - Apply video effects and watermarks

3. **Transcription Services**
   - Audio/video transcription with high accuracy
   - Speaker identification and separation
   - Multiple output formats
   - Real-time transcription capabilities

4. **Text-to-Speech Services**
   - Convert text documents to audio
   - Support for multiple document formats (PDF, DOCX, DOC, ODT, TXT, RTF)
   - Automatic language detection (Hungarian, English)
   - URL content extraction and conversion
   - OCR-based text extraction from images

### Königstiger Features
1. **Advanced Video Player**
   - GPU-accelerated playback
   - HLS streaming support
   - Multiple audio track and subtitle support
   - Hardware-optimized encoding

2. **Live Stream Management**
   - YouTube, Twitch, Facebook live stream support
   - Real-time recording
   - HLS proxy streaming
   - Automatic transcription of live content
   - Stream monitoring and recovery

## 🔌 API Architecture

### REST API Endpoints
- **Translation**: `POST /api/translate/`
- **Document Conversion**: `POST /api/convert/`
- **OCR Processing**: `POST /api/ocr/`
- **Video Processing**: `POST /api/video/`
- **Transcription**: `POST /api/transcribe/`
- **Text-to-Speech**: `POST /api/text-reader/generate`, `GET /api/text-reader/status/{job_id}`, `GET /api/text-reader/download/{job_id}`
- **Live Streams**: `GET|POST|DELETE /api/streams/`
- **Video Player**: `GET /api/videos/`, `POST /api/upload/`

### WebSocket Connections
- **Progress Updates**: `WS /ws/{connection_id}`
- Real-time progress tracking for long-running operations

### File Downloads
- **Processed Files**: `GET /download/{filename}`
- **Static Assets**: `GET /static/{path}`
- **HLS Streams**: `GET /hls/{stream_id}/`

## 📂 Directory Structure

```
mosaicmasternew/
├── main-integrated.py          # Main application entry point
├── config.py                   # Configuration and utilities
├── static/                     # Frontend assets
│   ├── index.html             # Main homepage
│   ├── js/videoeditor/        # Video editing modules
│   ├── css/                   # Stylesheets
│   └── images/                # Static images
├── templates/                  # HTML templates
│   ├── video-player.html      # Video player interface
│   └── live-streams.html      # Live streams interface
├── Backend Services/
│   ├── translator.py          # Translation service
│   ├── video_processor.py     # Video processing
│   ├── transcriber.py         # Transcription service
│   ├── document_processor.py  # Document conversion
│   ├── videodownloader.py     # Video downloading
│   ├── live_stream_handler.py # Live streaming
│   ├── video_player.py        # Video player service
│   └── gpu_acceleration.py    # Hardware acceleration
├── temp/                       # Temporary processing files
├── uploads/                    # User uploaded files
├── converted/                  # Processed files and thumbnails
├── hls/                       # HLS streaming content
├── recordings/                # Live stream recordings
└── requirements.txt           # Python dependencies
```

## 🔧 Technical Dependencies

### Core Technologies
- **FastAPI**: Modern Python web framework
- **FFmpeg**: Video/audio processing engine
- **yt-dlp**: Video downloading library
- **OpenAI API**: AI services (Whisper, GPT)
- **WebSocket**: Real-time communication

### Media Processing
- **GPU Acceleration**: NVIDIA hardware support
- **HLS Streaming**: HTTP Live Streaming
- **Multi-format Support**: Extensive codec support

### Document Processing
- **Calibre**: E-book conversion
- **LibreOffice**: Office document processing
- **Tesseract**: OCR engine
- **PyMuPDF**: PDF processing

## 🌟 Key Integrations

1. **AI Services Integration**
   - OpenAI Whisper for transcription
   - OpenAI GPT for translation and summarization
   - Speaker identification with AI

2. **Hardware Optimization**
   - NVIDIA GPU acceleration (LEOPARD engine)
   - Hardware-optimized video encoding
   - Performance monitoring and adjustment

3. **Multi-Platform Support**
   - YouTube, Twitter, Facebook, TikTok, Instagram
   - Twitch, Vimeo, and generic stream URLs
   - Automated platform detection

4. **Real-time Processing**
   - WebSocket progress updates
   - Live stream recording and transcription
   - Concurrent processing capabilities

## 🔒 Security Features

- Input validation and sanitization
- Temporary file cleanup
- Rate limiting for API calls
- Secure file handling
- Process isolation for external tools

## 📈 Performance Features

- **Asynchronous Processing**: Non-blocking operations
- **Background Tasks**: Long-running processes
- **GPU Acceleration**: Hardware-optimized video processing
- **Streaming**: Efficient large file handling
- **Caching**: Optimized resource usage

## 🚀 Quick Start

### Installation

1. Ensure Python 3.8+ is installed:
   ```bash
   python3 --version
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate   # Linux/Mac
   venv\Scripts\activate.bat  # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the application:
   ```bash
   ./start.sh
   # or
   python main-integrated.py
   ```

5. Open your browser to:
   ```
   http://localhost:8080
   ```

### Main Interface Access
- **Homepage**: `/` - Main MosaicMaster interface
- **Video Player**: `/video-player.html` - Advanced video player
- **Live Streams**: `/live-streams.html` - Stream management
- **Video Editor**: `/static/videocutter.html` - Video editing tools

## 📋 System Requirements

### Required Software
- **FFmpeg**: Video and audio processing
- **LibreOffice**: Document conversion
- **Python 3.8+**: Runtime environment

### Optional but Recommended
- **Calibre**: E-book conversion
- **NVIDIA GPU**: Hardware acceleration
- **Tesseract**: OCR processing

### API Keys (Required for AI features)
- **OpenAI API Key**: For transcription and translation
- Configure in environment variables or `.env` file

---

**© 2025 MosaicMaster & Königstiger. All rights reserved.**