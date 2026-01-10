# -*- coding: utf-8 -*-
"""
backend/app/shared/config/settings_base.py

Base de configuración (Pydantic v2) para DoxAI.
- Esta clase NO instancia singletons ni resuelve .env; eso lo hace config_loader.
- Es la base para settings_dev.py, settings_test.py y settings_prod.py.

Autor: Ixchel Beristain
Fecha: 24/10/2025
"""

from typing import Literal, Optional, Any
from pydantic import Field, HttpUrl, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Tipos de entorno soportados
EnvName = Literal["development", "test", "production"]


class BaseAppSettings(BaseSettings):
    # =========================
    # Núcleo de la aplicación
    # =========================
    python_env: EnvName = Field(default="development", validation_alias="PYTHON_ENV")
    app_name: str = Field(default="DoxAI", validation_alias="APP_NAME")
    app_version: str = Field(default="0.1.0", validation_alias="APP_VERSION")
    app_host: str = Field(default="0.0.0.0", validation_alias="APP_HOST")
    app_port: int = Field(default=8000, validation_alias="APP_PORT")
    debug: bool = Field(default=False, validation_alias="DEBUG")

    # =========================
    # Base de datos (PostgreSQL)
    # =========================
    db_user: str = Field(default="postgres", validation_alias="DB_USER")
    db_password: SecretStr = Field(default=SecretStr("postgres"), validation_alias="DB_PASSWORD")
    db_host: str = Field(default="localhost", validation_alias="DB_HOST")
    db_port: int = Field(default=5432, validation_alias="DB_PORT")
    db_name: str = Field(default="doxai", validation_alias="DB_NAME")
    db_pool_size: int = Field(default=5, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=5, validation_alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=5, validation_alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=1800, validation_alias="DB_POOL_RECYCLE")
    db_pool_pre_ping: bool = Field(default=True, validation_alias="DB_POOL_PRE_PING")
    db_echo_sql: bool = Field(default=False, validation_alias="DB_ECHO_SQL")
    db_sslmode: str = Field(default="prefer", validation_alias="DB_SSLMODE")  # prefer|require|disable
    db_url: Optional[str] = Field(default=None, validation_alias="DB_URL")

    @computed_field  # type: ignore[misc]
    @property
    def database_url(self) -> str:
        """
        Genera la URL de conexión completa para SQLAlchemy + asyncpg.
        Prioriza DB_URL si existe, sino construye desde componentes individuales.
        """
        from urllib.parse import quote_plus

        # Si se provee DB_URL completa, úsala (normaliza el esquema)
        if self.db_url:
            url = self.db_url
            url = (
                url.replace("postgres://", "postgresql+asyncpg://")
                   .replace("postgresql://", "postgresql+asyncpg://")
            )
            if "sslmode=" not in url and self.db_sslmode:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}sslmode={self.db_sslmode}"
            return url

        # Construye desde componentes (con password escapado)
        pw = quote_plus(self.db_password.get_secret_value())
        return (
            f"postgresql+asyncpg://{self.db_user}:{pw}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?sslmode={self.db_sslmode}"
        )

    # =========================
    # Redis / Cache (opcional)
    # =========================
    redis_url: Optional[str] = Field(default=None, validation_alias="REDIS_URL")

    # =========================
    # HTTP Metrics (observabilidad)
    # =========================
    http_metrics_enabled: bool = Field(default=True, validation_alias="HTTP_METRICS_ENABLED")
    http_metrics_single_instance_warning: bool = Field(
        default=True, 
        validation_alias="HTTP_METRICS_SINGLE_INSTANCE_WARNING",
        description="Log warning on startup if HTTP metrics are enabled without Redis (best-effort mode)"
    )

    # =========================
    # Supabase
    # =========================
    supabase_url: Optional[HttpUrl] = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_service_role_key: Optional[str] = Field(default=None, validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_bucket_name: str = Field(default="users-files", validation_alias="SUPABASE_BUCKET_NAME")

    # =========================
    # CORS / Frontend
    # =========================
    allowed_origins: str = Field(default="*", validation_alias="CORS_ORIGINS")
    frontend_url: str = Field(default="http://localhost:8080", validation_alias="FRONTEND_URL")
    frontend_base_url: Optional[str] = Field(default=None, validation_alias="FRONTEND_BASE_URL")

    # =========================
    # Auth / JWT / Recaptcha
    # =========================
    jwt_secret_key: SecretStr = Field(default=SecretStr("please-change-me"), validation_alias="JWT_SECRET_KEY")
    jwt_algorithm: Literal["HS256", "RS256"] = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_minutes: int = Field(default=1440, validation_alias="REFRESH_TOKEN_EXPIRE_MINUTES")
    activation_token_expire_minutes: int = Field(default=60, validation_alias="ACTIVATION_TOKEN_EXPIRE_MINUTES")
    recaptcha_enabled: bool = Field(default=False, validation_alias="RECAPTCHA_ENABLED")
    recaptcha_secret: Optional[SecretStr] = Field(default=None, validation_alias="RECAPTCHA_SECRET")
    recaptcha_timeout_sec: int = Field(default=8, validation_alias="RECAPTCHA_TIMEOUT_SEC")

    # Rate limiting para login
    login_attempts_limit: int = Field(default=5, validation_alias="LOGIN_ATTEMPTS_LIMIT")
    login_attempts_time_window_minutes: int = Field(default=15, validation_alias="LOGIN_ATTEMPTS_TIME_WINDOW_MINUTES")
    login_lockout_duration_minutes: int = Field(default=30, validation_alias="LOGIN_LOCKOUT_DURATION_MINUTES")

    # =========================
    # Pasarelas de pago (Stripe & PayPal) — sin suscripciones
    # =========================
    enable_paypal: bool = Field(default=True, validation_alias="ENABLE_PAYPAL")
    enable_stripe: bool = Field(default=False, validation_alias="ENABLE_STRIPE")
    payments_default: Literal["stripe", "paypal"] = Field(default="paypal", validation_alias="PAYMENTS_DEFAULT")

    # Stripe
    stripe_public_key: Optional[str] = Field(default=None, validation_alias="STRIPE_PUBLIC_KEY")
    stripe_secret_key: Optional[SecretStr] = Field(default=None, validation_alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: Optional[SecretStr] = Field(default=None, validation_alias="STRIPE_WEBHOOK_SECRET")
    stripe_mode: Literal["test", "live"] = Field(default="test", validation_alias="STRIPE_MODE")
    stripe_account_id: Optional[str] = Field(default=None, validation_alias="STRIPE_ACCOUNT_ID")

    # PayPal
    paypal_client_id: Optional[str] = Field(default=None, validation_alias="PAYPAL_CLIENT_ID")
    paypal_client_secret: Optional[SecretStr] = Field(default=None, validation_alias="PAYPAL_CLIENT_SECRET")
    paypal_env: Literal["sandbox", "live"] = Field(default="sandbox", validation_alias="PAYPAL_ENV")
    paypal_webhook_id: Optional[str] = Field(default=None, validation_alias="PAYPAL_WEBHOOK_ID")

    # =========================
    # Email
    # =========================
    email_mode: Literal["console", "smtp", "api"] = Field(default="console", validation_alias="EMAIL_MODE")
    email_provider: Literal["smtp", "mailersend", ""] = Field(default="", validation_alias="EMAIL_PROVIDER")
    email_timeout_sec: int = Field(default=30, validation_alias="EMAIL_TIMEOUT_SEC")

    # SMTP (solo aplica si email_mode == "smtp")
    smtp_server: Optional[str] = Field(default=None, validation_alias="EMAIL_SERVER")
    smtp_port: int = Field(default=465, validation_alias="EMAIL_PORT")
    smtp_username: Optional[str] = Field(default=None, validation_alias="EMAIL_USERNAME")
    smtp_password: Optional[SecretStr] = Field(default=None, validation_alias="EMAIL_PASSWORD")
    email_use_ssl: bool = Field(default=True, validation_alias="EMAIL_USE_SSL")

    # From / plantillas
    email_from: str = Field(default="no-reply@doxai.site", validation_alias="EMAIL_FROM")
    email_service: str = Field(default="doxai", validation_alias="EMAIL_SERVICE")
    admin_notification_email: str = Field(default="doxai@doxai.site", validation_alias="ADMIN_NOTIFY_EMAIL")
    support_email: str = Field(default="soporte@doxai.site", validation_alias="SUPPORT_EMAIL")
    email_templates_dir: Optional[str] = Field(default=None, validation_alias="EMAIL_TEMPLATES_DIR")

    # MailerSend API (solo aplica si email_mode == "api")
    mailersend_api_key: Optional[SecretStr] = Field(default=None, validation_alias="MAILERSEND_API_KEY")
    mailersend_from_email: Optional[str] = Field(default=None, validation_alias="MAILERSEND_FROM_EMAIL")
    mailersend_from_name: Optional[str] = Field(default="DoxAI", validation_alias="MAILERSEND_FROM_NAME")

    # =========================
    # Internal Service Auth
    # =========================
    internal_service_token: Optional[SecretStr] = Field(default=None, validation_alias="APP_SERVICE_TOKEN")
    internal_api_url: Optional[str] = Field(default=None, validation_alias="APP_INTERNAL_API_URL")

    # =========================
    # OpenAI / RAG (clave)
    # =========================
    openai_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="OPENAI_API_KEY")

    # =========================
    # Archivos y límites
    # =========================
    allowed_file_types: Any = Field(
        default_factory=lambda: ["pdf", "docx", "doc", "odt", "xlsx", "xls", "ods", "csv", "pptx", "ppt", "odp", "txt"],
        validation_alias="ALLOWED_FILE_TYPES",
    )
    max_file_size_mb: int = Field(default=100, validation_alias="MAX_FILE_SIZE_MB")

    # Paginación / créditos / reservas (migrados desde constants.py)
    page_size_default: int = Field(20, validation_alias="DEFAULT_PAGE_SIZE")
    page_size_max: int = Field(100, validation_alias="MAX_PAGE_SIZE")
    reservation_expiry_minutes: int = Field(30, validation_alias="DEFAULT_RESERVATION_EXPIRY_MINUTES")
    freemium_credits: int = Field(100, validation_alias="DEFAULT_FREEMIUM_CREDITS")
    credits_per_page: int = Field(1, validation_alias="CREDITS_PER_PAGE")
    credits_per_document: int = Field(10, validation_alias="CREDITS_PER_DOCUMENT")

    # =========================
    # Observabilidad / Logging
    # =========================
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: Literal["json", "pretty", "plain"] = Field(default="pretty", validation_alias="LOG_FORMAT")
    log_emoji: bool = Field(default=True, validation_alias="LOG_EMOJI")
    sentry_dsn: Optional[HttpUrl] = Field(default=None, validation_alias="SENTRY_DSN")

    # =========================
    # Warm-up flags (usados por shared/core)
    # =========================
    warmup_enable: bool = Field(default=True, validation_alias="WARMUP_ENABLE")
    warmup_preload_fast: bool = Field(default=True, validation_alias="WARMUP_PRELOAD_FAST")
    warmup_preload_hires: bool = Field(default=False, validation_alias="WARMUP_PRELOAD_HIRES")
    warmup_preload_table_model: bool = Field(default=False, validation_alias="WARMUP_PRELOAD_TABLE_MODEL")
    warmup_http_client: bool = Field(default=True, validation_alias="WARMUP_HTTP_CLIENT")
    warmup_http_health_check: bool = Field(default=False, validation_alias="WARMUP_HTTP_HEALTH_CHECK")
    warmup_http_health_url: str = Field(default="https://httpbin.org/status/200", validation_alias="WARMUP_HTTP_HEALTH_URL")
    warmup_http_health_warn_ms: float = Field(default=1000.0, validation_alias="WARMUP_HTTP_HEALTH_WARN_MS")
    warmup_http_health_timeout_sec: float = Field(default=5.0, validation_alias="WARMUP_HTTP_HEALTH_TIMEOUT_SEC")
    warmup_timeout_sec: int = Field(default=30, validation_alias="WARMUP_TIMEOUT_SEC")
    warmup_silence_pdfminer: bool = Field(default=True, validation_alias="WARMUP_SILENCE_PDFMINER")

    # =========================
    # Cliente HTTP global
    # =========================
    http_base_url: Optional[str] = Field(default=None, validation_alias="HTTP_BASE_URL")
    http_proxy: Optional[str] = Field(default=None, validation_alias="HTTP_PROXY")
    http_no_proxy: Optional[str] = Field(default=None, validation_alias="NO_PROXY")
    http_extra_headers: dict[str, str] = Field(default_factory=dict, validation_alias="HTTP_EXTRA_HEADERS")

    # ===== Helpers de entorno =====
    @computed_field  # type: ignore[misc]
    @property
    def is_dev(self) -> bool:
        return self.python_env == "development"

    @computed_field  # type: ignore[misc]
    @property
    def is_test(self) -> bool:
        return self.python_env == "test"

    @computed_field  # type: ignore[misc]
    @property
    def is_prod(self) -> bool:
        return self.python_env == "production"

    # ===== Propiedades de compatibilidad para código legacy =====
    @computed_field  # type: ignore[misc]
    @property
    def jwt_secret(self) -> str:
        """Alias de compatibilidad: jwt_secret_key -> jwt_secret"""
        return self.jwt_secret_key.get_secret_value()

    @computed_field  # type: ignore[misc]
    @property
    def RECAPTCHA_ENABLED(self) -> bool:
        """Alias de compatibilidad: recaptcha_enabled -> RECAPTCHA_ENABLED"""
        return self.recaptcha_enabled

    @computed_field  # type: ignore[misc]
    @property
    def recaptcha_secret_key(self) -> str:
        """Alias de compatibilidad: recaptcha_secret -> recaptcha_secret_key"""
        if self.recaptcha_secret:
            return self.recaptcha_secret.get_secret_value()
        return ""

    # ===== Normalizador de tipos para allowed_file_types =====
    @field_validator("allowed_file_types", mode="before")
    @classmethod
    def _normalize_allowed_file_types(cls, v):
        if isinstance(v, list):
            return v
        if v is None or (isinstance(v, str) and v.strip() in ("", "[]")):
            return ["pdf", "docx", "doc", "odt", "xlsx", "xls", "ods", "csv", "pptx", "ppt", "odp", "txt"]
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("[") and s.endswith("]"):
                import json
                try:
                    return json.loads(s)
                except Exception:
                    return ["pdf", "docx", "doc", "odt", "xlsx", "xls", "ods", "csv", "pptx", "ppt", "odp", "txt"]
            return [x.strip() for x in s.split(",") if x.strip()]
        return v

    # ===== Utilidad para normalizar CORS =====
    def get_cors_origins(self) -> list[str]:
        """Convierte allowed_origins en lista procesable para CORS middleware."""
        if not self.allowed_origins or self.allowed_origins == "*":
            return ["*"]
        # Parsea lista separada por comas, limpia comillas
        return [o.strip().strip('"').strip("'") for o in self.allowed_origins.split(",") if o.strip()]

    @computed_field  # type: ignore[misc]
    @property
    def _payments_enabled(self) -> bool:
        return self.enable_paypal or self.enable_stripe

    def _security_and_payments_checks(self) -> None:
        """
        Validaciones mínimas de seguridad y coherencia.
        Se invoca desde config_loader tras instanciar el settings.
        """
        import logging
        logger = logging.getLogger(__name__)

        # JWT en prod: debe ser fuerte
        if self.is_prod:
            jwt_key = self.jwt_secret_key.get_secret_value()
            if not jwt_key or jwt_key == "please-change-me" or len(jwt_key) < 32:
                raise ValueError("JWT_SECRET_KEY debe tener ≥32 caracteres en producción")

            # SSL requerido en prod
            if self.db_sslmode != "require":
                raise ValueError("DB_SSLMODE debe ser 'require' en producción")
            if not self.openai_api_key.get_secret_value():
                raise ValueError("OPENAI_API_KEY es requerido en producción")

        # Validaciones suaves para desarrollo
        if self.is_dev:
            jwt_key = self.jwt_secret_key.get_secret_value()
            if not jwt_key or jwt_key == "please-change-me" or len(jwt_key) < 32:
                logger.info("ℹ️ JWT_SECRET_KEY es débil o usa valor por defecto - considera usar una clave más segura en desarrollo")

            openai_key = self.openai_api_key.get_secret_value()
            if not openai_key or openai_key == "":
                logger.info("ℹ️ OPENAI_API_KEY está vacío - funcionalidades RAG/IA no estarán disponibles")

        # Pasarelas: al menos una habilitada
        if not self._payments_enabled:
            raise ValueError("Debes habilitar al menos un gateway de pagos (ENABLE_PAYPAL/ENABLE_STRIPE).")

        # Coherencia entre default y habilitación
        if self.payments_default == "paypal" and not self.enable_paypal:
            raise ValueError("PAYMENTS_DEFAULT=paypal pero ENABLE_PAYPAL=false.")
        if self.payments_default == "stripe" and not self.enable_stripe:
            raise ValueError("PAYMENTS_DEFAULT=stripe pero ENABLE_STRIPE=false.")

        # En producción, ambos gateways deben estar en modo live
        if self.enable_paypal and self.is_prod and self.paypal_env != "live":
            raise ValueError("En producción, PayPal debe usar PAYPAL_ENV=live.")
        if self.enable_stripe and self.is_prod and self.stripe_mode != "live":
            raise ValueError("En producción, Stripe debe usar STRIPE_MODE=live.")

        # ✅ Validación mínima para email, según modo (evita deploys "a medias")
        if self.email_mode == "smtp":
            if not self.smtp_server or not self.smtp_username or not self.smtp_password:
                raise ValueError("EMAIL_MODE=smtp requiere EMAIL_SERVER, EMAIL_USERNAME y EMAIL_PASSWORD.")
        if self.email_mode == "api":
            if not self.mailersend_api_key or not self.mailersend_from_email:
                raise ValueError("EMAIL_MODE=api requiere MAILERSEND_API_KEY y MAILERSEND_FROM_EMAIL.")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


__all__ = ["BaseAppSettings", "EnvName"]
# Fin del archivo backend\app\shared\config\settings_base.py
