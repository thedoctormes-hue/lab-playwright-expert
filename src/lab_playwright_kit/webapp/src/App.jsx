import { useState, useCallback } from 'react';

const API_BASE = '/api/v1';

const AVAILABLE_TAGS = [
  { id: 'social', label: '👥 Соцсети' },
  { id: 'coding', label: '💻 Код' },
  { id: 'ru', label: '🇷🇺 Русские' },
  { id: 'forum', label: '💬 Форумы' },
  { id: 'messaging', label: '✉️ Мессенджеры' },
  { id: 'media', label: '🎬 Медиа' },
  { id: 'gaming', label: '🎮 Игры' },
];

function stringToColor(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = ['#64b5f6', '#81c784', '#ffb74d', '#e57373', '#ba68c8', '#4dd0e1', '#ff8a65', '#a1887f'];
  return colors[Math.abs(hash) % colors.length];
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

export default function App() {
  const [username, setUsername] = useState('');
  const [selectedTags, setSelectedTags] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const toggleTag = (tagId) => {
    setSelectedTags(prev =>
      prev.includes(tagId) ? prev.filter(t => t !== tagId) : [...prev, tagId]
    );
  };

  const search = useCallback(async () => {
    if (!username.trim()) return;
    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const body = { username: username.trim(), top_n: 50 };
      if (selectedTags.length > 0) body.tags = selectedTags;

      const resp = await fetch(`${API_BASE}/osint/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) throw new Error(`Ошибка сервера: ${resp.status}`);

      const data = await resp.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [username, selectedTags]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') search();
  };

  return (
    <div className="container">
      <header className="header">
        <h1>🔍 OSINT Finder</h1>
        <p>Поиск аккаунтов на 50+ платформах по всему миру</p>
      </header>

      <section className="search-section">
        <div className="search-box">
          <input
            type="text"
            placeholder="Введите username..."
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={handleKeyDown}
            autoFocus
          />
          <button onClick={search} disabled={loading || !username.trim()}>
            {loading ? '⏳...' : '🔍 Найти'}
          </button>
        </div>

        <div className="tags">
          {AVAILABLE_TAGS.map(tag => (
            <span
              key={tag.id}
              className={`tag ${selectedTags.includes(tag.id) ? 'active' : ''}`}
              onClick={() => toggleTag(tag.id)}
            >
              {tag.label}
            </span>
          ))}
        </div>
      </section>

      {loading && (
        <div className="status">
          <div className="spinner" />
          <div>Ищу <b>{escapeHtml(username)}</b> на 50+ платформах...</div>
        </div>
      )}

      {error && (
        <div className="error">
          <h3>❌ Ошибка</h3>
          <p>{escapeHtml(error)}</p>
          <p style={{ marginTop: 8, fontSize: 13, color: 'var(--text-muted)' }}>
            Убедитесь, что API сервер запущен на порту 8190
          </p>
        </div>
      )}

      {result && !loading && (
        <>
          <div className="results-header">
            <h2>
              {result.total_found > 0
                ? `✅ Найдено: ${result.total_found}`
                : '❌ Не найдено'}
            </h2>
            <span className="meta">
              {result.checked} платформ · {result.elapsed_seconds}с
            </span>
          </div>

          {result.accounts && result.accounts.length > 0 ? (
            [...result.accounts]
              .sort((a, b) => b.confidence - a.confidence)
              .map((acc, i) => {
                const confClass = acc.confidence >= 0.8 ? 'high' : acc.confidence >= 0.5 ? 'medium' : 'low';
                const color = stringToColor(acc.platform);
                const initial = acc.platform.charAt(0).toUpperCase();

                return (
                  <a key={i} href={acc.url} target="_blank" rel="noopener noreferrer">
                    <div className="account-card">
                      <div className="icon" style={{ background: `${color}20`, color }}>
                        {initial}
                      </div>
                      <div className="info">
                        <div className="platform">{escapeHtml(acc.platform)}</div>
                        <div className="username">@{escapeHtml(acc.username)}</div>
                        {acc.tags && acc.tags.length > 0 && (
                          <div className="tags">
                            {acc.tags.slice(0, 3).map((t, j) => (
                              <span key={j} className="tag">{escapeHtml(t)}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className={`confidence ${confClass}`}>
                        {Math.round(acc.confidence * 100)}%
                      </div>
                    </div>
                  </a>
                );
              })
          ) : (
            <div className="empty">
              <div className="emoji">🔍</div>
              <h3>{escapeHtml(result.query)} не найден</h3>
              <p>Проверено {result.checked} платформ за {result.elapsed_seconds}с</p>
            </div>
          )}
        </>
      )}

      <footer className="footer">
        <p>OSINT Finder · Powered by Lab Playwright Expert · 50+ платформ</p>
      </footer>
    </div>
  );
}
