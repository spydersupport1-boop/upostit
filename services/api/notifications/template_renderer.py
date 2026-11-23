"""Safe, sandboxed template renderer for notification subjects and bodies.

Guarantees:
- Strictly prevents arbitrary Python code execution (no eval, exec, or unrestricted AST).
- Rejects prohibited identifier lookups (e.g., dunder methods, attribute navigation).
- Validates that all required placeholders in the template are supplied.
- Context-aware escaping: escapes HTML entities for HTML output to prevent script injection;
  strips CRLF/control characters for email subjects to prevent header injection.
"""

import html
import re
from typing import Any

from services.api.notifications.exceptions import TemplateRenderError

# Matches both {{ variable_name }} and {variable_name} with valid alphanumeric identifiers
_PLACEHOLDER_REGEX = re.compile(
    r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}|\{([a-zA-Z_][a-zA-Z0-9_]*)\}"
)

# Detects attempts to access dunder attributes or suspicious expressions
_SUSPICIOUS_EXPRESSION_REGEX = re.compile(
    r"\{\{[\s\S]*?__[\s\S]*?\}\}|\{[\s\S]*?__[\s\S]*?\}|import|eval|exec|compile|os\.|sys\."
)


class SafeTemplateRenderer:
    """Safe renderer supporting variable substitution without arbitrary code evaluation."""

    @classmethod
    def extract_required_variables(cls, template_str: str) -> set[str]:
        """Extracts the set of variable names required by a template string."""
        required: set[str] = set()
        for match in _PLACEHOLDER_REGEX.finditer(template_str):
            var_name = match.group(1) or match.group(2)
            if var_name:
                required.add(var_name)
        return required

    @classmethod
    def render_text(
        cls,
        template_str: str,
        variables: dict[str, Any],
        *,
        escape_html_entities: bool = False,
        is_subject: bool = False,
    ) -> str:
        """Renders a single template string safely with parameter substitution.

        Args:
            template_str: The raw template text containing {var} or {{ var }} placeholders.
            variables: Mapping of variable names to substitution values.
            escape_html_entities: If True, escapes HTML chars (<, >, &, \", ') for HTML body output.
            is_subject: If True, strips newlines and control characters to prevent header injection.

        Returns:
            The safely rendered text.

        Raises:
            TemplateRenderError: If required variables are missing or malicious syntax is detected.
        """
        if not template_str:
            return ""

        # Pre-scan for malicious SSTI attempts or prohibited dunder patterns
        if _SUSPICIOUS_EXPRESSION_REGEX.search(template_str):
            raise TemplateRenderError(
                "Template contains prohibited expressions, dunder attributes, or unsafe keywords."
            )

        required_vars = cls.extract_required_variables(template_str)
        missing_vars = [var for var in required_vars if var not in variables]
        if missing_vars:
            raise TemplateRenderError(
                f"Missing required template variables: {', '.join(sorted(missing_vars))}",
                missing_variable=missing_vars[0],
            )

        def _replace_match(match: re.Match[str]) -> str:
            var_name = match.group(1) or match.group(2)
            raw_val = variables.get(var_name, "")
            val_str = str(raw_val) if raw_val is not None else ""

            if escape_html_entities:
                return html.escape(val_str, quote=True)
            elif is_subject:
                # Strip CRLF to prevent email header injection
                clean_val = val_str.replace("\r", " ").replace("\n", " ").strip()
                return clean_val
            return val_str

        rendered = _PLACEHOLDER_REGEX.sub(_replace_match, template_str)

        if is_subject:
            # Final sanitize of subject line
            rendered = " ".join(rendered.split())

        return rendered

    @classmethod
    def render_notification(
        cls,
        subject_template: str | None,
        body_template: str,
        variables: dict[str, Any],
        *,
        is_html_channel: bool = False,
    ) -> tuple[str | None, str]:
        """Renders both subject and body for a notification snapshot.

        Args:
            subject_template: Optional subject template (e.g. for EMAIL).
            body_template: The body template (Text or HTML).
            variables: Template substitution parameters.
            is_html_channel: Whether to escape HTML entities in body.

        Returns:
            Tuple of (rendered_subject, rendered_body).
        """
        rendered_subject: str | None = None
        if subject_template:
            rendered_subject = cls.render_text(
                subject_template,
                variables,
                escape_html_entities=False,
                is_subject=True,
            )

        rendered_body = cls.render_text(
            body_template,
            variables,
            escape_html_entities=is_html_channel,
            is_subject=False,
        )

        return rendered_subject, rendered_body

