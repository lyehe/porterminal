"""Pure environment sanitization service."""

from dataclasses import dataclass

from ..values.environment_rules import EnvironmentRules


@dataclass
class EnvironmentSanitizer:
    """Pure environment sanitization service.

    Takes environment dict as input (does NOT access os.environ).
    Infrastructure layer is responsible for providing the input.
    """

    rules: EnvironmentRules

    def sanitize(self, source_env: dict[str, str]) -> dict[str, str]:
        """Sanitize environment variables according to rules.

        Args:
            source_env: Source environment (e.g., from os.environ).

        Returns:
            Sanitized environment dict.
        """
        result: dict[str, str] = {}

        # Copy only allowed variables
        for var in self.rules.allowed_vars:
            if var in source_env:
                result[var] = source_env[var]

        # Defense in depth: remove any blocked vars that might have slipped through
        for var in self.rules.blocked_vars:
            result.pop(var, None)

        # Also remove any vars that match blocked patterns
        blocked_suffixes = ("_KEY", "_SECRET", "_TOKEN", "_PASSWORD", "_CREDENTIAL")
        for var in list(result.keys()):
            if any(var.endswith(suffix) for suffix in blocked_suffixes):
                del result[var]

        # Apply forced variables
        result.update(self.rules.get_forced_vars_dict())

        return result

    def is_var_allowed(self, var_name: str) -> bool:
        """Check if a variable name is allowed."""
        if var_name in self.rules.blocked_vars:
            return False
        return var_name in self.rules.allowed_vars

    def is_var_blocked(self, var_name: str) -> bool:
        """Check if a variable name is blocked."""
        if var_name in self.rules.blocked_vars:
            return True

        blocked_suffixes = ("_KEY", "_SECRET", "_TOKEN", "_PASSWORD", "_CREDENTIAL")
        return any(var_name.endswith(suffix) for suffix in blocked_suffixes)
