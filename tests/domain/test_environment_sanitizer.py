"""Tests for EnvironmentSanitizer."""

from porterminal.domain import EnvironmentRules, EnvironmentSanitizer


class TestEnvironmentSanitizer:
    """Tests for EnvironmentSanitizer."""

    def test_allows_safe_vars(self, environment_rules):
        """Test that safe variables are allowed."""
        sanitizer = EnvironmentSanitizer(environment_rules)

        source = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/user",
            "TERM": "xterm",
        }

        result = sanitizer.sanitize(source)

        assert "PATH" in result
        assert result["PATH"] == "/usr/bin:/bin"
        assert "HOME" in result

    def test_blocks_secret_vars(self, environment_rules):
        """Test that secret variables are blocked."""
        sanitizer = EnvironmentSanitizer(environment_rules)

        source = {
            "PATH": "/usr/bin",
            "AWS_SECRET_ACCESS_KEY": "super-secret",
            "GITHUB_TOKEN": "ghp_xxxx",
            "OPENAI_API_KEY": "sk-xxxx",
        }

        result = sanitizer.sanitize(source)

        assert "PATH" in result
        assert "AWS_SECRET_ACCESS_KEY" not in result
        assert "GITHUB_TOKEN" not in result
        assert "OPENAI_API_KEY" not in result

    def test_blocks_suffix_patterns(self, environment_rules):
        """Test that variables with blocked suffixes are blocked."""
        sanitizer = EnvironmentSanitizer(environment_rules)

        source = {
            "PATH": "/usr/bin",
            "MY_CUSTOM_KEY": "value",
            "SOME_SECRET": "value",
            "AUTH_TOKEN": "value",
            "DB_PASSWORD": "value",
        }

        result = sanitizer.sanitize(source)

        assert "PATH" in result
        assert "MY_CUSTOM_KEY" not in result
        assert "SOME_SECRET" not in result
        assert "AUTH_TOKEN" not in result
        assert "DB_PASSWORD" not in result

    def test_applies_forced_vars(self, environment_rules):
        """Test that forced variables are applied."""
        sanitizer = EnvironmentSanitizer(environment_rules)

        source = {
            "PATH": "/usr/bin",
            "TERM": "dumb",  # Will be overwritten
        }

        result = sanitizer.sanitize(source)

        assert result["TERM"] == "xterm-256color"
        assert result["TERM_SESSION_TYPE"] == "remote-web"

    def test_unknown_vars_not_allowed(self, environment_rules):
        """Test that unknown variables are not allowed by default."""
        sanitizer = EnvironmentSanitizer(environment_rules)

        source = {
            "PATH": "/usr/bin",
            "MY_CUSTOM_VAR": "value",
            "RANDOM_VAR": "value",
        }

        result = sanitizer.sanitize(source)

        assert "PATH" in result
        assert "MY_CUSTOM_VAR" not in result
        assert "RANDOM_VAR" not in result

    def test_is_var_allowed(self, environment_rules):
        """Test is_var_allowed method."""
        sanitizer = EnvironmentSanitizer(environment_rules)

        assert sanitizer.is_var_allowed("PATH") is True
        assert sanitizer.is_var_allowed("HOME") is True
        assert sanitizer.is_var_allowed("AWS_SECRET_ACCESS_KEY") is False
        assert sanitizer.is_var_allowed("RANDOM_VAR") is False

    def test_is_var_blocked(self, environment_rules):
        """Test is_var_blocked method."""
        sanitizer = EnvironmentSanitizer(environment_rules)

        assert sanitizer.is_var_blocked("AWS_SECRET_ACCESS_KEY") is True
        assert sanitizer.is_var_blocked("MY_API_KEY") is True
        assert sanitizer.is_var_blocked("PATH") is False

    def test_empty_source(self, environment_rules):
        """Test sanitizing empty source."""
        sanitizer = EnvironmentSanitizer(environment_rules)

        result = sanitizer.sanitize({})

        # Should still have forced vars
        assert result["TERM"] == "xterm-256color"
        assert result["TERM_SESSION_TYPE"] == "remote-web"

    def test_custom_rules(self):
        """Test with custom rules."""
        rules = EnvironmentRules(
            allowed_vars=frozenset({"CUSTOM_VAR"}),
            blocked_vars=frozenset({"BLOCKED_VAR"}),
            forced_vars=(("FORCED", "value"),),
        )
        sanitizer = EnvironmentSanitizer(rules)

        source = {
            "CUSTOM_VAR": "allowed",
            "BLOCKED_VAR": "blocked",
            "OTHER_VAR": "not allowed",
        }

        result = sanitizer.sanitize(source)

        assert result["CUSTOM_VAR"] == "allowed"
        assert "BLOCKED_VAR" not in result
        assert "OTHER_VAR" not in result
        assert result["FORCED"] == "value"
