"""
Lab Playwright Kit — базовая библиотека браузерной автоматизации.
Лаборатория DoctorM&Ai.
"""

from .account_manager import Account, AccountManager, AccountStatus, Platform
from .action_engine import ActionEngine, ActionResult, ActionStep, ActionType
from .aria_snapshot import ARIASnapshot
from .browser import BrowserManager
from .captcha_solver import CaptchaResult, CaptchaSolver, CaptchaType, SolverProvider
from .clock import ClockController

# v2.0 — Next Level
from .fingerprint_auditor import (
    FingerprintAuditor,
    FingerprintIssue,
    FingerprintReport,
    Severity,
)
from .warmup_orchestrator import (
    PHASE_ACTIONS,
    PHASE_CONFIG,
    WarmupAction,
    WarmupOrchestrator,
    WarmupPhase,
    WarmupResult,
    WarmupState,
)
from .stealth_score import (
    RiskLevel,
    StealthCheck,
    StealthScoreResult,
    StealthScorer,
)
from .fingerprint import BrowserFingerprint, FingerprintManager
from .har_recorder import HARRecorder, HARStats
from .human_behavior import BEHAVIOR_PROFILES, BehaviorProfile, HumanBehaviorEngine
from .network import NetworkInterceptor
from .parser import PageParser
from .proxy_rotation import ProxyInfo, ProxyProtocol, ProxyRotator, RotationStrategy
from .screencast import ScreencastRecorder
from .screenshot import ScreenshotMaker
from .session_manager import SessionData, SessionManager
from .stealth import StealthConfig
from .stealth_audio import AudioConfig, AudioSpoofer, apply_audio_spoofing
from .stealth_benchmark import BenchmarkResult, StealthBenchmark, run_benchmark
from .stealth_client_hints import ClientHintsConfig, ClientHintsSpoofer, apply_client_hints
from .stealth_webrtc import WebRTCConfig, WebRTCProtector, apply_webrtc_protection
from .stealth_pipeline import (
    PipelineResult,
    StealthPipeline,
    apply_stealth_advanced,
    apply_stealth_full,
)
from .task_orchestrator import (
    DEFAULT_RATE_LIMITS,
    RateLimit,
    Task,
    TaskOrchestrator,
    TaskPriority,
    TaskStatus,
)
from .vpn_proxy import VPNProxy, VPNProxyManager
from .geo_check import GeoChecker, GeoResult, GeoCheckReport
from .health_monitor import HealthMonitor, HealthCheck, HealthReport, HealthStatus
from .task_template import (
    AuthTask,
    BaseTask,
    ContentPublishTask,
    CrossPostTask,
    DataCollectionTask,
    MonitoringTask,
    SocialMediaTask,
    TaskContext,
    TaskStep,
)
from .hype_client import (
    CrossPostReport,
    CrossPostResult,
    HypeClient,
    check_api,
    quick_crosspost,
)
from .telegraph_publisher import (
    TelegraphPublisher,
    TelegraphPage,
    TelegraphError,
    PublishResult,
    AccountInfo,
    quick_publish,
    create_telegraph_account,
)
from .site_health_monitor import (
    SiteConfig,
    SiteCheckResult,
    HealthReport as SiteHealthReport,
    SiteHealthMonitor,
    run_check,
)
from .vpn_monitor import (
    VPNServer,
    SiteCheck,
    VPNCheckResult,
    VPNMonitorReport,
    VPNMonitor,
    run_check as run_vpn_check,
)
from .browser_auth import (
    AUTH_PRESETS,
    HABR_AUTH_PRESET,
    VCRU_AUTH_PRESET,
    TWITTER_AUTH_PRESET,
    TELEGRAM_AUTH_PRESET,
    AuthPreset,
    AuthResult,
    AuthResultStatus,
    BrowserAuthManager,
)
from .saas_api import (
    AppState,
    Auth2FARequest,
    AuthCheckRequest,
    AuthLoginRequest,
    AuthResponse,
    BatchParseRequest,
    HealthResponse,
    NicheInfo,
    ParseRequest,
    StatusResponse,
    create_app,
    OSINTSearchRequest,
    OSINTSearchResponse,
    OSINTAccountResponse,
    OSINTPlatformsResponse,
    OSINTPlatformInfo,
)
from .platform_registry import (
    CheckType,
    PlatformProfile,
    PlatformRegistry,
)
from .account_finder import (
    AccountFinder,
    FoundAccount,
    SearchReport,
    UsernamePermuter,
)
from .cloudflare_bypass import (
    BypassResult,
    CloudflareBypass,
    FlareSolverrClient,
)
from .profile_analyzer import (
    ProfileAnalysis,
    ProfileAnalyzer,
    ProfileData,
)
from .osint_bot import (
    create_bot,
    main as run_bot,
)
from .price_parser import (
    PriceParser,
    PriceReport,
    PriceItem,
    CMDParser,
    InvitroParser,
    KDLParser,
)
from .data_parser import (
    BatchParser,
    DataParser,
    FieldMapping,
    NicheSchema,
    NicheType,
    ParseResult,
    SCHEMA_REGISTRY,
    detect_niche,
    export_to_csv,
    export_to_json,
    get_schema,
)
# Aliases
NicheProfile = NicheType


__version__ = "2.1.0"

__all__ = [
    # Core
    "BrowserManager",
    "StealthConfig",
    "PageParser",
    "ScreenshotMaker",
    "NetworkInterceptor",
    # New Capabilities
    "ScreencastRecorder",
    "ARIASnapshot",
    "ClockController",
    # Stealth Advanced
    "WebRTCConfig",
    "WebRTCProtector",
    "AudioConfig",
    "AudioSpoofer",
    "ClientHintsConfig",
    "ClientHintsSpoofer",
    "StealthBenchmark",
    "BenchmarkResult",
    "run_benchmark",
    "apply_webrtc_protection",
    "apply_audio_spoofing",
    "apply_client_hints",
    # Stealth Pipeline (unified facade)
    "StealthPipeline",
    "PipelineResult",
    "apply_stealth_full",
    "apply_stealth_advanced",
    # Infrastructure
    "ProxyRotator",
    "ProxyInfo",
    "ProxyProtocol",
    "RotationStrategy",
    "SessionManager",
    "SessionData",
    "HARRecorder",
    "HARStats",
    # v2.0 — Next Level
    "FingerprintManager",
    "BrowserFingerprint",
    "HumanBehaviorEngine",
    "BehaviorProfile",
    "BEHAVIOR_PROFILES",
    "CaptchaSolver",
    "CaptchaResult",
    "CaptchaType",
    "SolverProvider",
    "AccountManager",
    "Account",
    "AccountStatus",
    "Platform",
    "ActionEngine",
    "ActionType",
    "ActionResult",
    "ActionStep",
    "TaskOrchestrator",
    "Task",
    "TaskPriority",
    "TaskStatus",
    "RateLimit",
    "DEFAULT_RATE_LIMITS",
    # VPN Proxy
    "VPNProxy",
    "VPNProxyManager",
    # Data Parser
    "DataParser",
    "BatchParser",
    "ParseResult",
    "NicheType",
    "NicheSchema",
    "NicheProfile",
    "FieldMapping",
    "get_schema",
    "detect_niche",
    "export_to_csv",
    "export_to_json",
    "SCHEMA_REGISTRY",
    # Task Templates
    "BaseTask",
    "TaskContext",
    "TaskStep",
    "SocialMediaTask",
    "ContentPublishTask",
    "DataCollectionTask",
    "AuthTask",
    "MonitoringTask",
    "CrossPostTask",
    # SaaS API
    "create_app",
    "AppState",
    "ParseRequest",
    "BatchParseRequest",
    "AuthLoginRequest",
    "AuthCheckRequest",
    "Auth2FARequest",
    "AuthResponse",
    "NicheInfo",
    "HealthResponse",
    "StatusResponse",
    # OSINT API
    "OSINTSearchRequest",
    "OSINTSearchResponse",
    "OSINTAccountResponse",
    "OSINTPlatformsResponse",
    "OSINTPlatformInfo",
    # Hype Pilot Client
    "HypeClient",
    "CrossPostReport",
    "CrossPostResult",
    "quick_crosspost",
    "check_api",
    # Telegraph Publisher
    "TelegraphPublisher",
    "TelegraphPage",
    "TelegraphError",
    "PublishResult",
    "AccountInfo",
    "quick_publish",
    "create_telegraph_account",
    # Site Health Monitor
    "SiteConfig",
    "SiteCheckResult",
    "SiteHealthReport",
    "SiteHealthMonitor",
    "run_check",
    # VPN Monitor
    "VPNServer",
    "SiteCheck",
    "VPNCheckResult",
    "VPNMonitorReport",
    "VPNMonitor",
    "run_vpn_check",
    # Browser Auth
    "BrowserAuthManager",
    "AuthResult",
    "AuthResultStatus",
    "AuthPreset",
    "AUTH_PRESETS",
    "HABR_AUTH_PRESET",
    "VCRU_AUTH_PRESET",
    "TWITTER_AUTH_PRESET",
    "TELEGRAM_AUTH_PRESET",
    # Platform Registry (Maigret-inspired)
    "PlatformRegistry",
    "PlatformProfile",
    "CheckType",
    # Account Finder (recursive search)
    "AccountFinder",
    "FoundAccount",
    "SearchReport",
    "UsernamePermuter",
    # Cloudflare Bypass
    "CloudflareBypass",
    "FlareSolverrClient",
    "BypassResult",
    # Profile Analyzer (AI)
    "ProfileAnalyzer",
    "ProfileAnalysis",
    "ProfileData",
    # OSINT Bot
    "create_bot",
    "run_bot",
    # Price Parser
    "PriceParser",
    "PriceReport",
    "PriceItem",
    "CMDParser",
    "InvitroParser",
    "KDLParser",
    # Evolution — Fingerprint Auditor
    "FingerprintAuditor",
    "FingerprintIssue",
    "FingerprintReport",
    "Severity",
    # Evolution — Warmup Orchestrator
    "WarmupOrchestrator",
    "WarmupPhase",
    "WarmupAction",
    "WarmupState",
    "WarmupResult",
    "PHASE_CONFIG",
    "PHASE_ACTIONS",
    # Evolution — Stealth Score
    "StealthScorer",
    "StealthCheck",
    "StealthScoreResult",
    "RiskLevel",
]


def _try_import_metrics():
    """Опциональный импорт metrics — требует prometheus_client."""
    try:
        from .metrics import (  # noqa: F401
            CP_COOKIES_AGE,
            CP_ERRORS,
            CP_LATENCY,
            CP_POSTS,
            HM_CHECKS,
            HM_LATENCY,
            HM_UPTIME,
            REGISTRY,
            SM_CHECKS,
            SM_HTTP_STATUS,
            SM_LATENCY,
            SM_UPTIME,
            SM_VISUAL_DIFF,
            SS_ACTIVE_BROWSERS,
            SS_BROWSER_ERRORS,
            SS_CACHE_HITS,
            SS_CACHE_MISSES,
            SS_LATENCY,
            SS_REQUESTS,
            STEALTH_OVERALL,
            STEALTH_SCORE,
            STEALTH_TESTS_RUN,
            CacheMetrics,
            LatencyTimer,
            get_metrics_output,
        )
        return True
    except ImportError:
        return False
