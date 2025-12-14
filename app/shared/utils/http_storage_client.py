
# -*- coding: utf-8 -*-
"""
backend/app/utils/http_storage_client.py

Cliente HTTP para operaciones de Supabase Storage usando httpx directamente.
Optimizado con:
- Connection pooling para mejor rendimiento
- Compresión automática de uploads
- Manejo robusto de errores

Este cliente mantiene la misma funcionalidad que el cliente oficial pero con control
total sobre las requests HTTP y mejor manejo de errores.

Autor: Ixchel Beristain
Fecha: 10/07/2025 (optimizado: 05/11/2025)
"""

import logging
import httpx
import threading
from typing import List, Dict, Any, Optional, Union
from app.shared.config import settings

# Usar connection pool si está disponible
try:
    from app.shared.utils.connection_pool import get_pooled_client
    USE_CONNECTION_POOL = True
except ImportError:
    from app.shared.core.resource_cache import get_http_client
    async def get_pooled_client():
        return await get_http_client()
    USE_CONNECTION_POOL = False

logger = logging.getLogger(__name__)

if USE_CONNECTION_POOL:
    logger.info("🚀 HTTP Storage Client using optimized connection pool")


def _is_not_found(response: httpx.Response) -> bool:
    """
    Helper para detectar respuestas 'not found' de Supabase Storage.
    
    ROBUSTO: Maneja HTTP 404, HTTP 400 con error="not_found", y HTTP 400 genérico
    como "no existe" para eliminar ruido en logs cuando archivos simplemente no existen.
    """
    if response.status_code == 404:
        return True
    
    # Tratamiento robusto de HTTP 400 como "not found" genérico
    # Esto elimina el ruido de logs cuando se verifica existencia de archivos
    if response.status_code == 400:
        try:
            data = response.json()
            # Verificar si es explícitamente "not_found"
            if data.get("error") == "not_found":
                return True
            # Tratar otros 400 como "no existe" para HEAD requests (robustez)
            return True
        except Exception:
            # Si no se puede parsear JSON, asumir que es "not found"
            return True
    
    return False


async def exists(storage_path: str, bucket: str = None) -> bool:
    """
    Check if a file exists in Supabase Storage.
    
    Args:
        storage_path: Path to the file in storage
        bucket: Optional bucket name (uses default if not provided)
        
    Returns:
        bool: True if file exists, False otherwise
    """
    from app.shared.config import settings
    
    bucket = bucket or settings.supabase_bucket_name
    client = await get_pooled_client()  # Usar pool de conexiones
    
    # Use HEAD request to check existence
    url = f"{settings.supabase_url}/storage/v1/object/{bucket}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}"
    }
    
    try:
        response = await client.head(url, headers=headers)
        
        if response.status_code in (200, 206):
            logger.debug(f"📄 Storage hit for {storage_path} (HEAD 200)")
            return True
        elif _is_not_found(response):
            logger.debug(f"📄 Storage miss for {storage_path} (HEAD {response.status_code})")
            return False
        else:
            logger.warning(f"HEAD unexpected status {response.status_code} for {storage_path}")
            return False
            
    except Exception as e:
        logger.debug(f"📄 Storage miss for {storage_path} (exception: {str(e)})")
        return False


async def storage_exists(storage_path: str) -> bool:
    """
    Verifica si un archivo existe en Supabase Storage usando el cliente HTTP compartido.
    
    Args:
        storage_path: Ruta completa del archivo en storage
        
    Returns:
        True si el archivo existe, False caso contrario
    """
    from app.shared.config import settings
    
    client = await get_http_client()
    
    # Extract folder and filename from storage path
    path_parts = storage_path.rstrip('/').split('/')
    if len(path_parts) == 1:
        # File in root
        folder = ""
        target_file = path_parts[0]
    else:
        folder = '/'.join(path_parts[:-1])
        target_file = path_parts[-1]
    
    # List files in folder and check if target file exists
    list_url = f"{settings.supabase_url}/storage/v1/object/list/{settings.supabase_bucket_name}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json"
    }
    
    payload = {"prefix": folder, "limit": 1000}
    
    try:
        response = await client.post(list_url, headers=headers, json=payload)
        if response.status_code != 200:
            return False
            
        files = response.json()
        for file_info in files:
            if file_info.get("name") == target_file:
                return True
        
        return False
    except Exception:
        return False


class SupabaseStorageHTTPClient:
    """
    Cliente HTTP para operaciones de Supabase Storage.
    
    Proporciona métodos equivalentes al cliente oficial de Supabase
    pero usando httpx directamente para evitar conflictos de dependencias.
    """
    
    def __init__(self):
        if not all([settings.supabase_url, settings.supabase_service_role_key]):
            raise RuntimeError("❌ Faltan variables de entorno para Supabase Storage")
        
        self.base_url = settings.supabase_url
        self.headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json"
        }
    
    async def upload_file(
        self, 
        bucket: str, 
        path: str, 
        file_data: bytes, 
        content_type: str = "application/octet-stream",
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Sube un archivo a Supabase Storage.
        
        Args:
            bucket (str): Nombre del bucket
            path (str): Ruta completa del archivo en el bucket
            file_data (bytes): Contenido binario del archivo
            content_type (str): Tipo MIME del archivo
            overwrite (bool): Si True, usa upsert para sobrescribir archivos existentes
            
        Returns:
            Dict[str, Any]: Respuesta de la API de Supabase
            
        Raises:
            RuntimeError: Si la operación falla
        """
        url = f"{self.base_url}/storage/v1/object/{bucket}/{path}"
        headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": content_type
        }
        
        # Add upsert header if overwrite is enabled
        if overwrite:
            headers["x-upsert"] = "true"
        
        try:
            client = await get_pooled_client()  # Usar pool de conexiones
            response = await client.post(url, headers=headers, content=file_data)
                
            # Handle 409 Duplicate - retry with upsert if not already enabled
            if response.status_code == 409 and not overwrite:
                logger.debug(f"📄 File exists, retrying with upsert: {path}")
                headers["x-upsert"] = "true"
                response = await client.post(url, headers=headers, content=file_data)
            
            if response.status_code == 409:
                logger.info(f"📄 Archivo ya existe en Storage: {path}")
                return {"message": "File already exists", "duplicate": True}
            elif response.status_code not in [200, 201]:
                logger.error(f"❌ Error al subir archivo: {response.status_code} - {response.text}")
                raise RuntimeError(f"Error al subir archivo a Supabase: {response.status_code}")
            
            # Log successful upload/overwrite
            action = "sobrescrito" if overwrite else "subido correctamente"
            logger.info(f"✅ Archivo {action}: {path}")
            return response.json() if response.content else {}
            
        except httpx.RequestError as e:
            logger.error(f"🔥 Error de conexión al subir archivo: {str(e)}")
            raise RuntimeError(f"Error de conexión: {str(e)}")
    
    async def get_file_metadata(self, bucket: str, path: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene metadatos del archivo usando HEAD request.
        Retorna dict con 'exists', 'etag', 'content_length', etc.
        Retorna None si no puede obtener los metadatos.
        """
        url = f"{self.base_url}/storage/v1/object/{bucket}/{path}"
        headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}"
        }
        
        try:
            client = await get_http_client()
            response = await client.head(url, headers=headers)
            
            if response.status_code in (200, 206):
                # Extract relevant metadata from response headers
                metadata = {
                    "exists": True,
                    "etag": response.headers.get("etag", "").strip('"'),
                    "content_length": int(response.headers.get("content-length", 0)),
                    "last_modified": response.headers.get("last-modified"),
                    "content_type": response.headers.get("content-type"),
                }
                logger.debug(f"📄 HEAD request successful for {path}: etag={metadata['etag'][:8]}...")
                return metadata
            elif _is_not_found(response):
                return {"exists": False}
            else:
                logger.debug(f"HEAD request failed for {path}: {response.status_code}")
                return None
                
        except Exception as e:
            logger.debug(f"HEAD request failed for {path}: {e}")
            return None

    async def download_file_with_etag_check(
        self, 
        bucket: str, 
        path: str, 
        if_none_match: Optional[str] = None
    ) -> Union[bytes, dict, None]:
        """
        Descarga archivo con verificación ETag opcional para idempotencia.
        Si if_none_match coincide, retorna {"not_modified": True}.
        Si no coincide o no existe ETag, descarga normalmente.
        """
        url = f"{self.base_url}/storage/v1/object/{bucket}/{path}"
        headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}"
        }
        
        # Agregar If-None-Match header si se proporciona
        if if_none_match:
            headers["If-None-Match"] = f'"{if_none_match}"'
        
        try:
            client = await get_pooled_client()  # Usar pool de conexiones
            response = await client.get(url, headers=headers)
            
            if response.status_code == 304:
                # Not Modified - contenido no ha cambiado
                logger.debug(f"📋 If-None-Match: Not modified for {path}")
                return {"not_modified": True}
            elif response.status_code == 200:
                logger.debug(f"📥 Downloaded {path} ({len(response.content)} bytes)")
                return response.content
            elif _is_not_found(response):
                raise FileNotFoundError(f"Archivo no encontrado: {path}")
            else:
                raise RuntimeError(f"Error al descargar archivo: HTTP {response.status_code}")
                
        except httpx.RequestError as e:
            raise RuntimeError(f"Error de conexión al descargar archivo: {e}")
    
    async def download_file(self, bucket: str, path: str, if_none_match: str = None) -> dict:
        """
        Descarga un archivo desde Supabase Storage con soporte para conditional requests.
        
        Args:
            bucket (str): Nombre del bucket
            path (str): Ruta completa del archivo en el bucket
            if_none_match (str): ETag para conditional request (opcional)
            
        Returns:
            dict: {"content": bytes, "etag": str, "not_modified": bool}
            
        Raises:
            FileNotFoundError: Si el archivo no existe
            RuntimeError: Si la operación falla
        """
        url = f"{self.base_url}/storage/v1/object/{bucket}/{path}"
        headers = self.headers.copy()
        
        # Add conditional headers if provided
        if if_none_match:
            headers["If-None-Match"] = if_none_match
        
        try:
            client = await get_http_client()
            response = await client.get(url, headers=headers)
            
            if response.status_code == 304:
                # Not modified - content hasn't changed
                logger.debug(f"📋 Conditional GET: Not modified for {path}")
                return {"content": None, "etag": if_none_match, "not_modified": True}
            elif _is_not_found(response):
                raise FileNotFoundError(f"El archivo '{path}' no existe en el bucket '{bucket}'")
            elif response.status_code != 200:
                logger.error(f"❌ Error al descargar archivo: {response.status_code} - {response.text}")
                raise RuntimeError(f"Error al descargar archivo: {response.status_code}")
                
            # Extract ETag from response headers
            etag = response.headers.get("etag", "").strip('"')
            
            # Log download with conditional info
            if if_none_match:
                logger.debug(f"📥 Conditional GET: Content changed for {path} ({len(response.content)} bytes)")
            else:
                logger.debug(f"📥 Downloaded {path} ({len(response.content)} bytes, etag: {etag[:8]}...)")
            
            return {"content": response.content, "etag": etag, "not_modified": False}
            
        except httpx.RequestError as e:
            logger.error(f"🔥 Error de conexión al descargar archivo: {str(e)}")
            raise RuntimeError(f"Error de conexión: {str(e)}")
    
    async def delete_file(self, bucket: str, path: str) -> bool:
        """
        Elimina un archivo de Supabase Storage.
        
        Args:
            bucket (str): Nombre del bucket
            path (str): Ruta completa del archivo en el bucket
            
        Returns:
            bool: True si se eliminó correctamente
            
        Raises:
            FileNotFoundError: Si el archivo no existe (404)
            RuntimeError: Si la operación falla por otras causas
        """
        url = f"{self.base_url}/storage/v1/object/{bucket}/{path}"
        
        # Headers específicos para DELETE (sin Content-Type)
        delete_headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}"
        }
        
        try:
            client = await get_http_client()
            response = await client.delete(url, headers=delete_headers)
                
            # ✅ FASE 2: Manejo detallado de códigos de estado
            if response.status_code == 404:
                logger.warning(f"⚠️ Archivo no encontrado para eliminación: {path}")
                raise FileNotFoundError(f"El archivo '{path}' no existe en el bucket '{bucket}'")
            elif response.status_code == 403:
                logger.error(f"🔒 Sin permisos para eliminar archivo: {path}")
                raise RuntimeError(f"Sin permisos para eliminar archivo (403): {path}")
            elif response.status_code == 401:
                logger.error(f"🔑 Token de autorización inválido para eliminación: {path}")
                raise RuntimeError(f"Token de autorización inválido (401)")
            elif response.status_code not in [200, 204]:
                error_text = response.text if hasattr(response, 'text') else "Sin detalles"
                logger.error(f"❌ Error HTTP {response.status_code} al eliminar archivo {path}: {error_text}")
                raise RuntimeError(f"Error HTTP {response.status_code} al eliminar archivo: {error_text}")
                
            logger.info(f"🗑️ Archivo eliminado correctamente: {path}")
            return True
            
        except httpx.TimeoutException as e:
            logger.error(f"⏱️ Timeout al eliminar archivo {path}: {str(e)}")
            raise RuntimeError(f"Timeout de conexión al eliminar archivo: {str(e)}")
        except httpx.ConnectError as e:
            logger.error(f"🌐 Error de conexión al eliminar archivo {path}: {str(e)}")
            raise RuntimeError(f"Error de conectividad con Supabase: {str(e)}")
        except httpx.RequestError as e:
            logger.error(f"🔥 Error de request al eliminar archivo {path}: {str(e)}")
            raise RuntimeError(f"Error de conexión HTTP: {str(e)}")
        except FileNotFoundError:
            # Re-raise FileNotFoundError tal como está
            raise
        except Exception as e:
            logger.error(f"💥 Error inesperado al eliminar archivo {path}: {str(e)}")
            raise RuntimeError(f"Error inesperado: {str(e)}")
    
    async def list_files(
        self, 
        bucket: str, 
        prefix: str = "", 
        limit: int = 100, 
        offset: int = 0,
        recursive: bool = False
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Lista archivos en Supabase Storage con paginación.

        Args:
            bucket: Nombre del bucket
            prefix: Prefijo para filtrar archivos
            limit: Número máximo de archivos a retornar (default: 100)
            offset: Número de archivos a saltar (default: 0)
            recursive: Si True, busca recursivamente en subdirectorios

        Returns:
            Lista de archivos o dict con {'files': [...], 'has_more': bool}
        """
        url = f"{self.base_url}/storage/v1/object/list/{bucket}"
        payload = {
            "prefix": prefix,
            "limit": limit,
            "offset": offset
        }

        try:
            client = await get_http_client()
            response = await client.post(url, headers=self.headers, json=payload)

            if response.status_code != 200:
                logger.error(f"❌ Error al listar archivos: {response.status_code} - {response.text}")
                raise RuntimeError(f"Error al listar archivos: {response.status_code} - {response.text}")

            files = response.json()
            logger.debug(f"📂 Se encontraron {len(files)} archivos con prefijo '{prefix}' en bucket '{bucket}' (offset={offset}, limit={limit})")
            
            # Return format compatible with cache_eviction_service expectations
            return {
                'files': files,
                'has_more': len(files) >= limit
            }

        except httpx.RequestError as e:
            logger.error(f"🔥 Error de conexión al listar archivos: {str(e)}")
            raise RuntimeError(f"Error de conexión: {str(e)}")

    
    async def create_signed_url(
        self, 
        bucket: str, 
        path: str, 
        expires_in: int = 3600
    ) -> str:
        """
        Crea una URL firmada para acceso temporal a un archivo.
        
        Args:
            bucket (str): Nombre del bucket
            path (str): Ruta completa del archivo en el bucket
            expires_in (int): Tiempo de validez en segundos
            
        Returns:
            str: URL firmada válida por el tiempo especificado
            
        Raises:
            RuntimeError: Si la operación falla
        """
        url = f"{self.base_url}/storage/v1/object/sign/{bucket}/{path}"
        payload = {"expiresIn": expires_in}
        
        try:
            client = await get_http_client()
            response = await client.post(url, headers=self.headers, json=payload)
                
            if response.status_code != 200:
                logger.error(f"❌ Error al crear URL firmada: {response.status_code} - {response.text}")
                raise RuntimeError(f"Error al crear URL firmada: {response.status_code}")
                
            result = response.json()
            signed_url = result.get("signedURL")
            if not signed_url:
                raise RuntimeError("No se pudo generar la URL firmada desde Supabase")
                
            logger.info(f"🔐 URL firmada generada: {signed_url}")
            return signed_url
            
        except httpx.RequestError as e:
            logger.error(f"🔥 Error de conexión al crear URL firmada: {str(e)}")
            raise RuntimeError(f"Error de conexión: {str(e)}")

# Global instance management with lazy initialization
_http_storage_client: Optional[SupabaseStorageHTTPClient] = None
_client_lock = threading.Lock()


def get_http_storage_client() -> SupabaseStorageHTTPClient:
    """
    Get or create the global HTTP storage client instance with proper event loop handling.
    
    Returns:
        SupabaseStorageHTTPClient: The shared client instance
    """
    global _http_storage_client
    
    # PATCH: Test mode support
    import os
    if os.getenv("PYTHON_ENV") == "test":
        # Return a mock client for tests
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        mock_client.upload_file = MagicMock(return_value={})
        mock_client.download_file = MagicMock(return_value={"content": b"test", "etag": "test123", "not_modified": False})
        mock_client.delete_file = MagicMock(return_value=True)  
        mock_client.list_files = MagicMock(return_value=[])
        mock_client.get_file_metadata = MagicMock(return_value={"exists": True, "etag": "test123"})
        mock_client.create_signed_url = MagicMock(return_value="https://example.com/signed-url")
        mock_client.download_file_with_etag_check = MagicMock(return_value=b"test")
        return mock_client
    
    # Use thread-safe lazy initialization
    with _client_lock:
        if _http_storage_client is None:
            try:
                _http_storage_client = SupabaseStorageHTTPClient()
                logger.debug("✅ HTTP storage client initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize HTTP storage client: {e}")
                raise
        return _http_storage_client


# Backward compatibility: Create a lazy property-like object
class _HTTPStorageClientProxy:
    """Proxy object that lazily creates the HTTP storage client."""
    
    def __getattr__(self, name):
        # Get the actual client and delegate the attribute access
        client = get_http_storage_client()
        return getattr(client, name)
    
    def __call__(self, *args, **kwargs):
        # Allow the proxy to be called like the class constructor
        client = get_http_storage_client()
        return client(*args, **kwargs)


# Create the proxy instance for backward compatibility
http_storage_client = _HTTPStorageClientProxy()


# Import threading for the lock
# (threading import moved to top of file)







