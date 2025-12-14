# -*- coding: utf-8 -*-
"""
backend/app/utils/temp_directory_manager.py

Temp directory manager mejorado con cleanup manual y retry logic.
Reemplaza safe_temp_directory con mejor manejo de archivos bloqueados.

Author: Sistema de IA
Date: 08/09/2025
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import logging
from pathlib import Path
from typing import Optional, List
from contextlib import contextmanager
import atexit

logger = logging.getLogger(__name__)

class SafeTempDirectory:
    """Context manager mejorado para directorios temporales con cleanup robusto."""
    
    def __init__(self, 
                 prefix: str = "doxai_temp_",
                 ignore_cleanup_errors: bool = True,
                 max_cleanup_retries: int = 3,
                 cleanup_retry_delay: float = 0.5):
        self.prefix = prefix
        self.ignore_cleanup_errors = ignore_cleanup_errors
        self.max_cleanup_retries = max_cleanup_retries
        self.cleanup_retry_delay = cleanup_retry_delay
        self.temp_dir: Optional[Path] = None
        self._atexit_registered = False
        
    def __enter__(self) -> Path:
        self.temp_dir = Path(tempfile.mkdtemp(prefix=self.prefix))
        logger.debug(f"📁 Created temp directory: {self.temp_dir}")
        
        # Register for atexit cleanup as backup
        if not self._atexit_registered:
            atexit.register(self._atexit_cleanup)
            self._atexit_registered = True
            
        return self.temp_dir
        
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()
        
    def cleanup(self) -> bool:
        """Limpia el directorio temporal con retry logic."""
        if not self.temp_dir or not self.temp_dir.exists():
            return True
            
        return self.force_cleanup_directory(self.temp_dir)
        
    def force_cleanup_directory(self, dir_path: Path) -> bool:
        """Fuerza cleanup de directorio con manejo de archivos bloqueados."""
        for attempt in range(self.max_cleanup_retries + 1):
            try:
                if dir_path.exists():
                    # Primero intentar limpiar archivos individuales
                    locked_files = self._cleanup_files_individually(dir_path)
                    
                    if not locked_files:
                        # Si no hay archivos bloqueados, eliminar directorio
                        shutil.rmtree(dir_path)
                        logger.debug(f"✅ Cleaned temp directory: {dir_path}")
                        return True
                    else:
                        # Algunos archivos están bloqueados
                        if attempt < self.max_cleanup_retries:
                            logger.warning(f"⚠️ {len(locked_files)} files locked, retry {attempt + 1}/{self.max_cleanup_retries}")
                            time.sleep(self.cleanup_retry_delay)
                            continue
                        else:
                            # Último intento: quarantine
                            return self._quarantine_locked_files(dir_path, locked_files)
                else:
                    return True
                    
            except Exception as e:
                if attempt < self.max_cleanup_retries:
                    logger.warning(f"⚠️ Cleanup attempt {attempt + 1} failed: {e}")
                    time.sleep(self.cleanup_retry_delay)
                    continue
                else:
                    if self.ignore_cleanup_errors:
                        logger.error(f"❌ Final cleanup attempt failed: {e}")
                        return False
                    else:
                        raise
        
        return False
    
    def _cleanup_files_individually(self, dir_path: Path) -> List[Path]:
        """Intenta limpiar archivos individualmente, retorna lista de archivos bloqueados."""
        locked_files = []
        
        for root, dirs, files in os.walk(dir_path, topdown=False):
            root_path = Path(root)
            
            # Eliminar archivos
            for file in files:
                file_path = root_path / file
                try:
                    file_path.unlink()
                except (PermissionError, OSError) as e:
                    locked_files.append(file_path)
                    logger.debug(f"🔒 Locked file: {file_path} - {e}")
            
            # Eliminar directorios vacíos
            for dir_name in dirs:
                dir_full_path = root_path / dir_name
                try:
                    if dir_full_path.exists() and not any(dir_full_path.iterdir()):
                        dir_full_path.rmdir()
                except (PermissionError, OSError):
                    pass  # Directory not empty or locked
        
        return locked_files
    
    def _quarantine_locked_files(self, dir_path: Path, locked_files: List[Path]) -> bool:
        """Mueve archivos bloqueados a directorio de cuarentena."""
        try:
            quarantine_dir = Path(tempfile.gettempdir()) / "doxai_quarantine"
            quarantine_dir.mkdir(exist_ok=True)
            
            # Mover archivos bloqueados
            moved_count = 0
            for locked_file in locked_files:
                try:
                    if locked_file.exists():
                        quarantine_path = quarantine_dir / f"{int(time.time())}_{locked_file.name}"
                        shutil.move(str(locked_file), str(quarantine_path))
                        moved_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Could not quarantine {locked_file}: {e}")
            
            if moved_count > 0:
                logger.info(f"🏥 Quarantined {moved_count} locked files to {quarantine_dir}")
            
            # Intentar eliminar directorio ahora que los archivos fueron movidos
            try:
                if dir_path.exists():
                    shutil.rmtree(dir_path)
                    logger.info(f"✅ Cleaned temp directory after quarantine: {dir_path}")
                    return True
            except Exception as e:
                logger.error(f"❌ Could not remove temp directory even after quarantine: {e}")
                
        except Exception as e:
            logger.error(f"❌ Quarantine operation failed: {e}")
        
        return False
    
    def _atexit_cleanup(self) -> None:
        """Cleanup llamado por atexit como backup."""
        if self.temp_dir and self.temp_dir.exists():
            logger.debug("🔄 Running atexit cleanup for temp directory")
            self.cleanup()


@contextmanager
def safe_temp_directory_improved(prefix: str = "doxai_temp_", 
                                ignore_cleanup_errors: bool = True):
    """Context manager mejorado para compatibilidad con código existente."""
    with SafeTempDirectory(prefix=prefix, ignore_cleanup_errors=ignore_cleanup_errors) as tmpdir:
        yield tmpdir


def force_cleanup_temp_files(temp_dir: Path, 
                           max_retries: int = 3, 
                           retry_delay: float = 0.5) -> bool:
    """Función independiente para cleanup forzado de archivos temporales."""
    temp_mgr = SafeTempDirectory(max_cleanup_retries=max_retries, 
                                cleanup_retry_delay=retry_delay)
    return temp_mgr.force_cleanup_directory(temp_dir)


def cleanup_quarantine_directory(max_age_hours: int = 24) -> int:
    """Limpia archivos antiguos del directorio de cuarentena."""
    import re
    
    try:
        quarantine_dir = Path(tempfile.gettempdir()) / "doxai_quarantine"
        if not quarantine_dir.exists():
            return 0
        
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        cleaned_count = 0
        
        for file_path in quarantine_dir.iterdir():
            try:
                if file_path.is_file():
                    # Get file age from mtime
                    mtime_age = current_time - file_path.stat().st_mtime
                    
                    # Try to parse timestamp from filename prefix
                    filename_timestamp = None
                    match = re.match(r'^(\d{10,})_', file_path.name)
                    if match:
                        try:
                            filename_timestamp = int(match.group(1))
                        except ValueError:
                            pass
                    
                    # Use the more conservative (older) of the two ages
                    if filename_timestamp:
                        filename_age = current_time - filename_timestamp
                        file_age = max(mtime_age, filename_age)  # Use the older age
                    else:
                        file_age = mtime_age
                    
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        cleaned_count += 1
                        logger.debug(f"🗑️ Cleaned quarantine file: {file_path.name} (age: {file_age/3600:.1f}h)")
                        
            except Exception as e:
                logger.warning(f"⚠️ Could not clean quarantine file {file_path}: {e}")
        
        if cleaned_count > 0:
            logger.info(f"🧹 Cleaned {cleaned_count} old files from quarantine")
            
        return cleaned_count
        
    except Exception as e:
        logger.error(f"❌ Error cleaning quarantine directory: {e}")
        return 0


# Global registry para cleanup en shutdown
_global_temp_directories: List[Path] = []

def register_temp_directory_for_cleanup(temp_dir: Path) -> None:
    """Registra directorio temporal para cleanup global."""
    _global_temp_directories.append(temp_dir)

def force_cleanup_all_temp_directories() -> None:
    """Fuerza cleanup de todos los directorios temporales globales."""
    cleaned_count = 0
    for temp_dir in _global_temp_directories:
        try:
            if force_cleanup_temp_files(temp_dir):
                cleaned_count += 1
        except Exception as e:
            logger.error(f"❌ Error cleaning global temp directory {temp_dir}: {e}")
    
    _global_temp_directories.clear()
    if cleaned_count > 0:
        logger.info(f"🧹 Global cleanup: {cleaned_count} temp directories cleaned")






