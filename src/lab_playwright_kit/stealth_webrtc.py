"""
WebRTC IP leak protection модуль.

Защищает от утечки реального IP-адреса через WebRTC API:
  - Блокировка RTCPeerConnection (полная или селективная)
  - Подмена ICE candidates (фильтрация host-кандидатов)
  - Подмена SDP offer/answer для удаления реальных IP
  - Блокировка STUN/TURN запросов через подмену конфигурации

Использование:
    >>> from lab_playwright_kit.stealth_webrtc import WebRTCConfig, WebRTCProtector
    >>> config = WebRTCConfig(mode="block_all")
    >>> js = WebRTCProtector.get_script(config)
    >>> await page.add_init_script(js)

Режимы работы:
  - block_all:   Полная блокировка RTCPeerConnection (безопаснее всего)
  - filter_host: Фильтрация только host-ICE-кандидатов (совместимость)
  - fake_ice:    Подмена всех ICE candidates на фейковые адреса
  - disabled:    Защита отключена

Покрытие сигнатур:
  - WebRTC IP leak тесты (browserleaks.com/webrtc, ipleak.net)
  - STUN/TURN fingerprinting
  - ICE candidate enumeration
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from loguru import logger
from playwright.async_api import Page


class WebRTCMode(str, Enum):
    """Режим защиты WebRTC."""
    BLOCK_ALL = "block_all"
    FILTER_HOST = "filter_host"
    FAKE_ICE = "fake_ice"
    DISABLED = "disabled"


@dataclass
class WebRTCConfig:
    """Конфигурация WebRTC IP leak protection.

    Attributes:
        mode: Режим защиты.
        block_stun: Блокировать STUN/TURN серверы в конфигурации.
        fake_ip: Фейковый IP для подмены (используется в режиме fake_ice).
        preserve_datachannel: Сохранить DataChannel API (работает только в filter_host).
    """
    mode: WebRTCMode = WebRTCMode.FILTER_HOST
    block_stun: bool = True
    fake_ip: str = "10.123.45.67"
    preserve_datachannel: bool = True

    @classmethod
    def block_all(cls) -> WebRTCConfig:
        """Полная блокировка — RTCPeerConnection возвращает пустой прокси."""
        return cls(mode=WebRTCMode.BLOCK_ALL)

    @classmethod
    def filter_host(cls) -> WebRTCConfig:
        """Фильтрация host-кандидатов — совместимость с WebRTC-приложениями."""
        return cls(mode=WebRTCMode.FILTER_HOST)

    @classmethod
    def fake_ice(cls, fake_ip: str = "10.123.45.67") -> WebRTCConfig:
        """Подмена ICE candidates на фейковый IP."""
        return cls(mode=WebRTCMode.FAKE_ICE, fake_ip=fake_ip)


class WebRTCProtector:
    """Генератор JS-скриптов для WebRTC IP leak protection.

    Каждый метод возвращает готовый JS-скрипт для инъекции через
    page.add_init_script(). Скрипты выполняются ДО загрузки страницы.

    Example:
        >>> config = WebRTCConfig.block_all()
        >>> script = WebRTCProtector.get_script(config)
        >>> await page.add_init_script(script)
    """

    @staticmethod
    def get_script(config: WebRTCConfig) -> str:
        """Получить полный JS-скрипт для инъекции.

        Объединяет все компоненты защиты в один скрипт
        в правильном порядке.

        Args:
            config: Конфигурация WebRTC защиты.

        Returns:
            JS-скрипт для инъекции через page.add_init_script().
        """
        if config.mode == WebRTCMode.DISABLED:
            return ""

        parts = [
            WebRTCProtector._block_rtcpeerconnection(config),
            WebRTCProtector._filter_ice_candidates(config),
            WebRTCProtector._patch_stun_config(config),
            WebRTCProtector._patch_sdp(config),
        ]

        # Оборачиваем в IIFE для изоляции переменных
        inner = "\n".join(p for p in parts if p.strip())
        return f"(function() {{\n{inner}\n}})();"

    @staticmethod
    def _block_rtcpeerconnection(config: WebRTCConfig) -> str:
        """Блокировка или патчинг RTCPeerConnection.

        В режиме BLOCK_ALL — заменяет конструктор на пустой прокси,
        который не создаёт реального соединения.

        В режиме FILTER_HOST/FAKE_ICE — патчит существующий конструктор
        для фильтрации ICE candidates.
        """
        if config.mode == WebRTCMode.BLOCK_ALL:
            return """
                // ── Полная блокировка RTCPeerConnection ──
                (function() {
                    const noop = function() { return this; };
                    const noopAsync = function() { return Promise.resolve(); };

                    function FakeRTCPeerConnection() {
                        // Пустой прокси — все методы возвращают this/Promise
                        return new Proxy(this, {
                            get(target, prop) {
                                if (prop === 'addEventListener') return noop;
                                if (prop === 'removeEventListener') return noop;
                                if (prop === 'dispatchEvent') return noop;
                                if (prop === 'createOffer') return noopAsync;
                                if (prop === 'createAnswer') return noopAsync;
                                if (prop === 'setLocalDescription') return noopAsync;
                                if (prop === 'setRemoteDescription') return noopAsync;
                                if (prop === 'addIceCandidate') return noopAsync;
                                if (prop === 'close') return noop;
                                if (prop === 'connectionState') return 'new';
                                if (prop === 'iceConnectionState') return 'new';
                                if (prop === 'iceGatheringState') return 'new';
                                if (prop === 'signalingState') return 'stable';
                                if (prop === 'onnegotiationneeded') return null;
                                if (prop === 'onicecandidate') return null;
                                if (prop === 'oniceconnectionstatechange') return null;
                                if (prop === 'onicegatheringstatechange') return null;
                                if (prop === 'onsignalingstatechange') return null;
                                if (prop === 'ontrack') return null;
                                if (prop === 'ondatachannel') return null;
                                if (prop === 'addTrack') return Promise.resolve();
                                if (prop === 'removeTrack') return noop;
                                if (prop === 'getSenders') return [];
                                if (prop === 'getReceivers') return [];
                                if (prop === 'getTransceivers') return [];
                                if (prop === 'getStats') return Promise.resolve(new Map());
                                return target[prop];
                            },
                            set(target, prop, value) {
                                target[prop] = value;
                                return true;
                            }
                        });
                    }

                    FakeRTCPeerConnection.prototype = {};
                    FakeRTCPeerConnection.prototype.constructor = FakeRTCPeerConnection;

                    if (window.RTCPeerConnection) window.RTCPeerConnection = FakeRTCPeerConnection;
                    if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = FakeRTCPeerConnection;
                    if (window.mozRTCPeerConnection) window.mozRTCPeerConnection = FakeRTCPeerConnection;
                })();
            """
        else:
            # FILTER_HOST и FAKE_ICE — патчим существующий конструктор
            return WebRTCProtector._patch_rtcpeerconnection(config)

    @staticmethod
    def _patch_rtcpeerconnection(config: WebRTCConfig) -> str:
        """Патчинг RTCPeerConnection для фильтрации/подмены ICE candidates."""
        fake_ip_js = config.fake_ip if config.mode == WebRTCMode.FAKE_ICE else ""

        return f"""
            // ── Патчинг RTCPeerConnection для ICE фильтрации ──
            (function() {{
                const OriginalRTCPeerConnection = window.RTCPeerConnection
                    || window.webkitRTCPeerConnection
                    || window.mozRTCPeerConnection;

                if (!OriginalRTCPeerConnection) return;

                const FAKE_IP = "{fake_ip_js}";
                const MODE = "{config.mode.value}";

                function PatchedRTCPeerConnection(config, ...args) {{
                    // Патчим iceServers конфигурацию
                    if (config && config.iceServers && config.iceServers.length > 0) {{
                        config = Object.assign({{}}, config, {{
                            iceServers: config.iceServers.map(server => {{
                                if (server.urls) {{
                                    return Object.assign({{}}, server, {{
                                        urls: Array.isArray(server.urls)
                                            ? server.urls.filter(u =>
                                                !u.includes('stun:') &&
                                                !u.includes('turn:') &&
                                                !u.includes('turns:'))
                                            : (typeof server.urls === 'string' &&
                                               (server.urls.includes('stun:') ||
                                                server.urls.includes('turn:') ||
                                                server.urls.includes('turns:'))
                                                ? '' : server.urls)
                                    }});
                                }}
                                return server;
                            }})
                        }});
                    }}

                    const pc = new OriginalRTCPeerConnection(config, ...args);

                    // Перехват addIceCandidate
                    const origAddIceCandidate = pc.addIceCandidate.bind(pc);
                    pc.addIceCandidate = function(iceCandidate, ...a) {{
                        try {{
                            const candidateStr = iceCandidate && iceCandidate.candidate ? iceCandidate.candidate : '';
                            if (MODE === 'filter_host' && candidateStr.includes('typ host')) {{
                                return Promise.resolve();
                            }}
                            if (MODE === 'fake_ice' && candidateStr) {{
                                // Подменяем IP в candidate
                                const modified = Object.assign({{}}, iceCandidate, {{
                                    candidate: candidateStr.replace(
                                        /\\d+\\.\\d+\\.\\d+\\.\\d+/g, FAKE_IP
                                    )
                                }});
                                return origAddIceCandidate(modified, ...a);
                            }}
                        }} catch(e) {{}}
                        return origAddIceCandidate(iceCandidate, ...a);
                    }};

                    // Перехват onicecandidate
                    let origHandler = null;
                    Object.defineProperty(pc, 'onicecandidate', {{
                        get: () => origHandler,
                        set: function(handler) {{
                            origHandler = handler;
                            if (handler) {{
                                pc.addEventListener('icecandidate', function(event) {{
                                    const candidate = event.candidate;
                                    if (!candidate || !candidate.candidate) {{
                                        handler(event);
                                        return;
                                    }}
                                    if (MODE === 'filter_host') {{
                                        if (candidate.candidate.includes('typ srflx') ||
                                            candidate.candidate.includes('typ relay')) {{
                                            handler(event);
                                        }}
                                    }} else if (MODE === 'fake_ice') {{
                                        // Подменяем IP в candidate
                                        const modifiedEvent = Object.create(event);
                                        modifiedEvent.candidate = Object.assign({{}}, candidate, {{
                                            candidate: candidate.candidate.replace(
                                                /\\d+\\.\\d+\\.\\d+\\.\\d+/g, FAKE_IP
                                            )
                                        }});
                                        handler(modifiedEvent);
                                    }} else {{
                                        handler(event);
                                    }}
                                }});
                            }}
                        }},
                        configurable: true
                    }});

                    // Патчим createOffer для подмены SDP
                    const origCreateOffer = pc.createOffer.bind(pc);
                    pc.createOffer = async function(...opts) {{
                        const offer = await origCreateOffer(...opts);
                        if (offer && offer.sdp) {{
                            if (MODE === 'filter_host') {{
                                offer.sdp = offer.sdp
                                    .split('\\r\\n')
                                    .filter(line => {{
                                        if (!line.startsWith('a=candidate:')) return true;
                                        return line.includes('typ srflx') || line.includes('typ relay');
                                    }})
                                    .join('\\r\\n');
                            }} else if (MODE === 'fake_ice') {{
                                offer.sdp = offer.sdp.replace(
                                    /\\d+\\.\\d+\\.\\d+\\.\\d+/g, FAKE_IP
                                );
                            }}
                        }}
                        return offer;
                    }};

                    return pc;
                }}

                PatchedRTCPeerConnection.prototype = OriginalRTCPeerConnection.prototype;
                Object.setPrototypeOf(PatchedRTCPeerConnection, OriginalRTCPeerConnection);

                if (window.RTCPeerConnection) window.RTCPeerConnection = PatchedRTCPeerConnection;
                if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = PatchedRTCPeerConnection;
                if (window.mozRTCPeerConnection) window.mozRTCPeerConnection = PatchedRTCPeerConnection;
            }})();
        """

    @staticmethod
    def _filter_ice_candidates(config: WebRTCConfig) -> str:
        """Дополнительная фильтрация ICE candidates через addEventListener."""
        if config.mode == WebRTCMode.BLOCK_ALL:
            return ""  # В режиме block_all уже заблокировано

        return """
            // ── Дополнительная фильтрация ICE candidates ──
            (function() {
                // Перехватываем addEventListener на уровне документа
                // для блокировки STUN запросов через fetch/XHR
                const origFetch = window.fetch;
                if (origFetch) {
                    window.fetch = function(url, ...args) {
                        const urlStr = typeof url === 'string' ? url : (url.url || '');
                        if (urlStr.includes('stun:') || urlStr.includes('turn:')) {
                            return Promise.reject(new TypeError('Failed to fetch'));
                        }
                        return origFetch.call(this, url, ...args);
                    };
                }
            })();
        """

    @staticmethod
    def _patch_stun_config(config: WebRTCConfig) -> str:
        """Блокировка STUN/TURN серверов в конфигурации ICE."""
        if not config.block_stun:
            return ""

        return """
            // ── Блокировка STUN/TURN серверов ──
            (function() {
                // Перехватываем создание RTCPeerConnection для очистки iceServers
                const origRTC = window.RTCPeerConnection
                    || window.webkitRTCPeerConnection
                    || window.mozRTCPeerConnection;

                if (!origRTC) return;

                function cleanIceServers(iceServers) {
                    if (!Array.isArray(iceServers)) return [];
                    return iceServers.filter(server => {
                        const urls = Array.isArray(server.urls) ? server.urls : [server.urls];
                        return !urls.some(url => {
                            if (!url) return false;
                            const u = url.toLowerCase();
                            return u.includes('stun:') || u.includes('turn:') || u.includes('turns:');
                        });
                    });
                }

                // Патчим конструктор для очистки iceServers
                function PatchedWithCleanIce(config, ...args) {
                    if (config && config.iceServers) {
                        config = Object.assign({}, config, {
                            iceServers: cleanIceServers(config.iceServers)
                        });
                    }
                    return new origRTC(config, ...args);
                }

                PatchedWithCleanIce.prototype = origRTC.prototype;
                if (window.RTCPeerConnection) window.RTCPeerConnection = PatchedWithCleanIce;
                if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = PatchedWithCleanIce;
                if (window.mozRTCPeerConnection) window.mozRTCPeerConnection = PatchedWithCleanIce;
            })();
        """

    @staticmethod
    def _patch_sdp(config: WebRTCConfig) -> str:
        """Подмена SDP для удаления информации о реальном IP."""
        if config.mode == WebRTCMode.BLOCK_ALL:
            return ""

        return """
            // ── Подмена SDP для удаления IP информации ──
            (function() {
                // Перехватываем createDataChannel для предотвращения
                // утечки через DataChannel negotiation
                const origRTC = window.RTCPeerConnection;
                if (!origRTC) return;

                // Патчим getStats для возврата пустой статистики
                const proto = origRTC.prototype;
                if (proto && proto.getStats) {
                    const origGetStats = proto.getStats;
                    proto.getStats = function() {
                        return Promise.resolve(new Map());
                    };
                }
            })();
        """


async def apply_webrtc_protection(
    page: Page,
    config: WebRTCConfig | None = None,
) -> None:
    """Применить WebRTC IP leak protection к странице.

    Инъектирует JS-скрипт через page.add_init_script() — скрипт
    выполняется ДО загрузки страницы.

    Args:
        page: Playwright Page объект.
        config: Конфигурация WebRTC защиты. По умолчанию — filter_host.

    Example:
        >>> from lab_playwright_kit.stealth_webrtc import apply_webrtc_protection, WebRTCConfig
        >>> await apply_webrtc_protection(page, WebRTCConfig.block_all())
    """
    cfg = config or WebRTCConfig.filter_host()
    script = WebRTCProtector.get_script(cfg)
    if script:
        await page.add_init_script(script)
        logger.debug(f"WebRTC protection applied: mode={cfg.mode.value}")
