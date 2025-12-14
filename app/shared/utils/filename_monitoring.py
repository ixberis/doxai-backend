# -*- coding: utf-8 -*-
"""
backend/app/utils/filename_monitoring.py

Monitoring and logging utilities for filename sanitization system (Phase 7).
Provides metrics, health checks, and monitoring capabilities.

Autor: Ixchel Beristain
Creado: 25/09/2025
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from functools import wraps
from sqlalchemy.orm import Session
from uuid import UUID

from app.modules.files.models.input_file_models import InputFile

logger = logging.getLogger(__name__)


class FilenameMetrics:
    """Metrics collector for filename sanitization system."""
    
    def __init__(self):
        self.sanitization_calls = 0
        self.sanitization_changes = 0
        self.sanitization_errors = 0
        self.consistency_checks = 0
        self.migration_fixes = 0
        self.start_time = datetime.now()
    
    def record_sanitization(self, changed: bool = False, error: bool = False):
        """Record a sanitization operation."""
        self.sanitization_calls += 1
        if changed:
            self.sanitization_changes += 1
        if error:
            self.sanitization_errors += 1
    
    def record_consistency_check(self):
        """Record a consistency check operation."""
        self.consistency_checks += 1
    
    def record_migration_fix(self, files_fixed: int):
        """Record migration fixes applied."""
        self.migration_fixes += files_fixed
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        uptime = datetime.now() - self.start_time
        
        return {
            'uptime_seconds': int(uptime.total_seconds()),
            'sanitization_calls': self.sanitization_calls,
            'sanitization_changes': self.sanitization_changes,
            'sanitization_errors': self.sanitization_errors,
            'consistency_checks': self.consistency_checks,
            'migration_fixes': self.migration_fixes,
            'change_rate': (self.sanitization_changes / max(self.sanitization_calls, 1)) * 100,
            'error_rate': (self.sanitization_errors / max(self.sanitization_calls, 1)) * 100
        }


# Global metrics instance
metrics = FilenameMetrics()


def monitor_sanitization(func):
    """Decorator to monitor sanitization operations."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        error_occurred = False
        changed = False
        
        try:
            result = func(*args, **kwargs)
            
            # Detect if sanitization changed the filename
            if hasattr(result, 'changed'):
                changed = result.changed
            elif len(args) > 0 and isinstance(result, str):
                changed = args[0] != result
            
            return result
            
        except Exception as e:
            error_occurred = True
            logger.error(f"Sanitization error in {func.__name__}: {e}")
            raise
            
        finally:
            duration = time.time() - start_time
            metrics.record_sanitization(changed=changed, error=error_occurred)
            
            logger.debug(f"Sanitization {func.__name__} completed in {duration:.3f}s, "
                        f"changed={changed}, error={error_occurred}")
    
    return wrapper


def monitor_migration(func):
    """Decorator to monitor migration operations."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            
            # Record fixes if this was a fix operation
            if isinstance(result, dict) and 'files_fixed' in result:
                metrics.record_migration_fix(result['files_fixed'])
            
            # Record consistency checks
            if 'consistency' in func.__name__ or 'check' in func.__name__:
                metrics.record_consistency_check()
            
            return result
            
        except Exception as e:
            logger.error(f"Migration error in {func.__name__}: {e}")
            raise
            
        finally:
            duration = time.time() - start_time
            logger.info(f"Migration {func.__name__} completed in {duration:.3f}s")
    
    return wrapper


def get_system_health(db: Session) -> Dict[str, Any]:
    """Get comprehensive system health status."""
    
    logger.info("Checking filename system health...")
    
    try:
        # Import here to avoid circular imports
        from app.shared.utils.migration_tools import check_filename_consistency
        
        # Basic metrics
        health_data = {
            'timestamp': datetime.now().isoformat(),
            'status': 'healthy',
            'metrics': metrics.get_summary(),
            'checks': {}
        }
        
        # Database connectivity check
        try:
            file_count = db.query(InputFile).filter(
                InputFile.input_file_is_active.is_(True)
            ).count()
            health_data['checks']['database'] = {
                'status': 'ok',
                'active_files': file_count
            }
        except Exception as e:
            health_data['checks']['database'] = {
                'status': 'error',
                'error': str(e)
            }
            health_data['status'] = 'degraded'
        
        # Consistency check (light version)
        try:
            consistency = check_filename_consistency(db)
            consistency_percentage = consistency.get('consistency_percentage', 0)
            
            health_data['checks']['consistency'] = {
                'status': 'ok' if consistency_percentage >= 95 else 'warning' if consistency_percentage >= 80 else 'error',
                'percentage': consistency_percentage,
                'total_files': consistency.get('total_files', 0),
                'inconsistent_files': consistency.get('inconsistent_files', 0)
            }
            
            if consistency_percentage < 95:
                health_data['status'] = 'warning' if health_data['status'] == 'healthy' else health_data['status']
            
        except Exception as e:
            health_data['checks']['consistency'] = {
                'status': 'error',
                'error': str(e)
            }
            health_data['status'] = 'degraded'
        
        # Performance check
        recent_calls = metrics.sanitization_calls
        if recent_calls > 0:
            error_rate = metrics.sanitization_errors / recent_calls
            if error_rate > 0.05:  # 5% error rate threshold
                health_data['status'] = 'warning'
                health_data['checks']['performance'] = {
                    'status': 'warning',
                    'high_error_rate': error_rate
                }
            else:
                health_data['checks']['performance'] = {'status': 'ok'}
        
        logger.info(f"System health check completed: {health_data['status']}")
        return health_data
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'timestamp': datetime.now().isoformat(),
            'status': 'error',
            'error': str(e),
            'metrics': metrics.get_summary()
        }


def log_sanitization_event(
    operation: str, 
    filename: str, 
    result: str, 
    changed: bool, 
    duration: float = None,
    project_id: UUID = None
):
    """Log detailed sanitization events."""
    
    log_data = {
        'operation': operation,
        'original_filename': filename,
        'sanitized_filename': result,
        'changed': changed,
        'timestamp': datetime.now().isoformat()
    }
    
    if duration is not None:
        log_data['duration_ms'] = round(duration * 1000, 2)
    
    if project_id:
        log_data['project_id'] = str(project_id)
    
    if changed:
        logger.info(f"Filename sanitized: '{filename}' -> '{result}'", extra=log_data)
    else:
        logger.debug(f"Filename unchanged: '{filename}'", extra=log_data)


def generate_daily_report(db: Session, date: datetime = None) -> Dict[str, Any]:
    """Generate daily system report."""
    
    if date is None:
        date = datetime.now()
    
    logger.info(f"Generating daily report for {date.date()}")
    
    try:
        # Import here to avoid circular imports
        from app.shared.utils.migration_tools import check_filename_consistency
        
        # Basic stats
        report = {
            'date': date.date().isoformat(),
            'generated_at': datetime.now().isoformat(),
            'system_metrics': metrics.get_summary()
        }
        
        # Consistency status
        try:
            consistency = check_filename_consistency(db)
            report['consistency'] = {
                'total_files': consistency.get('total_files', 0),
                'consistent_files': consistency.get('consistent_files', 0),
                'inconsistent_files': consistency.get('inconsistent_files', 0),
                'percentage': consistency.get('consistency_percentage', 0)
            }
        except Exception as e:
            report['consistency'] = {'error': str(e)}
        
        # Recent activity (if available)
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        try:
            daily_uploads = db.query(InputFile).filter(
                InputFile.input_file_uploaded_at >= start_of_day,
                InputFile.input_file_uploaded_at < end_of_day,
                InputFile.input_file_is_active.is_(True)
            ).count()
            
            report['daily_activity'] = {
                'new_uploads': daily_uploads
            }
        except Exception as e:
            report['daily_activity'] = {'error': str(e)}
        
        # Health status
        report['health'] = get_system_health(db)
        
        logger.info(f"Daily report generated successfully")
        return report
        
    except Exception as e:
        logger.error(f"Failed to generate daily report: {e}")
        return {
            'date': date.date().isoformat(),
            'generated_at': datetime.now().isoformat(),
            'error': str(e),
            'system_metrics': metrics.get_summary()
        }


def alert_on_consistency_issues(db: Session, threshold: float = 90.0):
    """Check consistency and alert if below threshold."""
    
    try:
        # Import here to avoid circular imports
        from app.shared.utils.migration_tools import check_filename_consistency
        
        consistency = check_filename_consistency(db)
        percentage = consistency.get('consistency_percentage', 100)
        
        if percentage < threshold:
            inconsistent_count = consistency.get('inconsistent_files', 0)
            total_files = consistency.get('total_files', 0)
            
            logger.warning(
                f"ALERT: Filename consistency below threshold! "
                f"{percentage:.1f}% consistent ({inconsistent_count}/{total_files} files need attention)"
            )
            
            # Log details of inconsistent files
            for detail in consistency.get('inconsistent_details', [])[:5]:  # Log first 5
                logger.warning(
                    f"Inconsistent file: {detail.get('file_id')} - "
                    f"'{detail.get('stored_name')}' should be '{detail.get('expected_sanitized')}'"
                )
            
            return {
                'alert_triggered': True,
                'consistency_percentage': percentage,
                'inconsistent_files': inconsistent_count,
                'total_files': total_files
            }
        else:
            logger.info(f"Consistency check passed: {percentage:.1f}%")
            return {
                'alert_triggered': False,
                'consistency_percentage': percentage
            }
            
    except Exception as e:
        logger.error(f"Consistency alert check failed: {e}")
        return {
            'alert_triggered': True,
            'error': str(e)
        }


# Export monitoring utilities
__all__ = [
    'FilenameMetrics',
    'metrics',
    'monitor_sanitization',
    'monitor_migration',
    'get_system_health',
    'log_sanitization_event',
    'generate_daily_report',
    'alert_on_consistency_issues'
]






