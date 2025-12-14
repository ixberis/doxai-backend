# -*- coding: utf-8 -*-
"""
backend/app/services/rag/converters/pdf_job_coordinator.py

Job-level coordination for PDF document processing with persistence.
Single responsibility: managing complete PDF processing jobs.

Author: Ixchel Beristáin Mendoza
Date: 28/09/2025 - Refactored from pdf_cached_page_processor.py
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Set
import logging

from .pdf_batch_processor import PDFBatchProcessor
from .pdf_processing_metrics import PDFProcessingMetricsCollector

logger = logging.getLogger(__name__)


class PDFJobCoordinator:
    """
    Coordinates complete PDF processing jobs with persistence and resumption.
    Single responsibility: job-level orchestration and state management.
    """
    
    def __init__(self):
        self.batch_processor = PDFBatchProcessor()
        self.metrics_collector = PDFProcessingMetricsCollector()
        
        # Import here to avoid circular dependencies
        from ..cache.pdf_batch_controller import PDFBatchController
        self.persistence_manager = PDFBatchController()
    
    def process_document_job(
        self,
        pdf_path: Path,
        job_id: str,
        pages_to_process: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Process a complete PDF document as a job with persistence and resumption.
        
        Args:
            pdf_path: Path to PDF file
            job_id: Unique job identifier
            pages_to_process: Specific pages to process (None for all pages)
            
        Returns:
            Complete job processing results
        """
        try:
            # Get PDF information
            total_pages = self._get_pdf_page_count(pdf_path)
            
            # Initialize or recover job state
            job_state = self.persistence_manager.initialize_job(
                job_id, total_pages, pdf_path
            )
            
            # Determine pages to process
            all_pages = set(pages_to_process or range(1, total_pages + 1))
            processed_pages = set(job_state.get('processed_pages', []))
            remaining_pages = all_pages - processed_pages
            
            logger.info(f"📋 Job {job_id}: {len(remaining_pages)} pages remaining "
                       f"({len(processed_pages)} already processed)")
            
            # Initialize metrics
            self.metrics_collector.initialize_metrics(
                total_pages, all_pages, processed_pages
            )
            
            # Process remaining pages in batches
            batch_size = 10  # Process in smaller batches for better control
            remaining_list = sorted(remaining_pages)
            
            for i in range(0, len(remaining_list), batch_size):
                batch_pages = remaining_list[i:i + batch_size]
                
                # Process batch
                batch_result = self._process_job_batch(
                    pdf_path, batch_pages, job_id
                )
                
                # Handle batch persistence
                if batch_result.get('success', False):
                    self._handle_batch_completion(job_id, batch_result)
                else:
                    logger.warning(f"⚠️ Batch processing failed for pages {batch_pages}")
            
            # Finalize job
            final_summary = self.persistence_manager.finalize_job(job_id)
            job_metrics = self.metrics_collector.get_current_metrics()
            
            # Create job result
            result = {
                'job_id': job_id,
                'pdf_path': str(pdf_path),
                'success': True,
                'total_pages': total_pages,
                'processing_metrics': job_metrics,
                'final_summary': final_summary,
                'output_files': self._get_output_file_paths(job_id),
                'summary_report': self.metrics_collector.get_summary_report(job_id, pdf_path)
            }
            
            logger.info(f"✅ Job {job_id} completed successfully")
            logger.info(f"📊 {result['summary_report']}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Job processing failed for {job_id}: {e}")
            return {
                'job_id': job_id,
                'success': False,
                'error': str(e),
                'processing_metrics': self.metrics_collector.get_current_metrics()
            }
    
    def _process_job_batch(
        self, 
        pdf_path: Path, 
        batch_pages: List[int], 
        job_id: str
    ) -> Dict[str, Any]:
        """
        Process a batch of pages within a job context.
        
        Args:
            pdf_path: Path to PDF file
            batch_pages: Pages to process in this batch
            job_id: Job identifier
            
        Returns:
            Batch processing results
        """
        logger.info(f"🔄 Processing batch: pages {batch_pages[0]}-{batch_pages[-1]} for job {job_id}")
        
        batch_result = self.batch_processor.process_pages_batch(
            pdf_path=pdf_path,
            pages=batch_pages,
            job_id=job_id
        )
        
        # Update job-level metrics
        for page_num in batch_result.get('processed_pages', []):
            self.metrics_collector.record_page_operation(page_num, "processing", success=True)
        
        for error in batch_result.get('errors', []):
            self.metrics_collector.record_page_operation(
                error['page'], "processing", success=False, error=error['error']
            )
        
        return batch_result
    
    def _handle_batch_completion(self, job_id: str, batch_result: Dict[str, Any]):
        """
        Handle completion of a batch including persistence.
        
        Args:
            job_id: Job identifier
            batch_result: Results from batch processing
        """
        # Add results to persistence manager
        for page_num in batch_result.get('processed_pages', []):
            # Mock page result for persistence - in real implementation,
            # this would contain actual page processing data
            page_data = {'page': page_num, 'status': 'completed'}
            self.persistence_manager.add_page_result(page_num, page_data)
        
        # Check if should persist batch
        if self.persistence_manager.should_persist_batch():
            if self.persistence_manager.persist_batch(job_id):
                self.metrics_collector.record_batch_persistence()
                logger.info(f"💾 Batch persisted for job {job_id}")
    
    def _get_pdf_page_count(self, pdf_path: Path) -> int:
        """
        Get the total number of pages in a PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Number of pages in PDF
        """
        try:
            import fitz
            pdf_doc = fitz.open(str(pdf_path))
            page_count = len(pdf_doc)
            pdf_doc.close()
            return page_count
        except Exception as e:
            logger.error(f"Error getting page count for {pdf_path}: {e}")
            return 0
    
    def _get_output_file_paths(self, job_id: str) -> Dict[str, str]:
        """
        Generate expected output file paths for a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Dictionary with output file paths
        """
        return {
            'markdown': f"{job_id}.md",
            'tables': f"{job_id}.tables.json", 
            'forms': f"{job_id}.forms.json"
        }
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get current status of a processing job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job status information
        """
        try:
            # This would be implemented based on persistence manager capabilities
            return {
                'job_id': job_id,
                'status': 'in_progress',  # or completed, failed, etc.
                'metrics': self.metrics_collector.get_current_metrics()
            }
        except Exception as e:
            logger.error(f"Error getting job status for {job_id}: {e}")
            return {'job_id': job_id, 'status': 'error', 'error': str(e)}






