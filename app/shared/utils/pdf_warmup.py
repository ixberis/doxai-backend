# -*- coding: utf-8 -*-
"""
backend/app/utils/pdf_warmup.py

Utilidades específicas para warm-up de procesadores PDF.
"""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def create_minimal_test_pdf(output_path: Path) -> bool:
    """
    Crea un PDF mínimo para warm-up si no existe.
    Útil para casos donde el asset no esté disponible.
    """
    try:
        if output_path.exists():
            return True
        
        # Contenido PDF mínimo válido
        pdf_content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj
4 0 obj<</Length 88>>stream
BT
/F1 12 Tf
100 700 Td
(Documento de prueba para precarga) Tj
0 -15 Td
(Sistema de análisis DoxAI) Tj
0 -15 Td
(Texto en español para warm-up) Tj
ET
endstream endobj
xref
0 5
0000000000 65535 f 
0000000010 00000 n 
0000000053 00000 n 
0000000100 00000 n 
0000000178 00000 n 
trailer<</Size 5/Root 1 0 R>>
startxref
315
%%EOF"""
        
        # Crear directorio si no existe
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Escribir archivo
        with open(output_path, 'wb') as f:
            f.write(pdf_content)
        
        logger.info(f"✅ PDF de warm-up creado: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creando PDF de warm-up: {e}")
        return False

def validate_pdf_asset(asset_path: Path) -> bool:
    """
    Valida que el asset PDF de warm-up sea válido.
    """
    if not asset_path.exists():
        logger.warning(f"⚠️ Asset PDF no encontrado: {asset_path}")
        return False
    
    try:
        # Verificar que el archivo tenga contenido PDF básico
        with open(asset_path, 'rb') as f:
            content = f.read(100)  # Leer primeros 100 bytes
            if not content.startswith(b'%PDF-'):
                logger.warning(f"⚠️ Asset no parece ser un PDF válido: {asset_path}")
                return False
        
        file_size = asset_path.stat().st_size
        if file_size < 100:  # PDF muy pequeño, probablemente corrupto
            logger.warning(f"⚠️ Asset PDF muy pequeño ({file_size} bytes): {asset_path}")
            return False
        
        logger.debug(f"✅ Asset PDF válido: {asset_path} ({file_size} bytes)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error validando asset PDF: {e}")
        return False






