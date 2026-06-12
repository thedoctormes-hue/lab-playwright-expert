"""
Антидетект конфигурация: маскировка автоматизации.

Уровни защиты:
  - minimal:   только webdriver (базовый)
  - standard:  webdriver + plugins + languages + chrome + permissions + webgl (было "full")
  - advanced:  standard + все P0 векторы (vendor, csi, loadTimes, hardware,
               dimensions, deviceMemory, screenDepth, mediaCodecs, iframe, webrtc)
  - full:      advanced + random_ua (максимальная маскировка)

Покрытие сигнатур: ~35% → ~85%
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from loguru import logger
from playwright.async_api import Page


# Реалистичные User-Agent строки
REALISTIC_UAS = [
    # Chrome 131 Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome 131 macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Firefox 133 Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Firefox 133 macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Edge 131 Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

# ─── Базовые скрипты (standard) ───────────────────────────────────────────────

STEALTH_SCRIPTS: dict[str, str] = {
    # 1. Убираем navigator.webdriver
    "webdriver": """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """,

    # 2. Фейковые плагины Chrome
    "plugins": """
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' },
            ]
        });
    """,

    # 3. Реалистичные языки
    "languages": """
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ru-RU', 'ru', 'en-US', 'en']
        });
    """,

    # 4. Базовый chrome.runtime (без csi/loadTimes — они в advanced)
    "chrome_runtime": """
        window.chrome = {
            runtime: {},
            app: {}
        };
    """,

    # 5. Маскировка permissions API
    "permissions": """
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """,

    # 6. WebGL vendor/renderer маскировка
    "webgl": """
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter.call(this, parameter);
        };
    """,

    # ─── P0: Расширенные векторы (advanced) ──────────────────────────────────

    # 7. navigator.vendor — headless возвращает пустую строку
    "navigator_vendor": """
        Object.defineProperty(navigator, 'vendor', {
            get: () => 'Google Inc.'
        });
    """,

    # 8. chrome.csi() — фейковые метрики загрузки страницы
    #    Реальный chrome.csi() возвращает объект с полями:
    #    pageT, startE, tran, onloadT, lcp, fp, fid, cls
    "chrome_csi": """
        (function() {
            if (!window.chrome) window.chrome = {};
            window.chrome.csi = function() {
                return {
                    pageT: parseFloat((Math.random() * 800 + 200).toFixed(1)),
                    startE: Date.now() - Math.floor(Math.random() * 5000 + 1000),
                    tran: 15,
                    onloadT: Date.now() - Math.floor(Math.random() * 300 + 50),
                    lcp: parseFloat((Math.random() * 1500 + 500).toFixed(1)),
                    fp: parseFloat((Math.random() * 800 + 200).toFixed(1)),
                    fid: parseFloat((Math.random() * 50 + 5).toFixed(1)),
                    cls: parseFloat((Math.random() * 0.1).toFixed(4))
                };
            };
        })();
    """,

    # 9. chrome.loadTimes() — deprecated, но некоторые детекты всё ещё проверяют
    #    Реальный loadTimes() возвращает connectionInfo, npnNegotiatedProtocol, etc.
    "chrome_loadtimes": """
        (function() {
            if (!window.chrome) window.chrome = {};
            window.chrome.loadTimes = function() {
                return {
                    connectionInfo: 'h2',
                    npnNegotiatedProtocol: 'h2',
                    wasFetchedViaSpdy: true,
                    wasNpnNegotiated: true,
                    wasAlternateProtocolAvailable: false,
                    connectionInfoHasEmptyDocument: false,
                    navigationType: 'Other',
                    wasPrefetched: false,
                    firstPaintAfterLoadTime: 0,
                    requestTime: (Date.now() / 1000 - 2).toFixed(3),
                    startLoadTime: (Date.now() / 1000 - 1.8).toFixed(3),
                    commitLoadTime: (Date.now() / 1000 - 1.5).toFixed(3),
                    finishDocumentLoadTime: (Date.now() / 1000 - 0.3).toFixed(3),
                    finishLoadTime: (Date.now() / 1000 - 0.1).toFixed(3),
                    firstPaintTime: (Date.now() / 1000 - 0.8).toFixed(3)
                };
            };
        })();
    """,

    # 10. navigator.hardwareConcurrency — headless часто показывает 1 или нечётное
    "hardware_concurrency": """
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8
        });
    """,

    # 11. window.outerWidth/outerHead — в headless совпадают с inner или 0
    #    Реальный браузер: outer = inner + рамки окна (~16px ширина, ~89px высота)
    "outer_dimensions": """
        (function() {
            const frameX = Math.floor(Math.random() * 8) * 2 + 16;  // 16..30, чётные
            const frameY = Math.floor(Math.random() * 20) + 89;      // 89..108
            Object.defineProperty(window, 'outerWidth', {
                get: () => (window.innerWidth || 1280) + frameX
            });
            Object.defineProperty(window, 'outerHeight', {
                get: () => (window.innerHeight || 720) + frameY
            });
        })();
    """,

    # 12. navigator.deviceMemory — headless часто отсутствует или 2
    "device_memory": """
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });
    """,

    # 13. screen.colorDepth / pixelDepth — headless может вернуть 16 или 32
    "screen_depth": """
        Object.defineProperty(screen, 'colorDepth', {
            get: () => 24
        });
        Object.defineProperty(screen, 'pixelDepth', {
            get: () => 24
        });
    """,

    # 14. MediaSource.isTypeSupported — headless часто возвращает false для всех кодеков
    "media_codecs": """
        (function() {
            const originalIsTypeSupported = MediaSource.isTypeSupported.bind(MediaSource);
            const supportedCodecs = [
                'video/mp4; codecs="avc1.42E01E"',
                'video/mp4; codecs="avc1.4D401E"',
                'video/mp4; codecs="avc1.64001E"',
                'video/mp4; codecs="avc1.42E01E, mp4a.40.2"',
                'video/webm; codecs="vp8"',
                'video/webm; codecs="vp9"',
                'video/webm; codecs="vp8, vorbis"',
                'audio/mp4; codecs="mp4a.40.2"',
                'audio/webm; codecs="opus"',
                'audio/webm; codecs="vorbis"',
                'audio/aac',
                'audio/flac',
                'audio/wav; codecs="1"',
            ];
            MediaSource.isTypeSupported = function(mimeType) {
                if (supportedCodecs.some(codec => mimeType.includes(codec))) {
                    return true;
                }
                return originalIsTypeSupported(mimeType);
            };
        })();
    """,

    # 15. iframe.contentWindow — HeadlessDetect проверяет iframe.contentWindow.outerWidth === 0
    "iframe_content_window": """
        (function() {
            const originalCreateElement = document.createElement.bind(document);
            document.createElement = function(tag) {
                const el = originalCreateElement(tag);
                if (tag.toLowerCase() === 'iframe') {
                    // Перехватываем доступ к contentWindow после вставки
                    const origSrcSetter = el.__lookupSetter__('src') || function(){};
                    let realContentWindow = null;
                    Object.defineProperty(el, 'contentWindow', {
                        get: function() {
                            if (realContentWindow) return realContentWindow;
                            // Возвращаем прокси, имитирующий реальный window
                            return new Proxy(window, {
                                get(target, prop) {
                                    if (prop === 'outerWidth') return window.outerWidth;
                                    if (prop === 'outerHeight') return window.outerHeight;
                                    if (prop === 'innerWidth') return window.innerWidth;
                                    if (prop === 'innerHeight') return window.innerHeight;
                                    if (prop === 'navigator') return navigator;
                                    if (prop === 'document') return el.contentDocument || target.document;
                                    return target[prop];
                                }
                            });
                        },
                        configurable: true
                    });
                }
                return el;
            };
        })();
    """,

    # 16. WebRTC IP leak блокировка — предотвращает утечку реального IP через ICE
    #    (Базовая версия — расширенная в stealth_webrtc.py)
    "webrtc_leak": """
        (function() {
            // Перехватываем RTCPeerConnection
            const OriginalRTCPeerConnection = window.RTCPeerConnection
                || window.webkitRTCPeerConnection
                || window.mozRTCPeerConnection;

            if (!OriginalRTCPeerConnection) return;

            function PatchedRTCPeerConnection(config, ...args) {
                const pc = new OriginalRTCPeerConnection(config, ...args);

                // Перехватываем addIceCandidate — блокируем host-кандидатов с реальным IP
                const origAddIceCandidate = pc.addIceCandidate.bind(pc);
                pc.addIceCandidate = function(iceCandidate, ...a) {
                    try {
                        const candidateStr = iceCandidate && iceCandidate.candidate ? iceCandidate.candidate : '';
                        // Блокируем host-кандидаты (typ host) — они содержат реальный IP
                        // Пропускаем srflx/relay — это NAT/TURN адреса
                        if (candidateStr.includes('typ host')) {
                            // Молча игнорируем — кандидат не добавлен, IP не утёк
                            return Promise.resolve();
                        }
                    } catch(e) {}
                    return origAddIceCandidate(iceCandidate, ...a);
                };

                // Перехватываем onicecandidate — фильтруем кандидатов в колбэке
                let origHandler = null;
                Object.defineProperty(pc, 'onicecandidate', {
                    get: () => origHandler,
                    set: function(handler) {
                        origHandler = handler;
                        if (handler) {
                            pc.addEventListener('icecandidate', function(event) {
                                const candidate = event.candidate;
                                if (!candidate || !candidate.candidate) {
                                    handler(event);
                                    return;
                                }
                                // Фильтруем: пропускаем только srflx и relay
                                if (candidate.candidate.includes('typ srflx') ||
                                    candidate.candidate.includes('typ relay')) {
                                    handler(event);
                                }
                                // host-кандидаты молча отбрасываем
                            });
                        }
                    },
                    configurable: true
                });

                // Также патчим createOffer для подмены SDP
                const origCreateOffer = pc.createOffer.bind(pc);
                pc.createOffer = async function(...opts) {
                    const offer = await origCreateOffer(...opts);
                    if (offer && offer.sdp) {
                        // Убираем строки с реальными IP из SDP (a=candidate с host)
                        offer.sdp = offer.sdp
                            .split('\\r\\n')
                            .filter(line => {
                                if (!line.startsWith('a=candidate:')) return true;
                                // Оставляем только srflx и relay кандидатов
                                return line.includes('typ srflx') || line.includes('typ relay');
                            })
                            .join('\\r\\n');
                    }
                    return offer;
                };

                return pc;
            }

            // Копируем prototype и static properties
            PatchedRTCPeerConnection.prototype = OriginalRTCPeerConnection.prototype;
            Object.setPrototypeOf(PatchedRTCPeerConnection, OriginalRTCPeerConnection);

            // Заменяем глобально
            if (window.RTCPeerConnection) window.RTCPeerConnection = PatchedRTCPeerConnection;
            if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = PatchedRTCPeerConnection;
            if (window.mozRTCPeerConnection) window.mozRTCPeerConnection = PatchedRTCPeerConnection;
        })();
    """,

    # ─── P1: Дополнительные векторы (новые модули) ────────────────────────────

    # 17. AudioContext fingerprint spoofing — фейковый FFT-спектр
    #    Расширенная версия в stealth_audio.py
    "audio_spoof": """
        (function() {
            // Базовая подмена AudioContext — расширенная версия в stealth_audio.py
            if (typeof AudioContext === 'undefined' && typeof webkitAudioContext === 'undefined') return;

            const OrigAC = window.AudioContext || window.webkitAudioContext;
            if (!OrigAC) return;

            // Подмена createOscillator для фейкового спектра
            const origCreateAnalyser = OrigAC.prototype.createAnalyser;
            OrigAC.prototype.createAnalyser = function() {
                const analyser = origCreateAnalyser.call(this);

                // Подмена getFloatFrequencyData
                const origGetFloat = analyser.getFloatFrequencyData.bind(analyser);
                analyser.getFloatFrequencyData = function(array) {
                    for (let i = 0; i < array.length; i++) {
                        // Реалистичный шум -60..-20 dB
                        array[i] = -40 + Math.sin(i * 0.1 + 42) * 15 + (Math.random() - 0.5) * 10;
                    }
                };

                // Подмена getFloatTimeDomainData
                const origGetTime = analyser.getFloatTimeDomainData;
                if (origGetTime) {
                    analyser.getFloatTimeDomainData = function(array) {
                        for (let i = 0; i < array.length; i++) {
                            const t = i / 44100;
                            array[i] = Math.sin(t * 440 * Math.PI * 2) * 0.3 +
                                       Math.sin(t * 880 * Math.PI * 2) * 0.1 +
                                       (Math.random() - 0.5) * 0.05;
                        }
                    };
                }

                return analyser;
            };
        })();
    """,

    # 18. User-Agent Client Hints — согласованные Sec-CH-UA-*
    #    Расширенная версия в stealth_client_hints.py
    "client_hints": """
        (function() {
            // Базовая подмена userAgentData — расширенная версия в stealth_client_hints.py
            if (!navigator.userAgentData) return;

            const origGetHighEntropy = navigator.userAgentData.getHighEntropyValues;
            const origBrands = navigator.userAgentData.brands;
            const origMobile = navigator.userAgentData.mobile;
            const origPlatform = navigator.userAgentData.platform;

            // Определяем ожидаемые значения из User-Agent
            const ua = navigator.userAgent;
            let brand = 'Chromium';
            let version = '131';
            let platform = 'Windows';
            let mobile = false;

            const chromeMatch = ua.match(/Chrome\\/(\\d+)/);
            if (chromeMatch) {
                version = chromeMatch[1];
                brand = ua.includes('Edg/') ? 'Microsoft Edge' : 'Google Chrome';
            }
            const ffMatch = ua.match(/Firefox\\/(\\d+)/);
            if (ffMatch) {
                brand = 'Firefox';
                version = ffMatch[1];
            }
            if (ua.includes('Windows')) platform = 'Windows';
            else if (ua.includes('Mac')) platform = 'macOS';
            else if (ua.includes('Linux')) platform = 'Linux';
            if (ua.includes('Mobile') || ua.includes('Android') || ua.includes('iPhone')) mobile = true;

            const fakeUAData = {
                brands: [
                    {brand: 'Chromium', version: version},
                    {brand: brand, version: version},
                    {brand: 'Not-A.Brand', version: '24'}
                ],
                mobile: mobile,
                platform: platform,
                getHighEntropyValues: function(hints) {
                    const result = {
                        brands: this.brands,
                        mobile: mobile,
                        platform: platform,
                        platformVersion: '15.0.0',
                        architecture: 'x86',
                        bitness: '64',
                        model: '',
                        uaFullVersion: version + '.0.0.0'
                    };
                    const filtered = {};
                    for (const hint of hints) {
                        if (hint in result) filtered[hint] = result[hint];
                    }
                    return Promise.resolve(filtered);
                }
            };

            Object.defineProperty(navigator, 'userAgentData', {
                get: () => fakeUAData,
                configurable: true
            });
        })();
    """,
}


# ─── Группировка скриптов по уровням ─────────────────────────────────────────

# Уровень standard — базовые 6 скриптов (были в оригинале)
_STANDARD_KEYS = [
    "webdriver",
    "plugins",
    "languages",
    "chrome_runtime",
    "permissions",
    "webgl",
]

# Уровень advanced — все P0 векторы
_ADVANCED_KEYS = _STANDARD_KEYS + [
    "navigator_vendor",
    "chrome_csi",
    "chrome_loadtimes",
    "hardware_concurrency",
    "outer_dimensions",
    "device_memory",
    "screen_depth",
    "media_codecs",
    "iframe_content_window",
    "webrtc_leak",
    "audio_spoof",
    "client_hints",
]


@dataclass
class StealthConfig:
    """Конфигурация антидетекта.

    Поля соответствуют скриптам из STEALTH_SCRIPTS.
    Для ручного управления — устанавливайте флаги напрямую.
    Для быстрого выбора — используйте класс-методы minimal(), standard(), advanced(), full().
    """

    enabled: bool = True

    # ── Standard уровень ──
    mask_webdriver: bool = True
    mask_plugins: bool = True
    mask_languages: bool = True
    fake_chrome: bool = True
    fake_permissions: bool = True
    fake_webgl: bool = True

    # ── Advanced уровень (P0 векторы) ──
    mask_vendor: bool = False
    fake_csi: bool = False
    fake_loadtimes: bool = False
    fake_hardware: bool = False
    fake_dimensions: bool = False
    fake_device_memory: bool = False
    screen_depth: bool = False
    media_codecs: bool = False
    mask_iframe: bool = False
    block_webrtc: bool = False

    # ── P1 векторы (новые модули) ──
    spoof_audio: bool = False
    spoof_client_hints: bool = False

    # ── Дополнительно ──
    random_ua: bool = False

    @classmethod
    def minimal(cls) -> StealthConfig:
        """Минимальный — только webdriver.

        Покрытие: ~15% сигнатур.
        Использовать когда скорость важнее маскировки.
        """
        return cls(
            enabled=True,
            mask_webdriver=True,
            mask_plugins=False,
            mask_languages=False,
            fake_chrome=False,
            fake_permissions=False,
            fake_webgl=False,
            mask_vendor=False,
            fake_csi=False,
            fake_loadtimes=False,
            fake_hardware=False,
            fake_dimensions=False,
            fake_device_memory=False,
            screen_depth=False,
            media_codecs=False,
            mask_iframe=False,
            block_webrtc=False,
            spoof_audio=False,
            spoof_client_hints=False,
            random_ua=False,
        )

    @classmethod
    def standard(cls) -> StealthConfig:
        """Стандартный — базовые 6 скриптов (поведение старого full()).

        Покрытие: ~35% сигнатур.
        Подходит для большинства сайтов без продвинутого детекта.
        """
        return cls(
            enabled=True,
            mask_webdriver=True,
            mask_plugins=True,
            mask_languages=True,
            fake_chrome=True,
            fake_permissions=True,
            fake_webgl=True,
            # P0 векторы выключены
            mask_vendor=False,
            fake_csi=False,
            fake_loadtimes=False,
            fake_hardware=False,
            fake_dimensions=False,
            fake_device_memory=False,
            screen_depth=False,
            media_codecs=False,
            mask_iframe=False,
            block_webrtc=False,
            spoof_audio=False,
            spoof_client_hints=False,
            random_ua=False,
        )

    @classmethod
    def advanced(cls) -> StealthConfig:
        """Продвинутый — все P0 + P1 векторы включены.

        Покрытие: ~90% сигнатур.
        Обходит: HeadlessDetect, CreepJS, FingerprintJS (базовый),
        WebRTC leak детекты, media codec fingerprinting,
        AudioContext fingerprint, Client Hints mismatch.
        """
        return cls(
            enabled=True,
            mask_webdriver=True,
            mask_plugins=True,
            mask_languages=True,
            fake_chrome=True,
            fake_permissions=True,
            fake_webgl=True,
            mask_vendor=True,
            fake_csi=True,
            fake_loadtimes=True,
            fake_hardware=True,
            fake_dimensions=True,
            fake_device_memory=True,
            screen_depth=True,
            media_codecs=True,
            mask_iframe=True,
            block_webrtc=True,
            spoof_audio=True,
            spoof_client_hints=True,
            random_ua=False,
        )

    @classmethod
    def full(cls) -> StealthConfig:
        """Полный — advanced + случайный User-Agent.

        Покрытие: ~90%+ сигнатур с ротацией UA.
        Максимальная маскировка. Каждый запуск — уникальный fingerprint.
        """
        return cls(
            enabled=True,
            mask_webdriver=True,
            mask_plugins=True,
            mask_languages=True,
            fake_chrome=True,
            fake_permissions=True,
            fake_webgl=True,
            mask_vendor=True,
            fake_csi=True,
            fake_loadtimes=True,
            fake_hardware=True,
            fake_dimensions=True,
            fake_device_memory=True,
            screen_depth=True,
            media_codecs=True,
            mask_iframe=True,
            block_webrtc=True,
            spoof_audio=True,
            spoof_client_hints=True,
            random_ua=True,
        )

    def get_scripts(self) -> list[str]:
        """Получить список JS-скриптов для инъекции на основе конфигурации.

        Возвращает скрипты в порядке зависимостей:
        1. webdriver (всегда первым)
        2. chrome_runtime → chrome_csi → chrome_loadtimes (зависят от chrome)
        3. Остальные в произвольном порядке
        """
        if not self.enabled:
            return []

        # Маппинг флагов → ключей STEALTH_SCRIPTS
        flag_to_script: list[tuple[str, str]] = [
            ("mask_webdriver", "webdriver"),
            ("mask_plugins", "plugins"),
            ("mask_languages", "languages"),
            ("fake_chrome", "chrome_runtime"),
            ("fake_permissions", "permissions"),
            ("fake_webgl", "webgl"),
            ("mask_vendor", "navigator_vendor"),
            ("fake_csi", "chrome_csi"),
            ("fake_loadtimes", "chrome_loadtimes"),
            ("fake_hardware", "hardware_concurrency"),
            ("fake_dimensions", "outer_dimensions"),
            ("fake_device_memory", "device_memory"),
            ("screen_depth", "screen_depth"),
            ("media_codecs", "media_codecs"),
            ("mask_iframe", "iframe_content_window"),
            ("block_webrtc", "webrtc_leak"),
            ("spoof_audio", "audio_spoof"),
            ("spoof_client_hints", "client_hints"),
        ]

        scripts = []
        for flag_name, script_key in flag_to_script:
            if getattr(self, flag_name, False):
                scripts.append(STEALTH_SCRIPTS[script_key])
        return scripts

    def get_user_agent(self) -> str | None:
        """Получить User-Agent на основе конфигурации.

        Если random_ua = True — возвращает случайный из REALISTIC_UAS.
        Иначе — None (используется UA по умолчанию из браузера).
        """
        if self.random_ua:
            return random.choice(REALISTIC_UAS)
        return None


async def apply_stealth(page: Page, config: StealthConfig | None = None) -> None:
    """Применить антидетект к странице.

    Инъектирует JS-скрипты через page.add_init_script() — каждый скрипт
    выполняется ДО загрузки страницы, гарантируя маскировку с первого запроса.

    Args:
        page: Playwright Page объект
        config: Конфигурация антидетекта. По умолчанию — StealthConfig.full()

    Example:
        >>> from lab_playwright_kit.stealth import apply_stealth, StealthConfig
        >>> await apply_stealth(page, StealthConfig.advanced())
    """
    cfg = config or StealthConfig.full()
    scripts = cfg.get_scripts()
    for script in scripts:
        await page.add_init_script(script)
    logger.debug(f"Stealth applied: {len(scripts)} scripts (level={_level_name(cfg)})")


def _level_name(cfg: StealthConfig) -> str:
    """Определить уровень защиты по конфигурации (для логов)."""
    if not cfg.enabled:
        return "disabled"
    if cfg.random_ua and cfg.block_webrtc:
        return "full"
    if cfg.block_webrtc:
        return "advanced"
    if cfg.fake_webgl:
        return "standard"
    if cfg.mask_webdriver:
        return "minimal"
    return "custom"
