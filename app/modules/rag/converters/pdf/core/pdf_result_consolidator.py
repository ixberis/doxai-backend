# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_result_consolidator.py

Result consolidation and merging for PDF parallel processing operations.
Single responsibility: consolidating and merging results from parallel operations.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_parallel_page_processor.py
"""

import logging
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger(__name__)


class PDFResultConsolidator:
    """
    Consolidates and merges results from parallel PDF processing operations.
    Single responsibility: result consolidation and document assembly.
    """
    
    def __init__(self):
        """Initialize result consolidator."""
        # Track consolidation statistics
        self.consolidation_stats = {
            "batches_processed": 0,
            "pages_consolidated": 0,
            "text_segments_merged": 0,
            "tables_collected": 0,
            "forms_collected": 0
        }
    
    def consolidate_batch_results(
        self,
        batch_results: Dict[int, Optional[Dict[str, Any]]],
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
        preserve_page_order: bool = True
    ) -> Dict[str, Any]:
        """
        Consolidate parallel batch results in page order.
        
        Args:
            batch_results: Dictionary mapping page_idx to results
            start_page: Starting page index (0-indexed, optional)
            end_page: Ending page index (exclusive, optional)
            preserve_page_order: Whether to preserve page ordering
            
        Returns:
            Consolidated batch results
        """
        # Backward compatibility: infer start_page and end_page if not provided
        if start_page is None or end_page is None:
            if batch_results:
                keys = sorted(batch_results.keys())
                start_page = keys[0] if start_page is None else start_page
                end_page = keys[-1] + 1 if end_page is None else end_page
            else:
                # Empty batch: use neutral range
                start_page = start_page or 1
                end_page = end_page or start_page
        
        text_parts = []
        tables = []
        forms = []
        pages_with_content = 0
        pages_failed = 0
        
        # Determine processing order
        if preserve_page_order:
            page_indices = range(start_page, end_page)
        else:
            # Process available results in any order (faster)
            page_indices = sorted(batch_results.keys())
        
        logger.debug(f"🔧 Consolidating batch results for pages {start_page}-{end_page-1}")
        
        # Process results in specified order
        for page_idx in page_indices:
            result = batch_results.get(page_idx)
            
            if result:
                # Extract text content
                page_text = result.get("text", "").strip()
                if page_text:
                    text_parts.append(page_text)
                    pages_with_content += 1
                    self.consolidation_stats["text_segments_merged"] += 1
                
                # Collect tables with page information
                page_tables = result.get("tables", [])
                for table in page_tables:
                    if isinstance(table, dict):
                        # Add page information to table
                        table_with_page = table.copy()
                        table_with_page["source_page"] = page_idx + 1  # 1-indexed for display
                        tables.append(table_with_page)
                    else:
                        tables.append(table)
                
                # Collect forms with page information
                page_forms = result.get("forms", [])
                for form in page_forms:
                    if isinstance(form, dict):
                        # Add page information to form
                        form_with_page = form.copy()
                        form_with_page["source_page"] = page_idx + 1  # 1-indexed for display
                        forms.append(form_with_page)
                    else:
                        forms.append(form)
            else:
                pages_failed += 1
                logger.debug(f"⚠️ No result for page {page_idx + 1}")
        
        # Consolidate text
        consolidated_text = self._merge_text_segments(text_parts)
        
        # Update statistics
        self.consolidation_stats["batches_processed"] += 1
        self.consolidation_stats["pages_consolidated"] += (end_page - start_page)
        self.consolidation_stats["tables_collected"] += len(tables)
        self.consolidation_stats["forms_collected"] += len(forms)
        
        # Create consolidated result
        consolidated_result = {
            "text": consolidated_text,
            "tables": tables,
            "forms": forms,
            "md_size_bytes": len(consolidated_text.encode("utf-8")),
            "no_text_extracted": len(consolidated_text) == 0,
            "pages_with_content": pages_with_content,
            "pages_failed": pages_failed,
            "page_range": f"{start_page + 1}-{end_page}"
        }
        
        logger.debug(f"✅ Batch consolidated: {pages_with_content}/{end_page - start_page} pages with content, "
                    f"{len(tables)} tables, {len(forms)} forms")
        
        return consolidated_result
    
    def consolidate_document_results(
        self,
        batch_results: List[Dict[str, Any]],
        total_pages: int,
        processing_mode: str = "parallel"
    ) -> Dict[str, Union[str, List, int, bool]]:
        """
        Consolidate results from multiple batches into final document.
        
        Args:
            batch_results: List of consolidated batch results
            total_pages: Total number of pages in document
            processing_mode: Processing mode identifier
            
        Returns:
            Final consolidated document result
        """
        logger.info(f"🔧 Consolidating {len(batch_results)} batches into final document")
        
        all_text_parts = []
        all_tables = []
        all_forms = []
        total_pages_with_content = 0
        total_pages_failed = 0
        
        # Collect all results
        for batch_result in batch_results:
            if not batch_result:
                continue
            
            # Collect text
            batch_text = batch_result.get("text", "").strip()
            if batch_text:
                all_text_parts.append(batch_text)
            
            # Collect structured data
            all_tables.extend(batch_result.get("tables", []))
            all_forms.extend(batch_result.get("forms", []))
            
            # Update page counts
            total_pages_with_content += batch_result.get("pages_with_content", 0)
            total_pages_failed += batch_result.get("pages_failed", 0)
        
        # Merge final text
        final_text = self._merge_text_segments(all_text_parts)
        
        # Calculate processing statistics
        processing_stats = {
            "total_pages": total_pages,
            "pages_processed": total_pages_with_content + total_pages_failed,
            "pages_with_content": total_pages_with_content,
            "pages_failed": total_pages_failed,
            "success_rate": (total_pages_with_content / total_pages) if total_pages > 0 else 0,
            "tables_extracted": len(all_tables),
            "forms_extracted": len(all_forms)
        }
        
        # Determine extraction status
        no_text_extracted = len(final_text) == 0
        extraction_mode = processing_mode + ("_failed" if no_text_extracted else "_optimized")
        
        # Create final result
        final_result = {
            "text": final_text,
            "tables": all_tables,
            "forms": all_forms,
            "md_size_bytes": len(final_text.encode("utf-8")),
            "no_text_extracted": no_text_extracted,
            "extraction_mode": extraction_mode,
            "processing_stats": processing_stats
        }
        
        logger.info(f"✅ Document consolidated: {len(final_text)} chars, "
                   f"{len(all_tables)} tables, {len(all_forms)} forms "
                   f"({processing_stats['success_rate']:.1%} success rate)")
        
        return final_result
    
    def _merge_text_segments(self, text_parts: List[str]) -> str:
        """
        Merge text segments with appropriate separators.
        
        Args:
            text_parts: List of text segments to merge
            
        Returns:
            Merged text string
        """
        if not text_parts:
            return ""
        
        # Filter out empty segments
        non_empty_parts = [part.strip() for part in text_parts if part.strip()]
        
        if not non_empty_parts:
            return ""
        
        # Join with double newline to separate pages/sections
        merged_text = "\n\n".join(non_empty_parts)
        
        logger.debug(f"🔧 Merged {len(non_empty_parts)} text segments into {len(merged_text)} chars")
        
        return merged_text
    
    def create_empty_result(
        self, 
        reason: str = "no_content",
        processing_mode: str = "parallel"
    ) -> Dict[str, Any]:
        """
        Create standardized empty result structure.
        
        Args:
            reason: Reason for empty result
            processing_mode: Processing mode identifier
            
        Returns:
            Empty result dictionary
        """
        return {
            "text": "",
            "tables": [],
            "forms": [],
            "md_size_bytes": 0,
            "no_text_extracted": True,
            "extraction_mode": f"{processing_mode}_{reason}",
            "processing_stats": {
                "total_pages": 0,
                "pages_processed": 0,
                "pages_with_content": 0,
                "pages_failed": 0,
                "success_rate": 0.0,
                "tables_extracted": 0,
                "forms_extracted": 0
            }
        }
    
    def validate_result_structure(self, result: Dict[str, Any]) -> bool:
        """
        Validate that result has expected structure.
        
        Args:
            result: Result dictionary to validate
            
        Returns:
            True if structure is valid
        """
        required_keys = ["text", "tables", "forms", "md_size_bytes", "no_text_extracted"]
        
        for key in required_keys:
            if key not in result:
                logger.warning(f"⚠️ Missing required key in result: {key}")
                return False
        
        # Validate data types
        if not isinstance(result["text"], str):
            logger.warning(f"⚠️ Invalid text type: {type(result['text'])}")
            return False
        
        if not isinstance(result["tables"], list):
            logger.warning(f"⚠️ Invalid tables type: {type(result['tables'])}")
            return False
        
        if not isinstance(result["forms"], list):
            logger.warning(f"⚠️ Invalid forms type: {type(result['forms'])}")
            return False
        
        return True
    
    def get_consolidation_statistics(self) -> Dict[str, int]:
        """
        Get consolidation statistics.
        
        Returns:
            Dictionary with consolidation statistics
        """
        return self.consolidation_stats.copy()
    
    def reset_statistics(self):
        """Reset consolidation statistics."""
        self.consolidation_stats = {
            "batches_processed": 0,
            "pages_consolidated": 0,
            "text_segments_merged": 0,
            "tables_collected": 0,
            "forms_collected": 0
        }
        logger.debug("📊 Consolidation statistics reset")






