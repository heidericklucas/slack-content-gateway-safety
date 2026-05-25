"""Slack integration — bolt app, handlers, warning formatting."""

from app.slack.bolt_app import build_bolt_app
from app.slack.handlers import MessageHandler
from app.slack.warnings import WARNING_TEMPLATES, render_warning

__all__ = ["WARNING_TEMPLATES", "MessageHandler", "build_bolt_app", "render_warning"]
