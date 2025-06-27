import subprocess
import os
import platform
import logging

logger = logging.getLogger(__name__)

class GPUAccelerator:
    """GPU gyorsítás kezelő a videó konverzióhoz"""
    
    def __init__(self):
        self.gpu_type = self._detect_gpu()
        logger.info(f"Detected GPU acceleration capability: {self.gpu_type}")
    
    def _detect_gpu(self):
        """Detektálja a rendelkezésre álló GPU-kat és támogatott gyorsítókat"""
        # Alap információk összegyűjtése
        system = platform.system()
        gpu_info = {"type": "cpu", "name": "CPU Only", "encoder": None}
        
        try:
            # NVIDIA GPU detektálás
            nvidia_smi = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, check=False
            )
            
            if nvidia_smi.returncode == 0 and nvidia_smi.stdout.strip():
                gpu_info["type"] = "nvidia"
                gpu_info["name"] = nvidia_smi.stdout.strip()
                gpu_info["encoder"] = "h264_nvenc"
                return gpu_info
                
            # AMD GPU detektálás Linuxon
            if system == "Linux":
                # Ellenőrizzük az amdgpu drivert
                amdgpu_check = subprocess.run(
                    ["lsmod"], capture_output=True, text=True, check=False
                )
                if "amdgpu" in amdgpu_check.stdout:
                    gpu_info["type"] = "amd"
                    gpu_info["name"] = "AMD GPU"
                    gpu_info["encoder"] = "h264_amf"
                    return gpu_info
                
                # VA-API ellenőrzés
                if os.path.exists("/dev/dri/renderD128"):
                    vaapi_check = subprocess.run(
                        ["vainfo"], capture_output=True, text=True, check=False
                    )
                    if vaapi_check.returncode == 0:
                        gpu_info["type"] = "vaapi"
                        gpu_info["name"] = "VA-API Compatible GPU"
                        gpu_info["encoder"] = "h264_vaapi"
                        return gpu_info
            
            # Intel Quick Sync ellenőrzés
            if system == "Linux":
                intel_check = subprocess.run(
                    ["lspci"], capture_output=True, text=True, check=False
                )
                if "Intel Corporation UHD Graphics" in intel_check.stdout or "Intel Corporation Iris" in intel_check.stdout:
                    gpu_info["type"] = "intel"
                    gpu_info["name"] = "Intel GPU (QSV)"
                    gpu_info["encoder"] = "h264_qsv"
                    return gpu_info
            elif system == "Windows":
                # Windows alatt egyszerűbb detektálás
                # DirectX Diagnostic eszköz használható lenne, de itt szimplán WMI-t használunk
                wmic_check = subprocess.run(
                    ["wmic", "path", "win32_VideoController", "get", "name"],
                    capture_output=True, text=True, check=False
                )
                if "Intel" in wmic_check.stdout and ("UHD" in wmic_check.stdout or "HD Graphics" in wmic_check.stdout):
                    gpu_info["type"] = "intel"
                    gpu_info["name"] = "Intel GPU (QSV)"
                    gpu_info["encoder"] = "h264_qsv"
                    return gpu_info
                elif "NVIDIA" in wmic_check.stdout:
                    gpu_info["type"] = "nvidia"
                    gpu_info["name"] = "NVIDIA GPU"
                    gpu_info["encoder"] = "h264_nvenc"
                    return gpu_info
                elif "AMD" in wmic_check.stdout:
                    gpu_info["type"] = "amd"
                    gpu_info["name"] = "AMD GPU"
                    gpu_info["encoder"] = "h264_amf"
                    return gpu_info
        
        except Exception as e:
            logger.warning(f"Error during GPU detection: {e}")
        
        # Fallback: CPU-t használunk
        return gpu_info
    
    def get_ffmpeg_hwaccel_args(self):
        """Visszaadja a megfelelő FFmpeg hardveres gyorsítási paramétereket"""
        if self.gpu_type["type"] == "cpu":
            # CPU-alapú kódolás, nincs hardveres gyorsítás
            return []
        
        elif self.gpu_type["type"] == "nvidia":
            # NVIDIA NVENC - csak hwaccel paramétert használunk, a kimenet formátumát nem állítjuk át
            # Ez megoldja a kompatibilitási problémákat egyes NVIDIA driverekkel
            return ["-hwaccel", "cuda"]
        
        elif self.gpu_type["type"] == "intel":
            # Intel Quick Sync
            if platform.system() == "Linux":
                return ["-hwaccel", "qsv"]
            else:
                return ["-hwaccel", "dxva2"]
        
        elif self.gpu_type["type"] == "amd":
            # AMD AMF
            if platform.system() == "Linux":
                return ["-hwaccel", "vaapi", "-hwaccel_device", "/dev/dri/renderD128"]
            else:
                return ["-hwaccel", "d3d11va"]
        
        elif self.gpu_type["type"] == "vaapi":
            # VA-API
            return ["-hwaccel", "vaapi", "-hwaccel_device", "/dev/dri/renderD128"]
        
        # Fallback: üres lista
        return []
    
    def get_encoder_args(self, target_format="h264"):
        """Visszaadja a megfelelő kodek argumentumokat a kódoláshoz"""
        if self.gpu_type["type"] == "cpu" or self.gpu_type["encoder"] is None:
            # CPU-alapú kódolás
            if target_format == "h264":
                return ["-c:v", "libx264", "-preset", "fast"]
            elif target_format == "h265":
                return ["-c:v", "libx265", "-preset", "fast"]
            elif target_format == "vp9":
                return ["-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "2"]
            else:
                return ["-c:v", "libx264", "-preset", "fast"]
        
        elif self.gpu_type["type"] == "nvidia":
            # NVIDIA encoders with more compatible settings
            if target_format == "h264":
                return ["-c:v", "h264_nvenc", "-preset", "fast"]
            elif target_format == "h265":
                return ["-c:v", "hevc_nvenc", "-preset", "fast"]
            else:
                return ["-c:v", "h264_nvenc", "-preset", "fast"]
        
        elif self.gpu_type["type"] == "intel":
            # Intel Quick Sync
            if target_format == "h264":
                return ["-c:v", "h264_qsv", "-preset", "medium"]
            elif target_format == "h265":
                return ["-c:v", "hevc_qsv", "-preset", "medium"]
            else:
                return ["-c:v", "h264_qsv", "-preset", "medium"]
        
        elif self.gpu_type["type"] == "amd":
            # AMD 
            if target_format == "h264":
                return ["-c:v", "h264_amf", "-quality", "balanced"]
            elif target_format == "h265":
                return ["-c:v", "hevc_amf", "-quality", "balanced"]
            else:
                return ["-c:v", "h264_amf", "-quality", "balanced"]
        
        elif self.gpu_type["type"] == "vaapi":
            # VA-API
            if target_format == "h264":
                return ["-c:v", "h264_vaapi"]
            elif target_format == "h265":
                return ["-c:v", "hevc_vaapi"]
            else:
                return ["-c:v", "h264_vaapi"]
        
        # Fallback CPU
        return ["-c:v", "libx264", "-preset", "fast"]
