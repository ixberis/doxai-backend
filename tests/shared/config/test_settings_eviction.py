# -*- coding: utf-8 -*-
import os
from app.shared.config.settings_eviction import CacheEvictionSettings

def test_eviction_defaults_sane():
    s = CacheEvictionSettings()
    assert s.pages_bucket == "rag-cache-pages"
    assert s.jobs_bucket == "rag-cache-jobs"
    assert 3600 <= s.ttl_ocr_results <= 7776000
    assert 3600 <= s.ttl_jobs <= 604800
    assert s.enabled is True

def test_env_prefix_mapping(monkeypatch):
    monkeypatch.setenv("CACHE_EVICTION_PAGES_BUCKET", "my-pages")
    monkeypatch.setenv("CACHE_EVICTION_PAGES_PREFIX", "tenant_a/")
    monkeypatch.setenv("CACHE_EVICTION_ENABLED", "false")
    s = CacheEvictionSettings()
    assert s.pages_bucket == "my-pages"
    assert s.pages_prefix == "tenant_a/"
    assert s.enabled is False
# Fin del archivo backend/tests/shared/config/test_settings_eviction.py