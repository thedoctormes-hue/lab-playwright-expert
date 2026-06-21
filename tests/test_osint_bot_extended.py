"""
Extended tests for osint_bot.py — BotState, create_bot, command handlers.

Covers: BotState, create_bot factory, handler registration.
"""

from lab_playwright_kit.osint_bot import BotState, create_bot


class TestBotState:
    def test_init(self):
        state = BotState()
        assert state.total_searches == 0
        assert state.total_found == 0
        assert state.start_time > 0

    def test_registry_loaded(self):
        state = BotState()
        assert state.registry is not None
        assert state.registry.count() > 0

    def test_finder_initialized(self):
        state = BotState()
        assert state.finder is not None

    def test_increment_searches(self):
        state = BotState()
        state.total_searches += 1
        assert state.total_searches == 1

    def test_increment_found(self):
        state = BotState()
        state.total_found += 5
        assert state.total_found == 5


class TestCreateBot:
    def test_create_with_valid_token(self):
        bot, dp = create_bot("test_token_123")
        assert bot is not None
        assert dp is not None

    def test_create_token_passed(self):
        bot, dp = create_bot("my_token")
        assert bot is not None

    def test_returns_tuple(self):
        result = create_bot("token")
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestHandlersExist:
    """Verify that all expected handlers are registered in the router."""

    def test_router_has_handlers(self):
        from lab_playwright_kit.osint_bot import router

        # Router should have handlers registered
        handlers = router._handlers
        assert len(handlers) > 0

    def test_start_handler_registered(self):
        from lab_playwright_kit.osint_bot import router

        # Check that CommandStart handler exists
        found = False
        for handler_list in router._handlers.values():
            for h in handler_list:
                callback = getattr(h, "callback", None)
                if callback and callback.__name__ == "cmd_start":
                    found = True
        assert found, "cmd_start handler not found in router"

    def test_find_handler_registered(self):
        from lab_playwright_kit.osint_bot import router

        found = False
        for handler_list in router._handlers.values():
            for h in handler_list:
                callback = getattr(h, "callback", None)
                if callback and callback.__name__ == "cmd_find":
                    found = True
        assert found, "cmd_find handler not found in router"

    def test_platforms_handler_registered(self):
        from lab_playwright_kit.osint_bot import router

        found = False
        for handler_list in router._handlers.values():
            for h in handler_list:
                callback = getattr(h, "callback", None)
                if callback and callback.__name__ == "cmd_platforms":
                    found = True
        assert found, "cmd_platforms handler not found in router"

    def test_stats_handler_registered(self):
        from lab_playwright_kit.osint_bot import router

        found = False
        for handler_list in router._handlers.values():
            for h in handler_list:
                callback = getattr(h, "callback", None)
                if callback and callback.__name__ == "cmd_stats":
                    found = True
        assert found, "cmd_stats handler not found in router"


class TestBotStateModule:
    """Test the module-level state singleton."""

    def test_module_state_exists(self):
        from lab_playwright_kit import osint_bot

        assert hasattr(osint_bot, "state")
        assert isinstance(osint_bot.state, BotState)

    def test_module_router_exists(self):
        from lab_playwright_kit import osint_bot

        assert hasattr(osint_bot, "router")
