"""
Platform Registry — расширяемый реестр платформ для авторизации и парсинга.

Вдохновлён Maigret (3000+ платформ):
  - Декларативное описание платформ
  - Три типа проверки: message, status_code, response_url
  - Presence/Absence строки для надёжной идентификации
  - Теги для фильтрации по категориям и странам
  - Ранжирование по популярности

Использование:
    >>> from lab_playwright_kit.platform_registry import PlatformRegistry, PlatformProfile
    >>> registry = PlatformRegistry()
    >>> profile = registry.get("github")
    >>> print(profile.url_template.format(username="octocat"))
    https://github.com/octocat
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CheckType(str, Enum):
    """Тип проверки наличия аккаунта."""
    MESSAGE = "message"         # Поиск подстрок в HTML
    STATUS_CODE = "status_code" # HTTP код ответа
    RESPONSE_URL = "response_url"  # Анализ редиректа


@dataclass
class PlatformProfile:
    """Профиль платформы для авторизации и парсинга.

    Аналог MaigretSite из Maigret, адаптирован под нашу архитектуру.

    Attributes:
        name: Имя платформы
        url_main: Главная страница
        url_template: URL профиля с {username}
        username_claimed: Заведомо существующий username для тестов
        username_unclaimed: Заведомо несуществующий username для тестов
        check_type: Тип проверки наличия аккаунта
        presense_strs: Подстроки в HTML, подтверждающие наличие
        absence_strs: Подстроки в HTML, подтверждающие отсутствие
        tags: Теги категорий (social, coding, ru, us, etc.)
        alexa_rank: Ранг популярности (меньше = популярнее)
        disabled: Отключена ли платформа
        headers: Пользовательские HTTP-заголовки
        regex_check: Регулярка для валидации username
        notes: Заметки
    """
    name: str = ""
    url_main: str = ""
    url_template: str = ""
    username_claimed: str = ""
    username_unclaimed: str = "noonewouldeverusethis7xyz"
    check_type: CheckType = CheckType.MESSAGE
    presense_strs: list[str] = field(default_factory=list)
    absence_strs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    alexa_rank: int = 999999
    disabled: bool = False
    headers: dict[str, str] = field(default_factory=dict)
    regex_check: str = ""
    notes: str = ""

    def url_for(self, username: str) -> str:
        """Получить URL профиля для username."""
        return self.url_template.format(username=username)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url_main": self.url_main,
            "url_template": self.url_template,
            "check_type": self.check_type.value,
            "tags": self.tags,
            "alexa_rank": self.alexa_rank,
        }


class PlatformRegistry:
    """Реестр платформ.

    Хранит профили платформ с быстрым доступом по имени.
    Поддерживает фильтрацию по тегам и категориям.

    Использование:
        >>> registry = PlatformRegistry()
        >>> registry.load_defaults()
        >>> profile = registry.get("github")
        >>> social = registry.filter_by_tag("social")
        >>> top50 = registry.top(50)
    """

    def __init__(self):
        self._profiles: dict[str, PlatformProfile] = {}

    def register(self, profile: PlatformProfile) -> None:
        """Зарегистрировать платформу."""
        self._profiles[profile.name.lower()] = profile

    def get(self, name: str) -> PlatformProfile | None:
        """Получить профиль по имени."""
        return self._profiles.get(name.lower())

    def filter_by_tag(self, tag: str) -> list[PlatformProfile]:
        """Фильтровать по тегу."""
        return [p for p in self._profiles.values() if tag in p.tags and not p.disabled]

    def filter_by_tags(self, tags: list[str], match_all: bool = False) -> list[PlatformProfile]:
        """Фильтровать по нескольким тегам."""
        if match_all:
            return [p for p in self._profiles.values()
                    if all(t in p.tags for t in tags) and not p.disabled]
        return [p for p in self._profiles.values()
                if any(t in p.tags for t in tags) and not p.disabled]

    def top(self, n: int = 50) -> list[PlatformProfile]:
        """Топ-N платформ по популярности."""
        enabled = [p for p in self._profiles.values() if not p.disabled]
        return sorted(enabled, key=lambda p: p.alexa_rank)[:n]

    def all(self) -> list[PlatformProfile]:
        """Все активные платформы."""
        return [p for p in self._profiles.values() if not p.disabled]

    def count(self) -> int:
        """Количество активных платформ."""
        return len([p for p in self._profiles.values() if not p.disabled])

    def load_defaults(self) -> None:
        """Загрузить платформы по умолчанию (50 популярных)."""
        for profile in _DEFAULT_PLATFORMS:
            self.register(profile)

    def load_from_dict(self, data: dict[str, dict]) -> None:
        """Загрузить платформы из словаря (совместимость с Maigret-форматом)."""
        for name, info in data.items():
            profile = PlatformProfile(
                name=name,
                url_main=info.get("urlMain", ""),
                url_template=info.get("url", ""),
                username_claimed=info.get("usernameClaimed", ""),
                username_unclaimed=info.get("usernameUnclaimed", "noonewouldeverusethis7xyz"),
                check_type=CheckType(info.get("checkType", "message")),
                presense_strs=info.get("presenseStrs", []),
                absence_strs=info.get("absenceStrs", []),
                tags=info.get("tags", []),
                alexa_rank=info.get("alexaRank", 999999),
                disabled=info.get("disabled", False),
                headers=info.get("headers", {}),
                regex_check=info.get("regexCheck", ""),
                notes="Imported from Maigret format",
            )
            self.register(profile)


# ─── 50 популярных платформ ─────────────────────────────────────────────────

_DEFAULT_PLATFORMS: list[PlatformProfile] = [
    # === Социальные сети ===
    PlatformProfile(
        name="VK",
        url_main="https://vk.com",
        url_template="https://vk.com/{username}",
        username_claimed="durov",
        check_type=CheckType.STATUS_CODE,
        tags=["social", "ru"],
        alexa_rank=25,
        notes="VK: 200=exists, 404=not found. Verified on live.",
    ),
    PlatformProfile(
        name="OK",
        url_main="https://ok.ru",
        url_template="https://ok.ru/profile/{username}",
        username_claimed="500000000000",
        check_type=CheckType.STATUS_CODE,
        tags=["social", "ru"],
        alexa_rank=45,
        notes="Одноклассники",
    ),
    PlatformProfile(
        name="Facebook",
        url_main="https://www.facebook.com",
        url_template="https://www.facebook.com/{username}",
        username_claimed="zuck",
        check_type=CheckType.STATUS_CODE,
        absence_strs=["404"],
        tags=["social", "us"],
        alexa_rank=3,
        notes="Facebook: может требовать авторизацию",
    ),
    PlatformProfile(
        name="Instagram",
        url_main="https://www.instagram.com",
        url_template="https://www.instagram.com/{username}/",
        username_claimed="instagram",
        check_type=CheckType.MESSAGE,
        presense_strs=["profile", "biography"],
        absence_strs=["Page Not Found", "404"],
        tags=["social", "photo", "us"],
        alexa_rank=4,
        notes="Instagram: JS-rendered, needs browser",
    ),
    PlatformProfile(
        name="Twitter",
        url_main="https://x.com",
        url_template="https://x.com/{username}",
        username_claimed="elonmusk",
        check_type=CheckType.MESSAGE,
        presense_strs=["profile", "UserDescription"],
        absence_strs=["This account doesn't exist", "404"],
        tags=["social", "news", "us"],
        alexa_rank=10,
        notes="Twitter/X: JS-rendered, needs browser for reliable check",
    ),
    PlatformProfile(
        name="LinkedIn",
        url_main="https://www.linkedin.com",
        url_template="https://www.linkedin.com/in/{username}",
        username_claimed="williamhgates",
        check_type=CheckType.MESSAGE,
        presense_strs=["profile", "pv-entity__summary-info"],
        absence_strs=["Page not found", "404"],
        tags=["social", "business", "us"],
        alexa_rank=20,
        notes="LinkedIn: требует авторизацию",
    ),
    PlatformProfile(
        name="Pinterest",
        url_main="https://www.pinterest.com",
        url_template="https://www.pinterest.com/{username}/",
        username_claimed="pinterest",
        check_type=CheckType.MESSAGE,
        presense_strs=["userProfile", "profile"],
        absence_strs=["404", "not found"],
        tags=["social", "photo", "us"],
        alexa_rank=30,
    ),
    PlatformProfile(
        name="Tumblr",
        url_main="https://www.tumblr.com",
        url_template="https://{username}.tumblr.com",
        username_claimed="staff",
        check_type=CheckType.STATUS_CODE,
        tags=["social", "blog", "us"],
        alexa_rank=60,
    ),
    PlatformProfile(
        name="Reddit",
        url_main="https://www.reddit.com",
        url_template="https://www.reddit.com/user/{username}",
        username_claimed="spez",
        check_type=CheckType.STATUS_CODE,
        tags=["social", "news", "us"],
        alexa_rank=18,
        notes="Reddit: returns 200 + Cloudflare verification for all. Needs browser/FlareSolverr.",
    ),
    PlatformProfile(
        name="Mastodon",
        url_main="https://mastodon.social",
        url_template="https://mastodon.social/@{username}",
        username_claimed="Gargron",
        check_type=CheckType.MESSAGE,
        presense_strs=["account__display-name"],
        absence_strs=["404"],
        tags=["social", "federated", "us"],
        alexa_rank=500,
        notes="Mastodon: федеративная соцсеть",
    ),

    # === Мессенджеры ===
    PlatformProfile(
        name="Telegram",
        url_main="https://t.me",
        url_template="https://t.me/{username}",
        username_claimed="durov",
        check_type=CheckType.MESSAGE,
        presense_strs=["Telegram: View @"],
        absence_strs=["Telegram: Contact @"],
        tags=["messenger", "social"],
        alexa_rank=50,
        notes="Telegram: 'View @user' = exists, 'Contact @user' = not found. Verified on live.",
    ),

    # === Разработка ===
    PlatformProfile(
        name="GitHub",
        url_main="https://github.com",
        url_template="https://github.com/{username}",
        username_claimed="torvalds",
        check_type=CheckType.STATUS_CODE,
        tags=["coding", "us"],
        alexa_rank=76,
        notes="GitHub: 200=exists, 404=not found. Verified on live.",
    ),
    PlatformProfile(
        name="GitLab",
        url_main="https://gitlab.com",
        url_template="https://gitlab.com/{username}",
        username_claimed="gitlab",
        check_type=CheckType.STATUS_CODE,
        tags=["coding", "us"],
        alexa_rank=200,
    ),
    PlatformProfile(
        name="Bitbucket",
        url_main="https://bitbucket.org",
        url_template="https://bitbucket.org/{username}/",
        username_claimed="bitbucket",
        check_type=CheckType.STATUS_CODE,
        tags=["coding", "us"],
        alexa_rank=300,
    ),
    PlatformProfile(
        name="StackOverflow",
        url_main="https://stackoverflow.com",
        url_template="https://stackoverflow.com/users/{username}",
        username_claimed="1",
        check_type=CheckType.STATUS_CODE,
        tags=["coding", "qa", "us"],
        alexa_rank=55,
    ),
    PlatformProfile(
        name="HackerNews",
        url_main="https://news.ycombinator.com",
        url_template="https://news.ycombinator.com/user?id={username}",
        username_claimed="pg",
        check_type=CheckType.MESSAGE,
        presense_strs=["hnuser", "score"],
        absence_strs=["No such user"],
        tags=["coding", "news", "us"],
        alexa_rank=400,
    ),
    PlatformProfile(
        name="Dev.to",
        url_main="https://dev.to",
        url_template="https://dev.to/{username}",
        username_claimed="ben",
        check_type=CheckType.STATUS_CODE,
        tags=["coding", "blog", "us"],
        alexa_rank=350,
    ),
    PlatformProfile(
        name="CodePen",
        url_main="https://codepen.io",
        url_template="https://codepen.io/{username}",
        username_claimed="chriscoyier",
        check_type=CheckType.STATUS_CODE,
        tags=["coding", "frontend", "us"],
        alexa_rank=250,
    ),
    PlatformProfile(
        name="Replit",
        url_main="https://replit.com",
        url_template="https://replit.com/@{username}",
        username_claimed="amasad",
        check_type=CheckType.STATUS_CODE,
        tags=["coding", "us"],
        alexa_rank=150,
    ),

    # === Русскоязычные платформы ===
    PlatformProfile(
        name="Habr",
        url_main="https://habr.com",
        url_template="https://habr.com/ru/users/{username}/",
        username_claimed="alizar",
        check_type=CheckType.STATUS_CODE,
        tags=["blog", "tech", "ru"],
        alexa_rank=150,
        notes="Habr: 200=exists, 404=not found. Verified on live.",
    ),
    PlatformProfile(
        name="VC.ru",
        url_main="https://vc.ru",
        url_template="https://vc.ru/u/{username}",
        username_claimed="vc",
        check_type=CheckType.STATUS_CODE,
        tags=["blog", "business", "ru"],
        alexa_rank=200,
        notes="VC.ru",
    ),
    PlatformProfile(
        name="DTF",
        url_main="https://dtf.ru",
        url_template="https://dtf.ru/u/{username}",
        username_claimed="dtf",
        check_type=CheckType.STATUS_CODE,
        tags=["blog", "gaming", "ru"],
        alexa_rank=300,
        notes="DTF",
    ),
    PlatformProfile(
        name="Pikabu",
        url_main="https://pikabu.ru",
        url_template="https://pikabu.ru/@{username}",
        username_claimed="admin",
        check_type=CheckType.STATUS_CODE,
        tags=["social", "blog", "ru"],
        alexa_rank=100,
        notes="Пикабу",
    ),
    PlatformProfile(
        name="Yandex.Zen",
        url_main="https://zen.yandex.ru",
        url_template="https://zen.yandex.ru/user/{username}",
        username_claimed="zen",
        check_type=CheckType.STATUS_CODE,
        tags=["blog", "ru"],
        alexa_rank=80,
        notes="Яндекс.Дзен",
    ),
    PlatformProfile(
        name="MyMail",
        url_main="https://my.mail.ru",
        url_template="https://my.mail.ru/mail/{username}/",
        username_claimed="mail",
        check_type=CheckType.STATUS_CODE,
        tags=["social", "ru"],
        alexa_rank=120,
        notes="Мой Мир",
    ),

    # === Видео ===
    PlatformProfile(
        name="YouTube",
        url_main="https://www.youtube.com",
        url_template="https://www.youtube.com/@{username}",
        username_claimed="YouTube",
        check_type=CheckType.MESSAGE,
        presense_strs=["channel-header", "ytd-channel-name"],
        absence_strs=["404", "This channel does not exist"],
        tags=["video", "us"],
        alexa_rank=2,
        notes="YouTube: JS-rendered, needs browser for reliable check",
    ),
    PlatformProfile(
        name="Twitch",
        url_main="https://www.twitch.tv",
        url_template="https://www.twitch.tv/{username}",
        username_claimed="shroud",
        check_type=CheckType.MESSAGE,
        presense_strs=["channel-header", "tw-image-avatar"],
        absence_strs=["404", "Sorry. Unless you've got a time machine"],
        tags=["video", "gaming", "us"],
        alexa_rank=35,
        notes="Twitch: may need browser",
    ),
    PlatformProfile(
        name="Vimeo",
        url_main="https://vimeo.com",
        url_template="https://vimeo.com/{username}",
        username_claimed="vimeo",
        check_type=CheckType.STATUS_CODE,
        tags=["video", "us"],
        alexa_rank=110,
    ),

    # === Фото и дизайн ===
    PlatformProfile(
        name="Flickr",
        url_main="https://www.flickr.com",
        url_template="https://www.flickr.com/people/{username}/",
        username_claimed="flickr",
        check_type=CheckType.STATUS_CODE,
        tags=["photo", "us"],
        alexa_rank=180,
    ),
    PlatformProfile(
        name="Dribbble",
        url_main="https://dribbble.com",
        url_template="https://dribbble.com/{username}",
        username_claimed="dribbble",
        check_type=CheckType.STATUS_CODE,
        tags=["design", "us"],
        alexa_rank=220,
    ),
    PlatformProfile(
        name="Behance",
        url_main="https://www.behance.net",
        url_template="https://www.behance.net/{username}",
        username_claimed="behance",
        check_type=CheckType.STATUS_CODE,
        tags=["design", "us"],
        alexa_rank=160,
    ),
    PlatformProfile(
        name="ArtStation",
        url_main="https://www.artstation.com",
        url_template="https://www.artstation.com/{username}",
        username_claimed="artstation",
        check_type=CheckType.STATUS_CODE,
        tags=["design", "art", "us"],
        alexa_rank=280,
    ),

    # === Музыка ===
    PlatformProfile(
        name="SoundCloud",
        url_main="https://soundcloud.com",
        url_template="https://soundcloud.com/{username}",
        username_claimed="soundcloud",
        check_type=CheckType.STATUS_CODE,
        tags=["music", "us"],
        alexa_rank=140,
    ),
    PlatformProfile(
        name="Spotify",
        url_main="https://open.spotify.com",
        url_template="https://open.spotify.com/user/{username}",
        username_claimed="spotify",
        check_type=CheckType.MESSAGE,
        presense_strs=["profile", "user"],
        absence_strs=["404"],
        tags=["music", "us"],
        alexa_rank=15,
        notes="Spotify: JS-rendered, returns 200 for all. Needs browser.",
    ),
    PlatformProfile(
        name="Bandcamp",
        url_main="https://bandcamp.com",
        url_template="https://{username}.bandcamp.com",
        username_claimed="bandcamp",
        check_type=CheckType.STATUS_CODE,
        tags=["music", "us"],
        alexa_rank=320,
    ),

    # === Блоги и форумы ===
    PlatformProfile(
        name="Medium",
        url_main="https://medium.com",
        url_template="https://medium.com/@{username}",
        username_claimed="medium",
        check_type=CheckType.STATUS_CODE,
        tags=["blog", "us"],
        alexa_rank=90,
        notes="Medium: returns 403 for all (Cloudflare). Needs FlareSolverr.",
    ),
    PlatformProfile(
        name="LiveJournal",
        url_main="https://www.livejournal.com",
        url_template="https://{username}.livejournal.com",
        username_claimed="lj",
        check_type=CheckType.STATUS_CODE,
        tags=["blog", "ru"],
        alexa_rank=250,
        notes="LiveJournal",
    ),
    PlatformProfile(
        name="Blogger",
        url_main="https://www.blogger.com",
        url_template="https://{username}.blogspot.com",
        username_claimed="blogger",
        check_type=CheckType.STATUS_CODE,
        tags=["blog", "us"],
        alexa_rank=30,
    ),
    PlatformProfile(
        name="WordPress",
        url_main="https://wordpress.com",
        url_template="https://{username}.wordpress.com",
        username_claimed="wordpress",
        check_type=CheckType.STATUS_CODE,
        tags=["blog", "us"],
        alexa_rank=22,
    ),

    # === Электронная коммерция ===
    PlatformProfile(
        name="Etsy",
        url_main="https://www.etsy.com",
        url_template="https://www.etsy.com/shop/{username}",
        username_claimed="etsy",
        check_type=CheckType.STATUS_CODE,
        tags=["shop", "us"],
        alexa_rank=40,
    ),
    PlatformProfile(
        name="eBay",
        url_main="https://www.ebay.com",
        url_template="https://www.ebay.com/usr/{username}",
        username_claimed="ebay",
        check_type=CheckType.STATUS_CODE,
        tags=["shop", "us"],
        alexa_rank=42,
    ),

    # === Образование ===
    PlatformProfile(
        name="Coursera",
        url_main="https://www.coursera.org",
        url_template="https://www.coursera.org/user/{username}",
        username_claimed="coursera",
        check_type=CheckType.STATUS_CODE,
        tags=["education", "us"],
        alexa_rank=85,
    ),
    PlatformProfile(
        name="Udemy",
        url_main="https://www.udemy.com",
        url_template="https://www.udemy.com/user/{username}/",
        username_claimed="udemy",
        check_type=CheckType.STATUS_CODE,
        tags=["education", "us"],
        alexa_rank=70,
    ),
    PlatformProfile(
        name="Kaggle",
        url_main="https://www.kaggle.com",
        url_template="https://www.kaggle.com/{username}",
        username_claimed="kaggle",
        check_type=CheckType.STATUS_CODE,
        tags=["education", "data", "us"],
        alexa_rank=130,
    ),

    # === Другое ===
    PlatformProfile(
        name="Keybase",
        url_main="https://keybase.io",
        url_template="https://keybase.io/{username}",
        username_claimed="keybase",
        check_type=CheckType.STATUS_CODE,
        tags=["crypto", "us"],
        alexa_rank=350,
    ),
    PlatformProfile(
        name="Figma",
        url_main="https://www.figma.com",
        url_template="https://www.figma.com/@{username}",
        username_claimed="figma",
        check_type=CheckType.STATUS_CODE,
        tags=["design", "us"],
        alexa_rank=95,
    ),
    PlatformProfile(
        name="Notion",
        url_main="https://www.notion.so",
        url_template="https://www.notion.so/{username}",
        username_claimed="notion",
        check_type=CheckType.STATUS_CODE,
        tags=["productivity", "us"],
        alexa_rank=120,
    ),
    PlatformProfile(
        name="ProductHunt",
        url_main="https://www.producthunt.com",
        url_template="https://www.producthunt.com/@{username}",
        username_claimed="producthunt",
        check_type=CheckType.STATUS_CODE,
        tags=["startup", "us"],
        alexa_rank=180,
    ),
    PlatformProfile(
        name="Goodreads",
        url_main="https://www.goodreads.com",
        url_template="https://www.goodreads.com/{username}",
        username_claimed="goodreads",
        check_type=CheckType.STATUS_CODE,
        tags=["books", "us"],
        alexa_rank=110,
    ),
    PlatformProfile(
        name="Last.fm",
        url_main="https://www.last.fm",
        url_template="https://www.last.fm/user/{username}",
        username_claimed="lastfm",
        check_type=CheckType.STATUS_CODE,
        tags=["music", "us"],
        alexa_rank=280,
    ),
    PlatformProfile(
        name="Gravatar",
        url_main="https://en.gravatar.com",
        url_template="https://en.gravatar.com/{username}",
        username_claimed="gravatar",
        check_type=CheckType.STATUS_CODE,
        tags=["avatar", "us"],
        alexa_rank=200,
        notes="Gravatar: глобальный аватар-сервис",
    ),
]
