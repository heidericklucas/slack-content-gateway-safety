"""Warning message templates shown back to users in-channel."""

from __future__ import annotations

from app.schemas import Category

WARNING_TEMPLATES: dict[Category, str] = {
    Category.THREAT: (
        ":rotating_light: <@{user_id}>, your message contains a threat. "
        "This type of language is not appropriate."
    ),
    Category.COERCIVE_AUTHORITY: (
        ":warning: <@{user_id}>, your message may come across as controlling or overly "
        "authoritative. Please reconsider your tone to maintain respect."
    ),
    Category.ABUSIVE_LANGUAGE: (
        ":warning: <@{user_id}>, your message contains abusive or offensive language. "
        "Please maintain respect."
    ),
    Category.HARASSMENT: (
        ":warning: <@{user_id}>, your message may come across as harassing. "
        "Please reconsider how it might land."
    ),
    Category.AGGRESSION: (
        ":warning: <@{user_id}>, your message reads as aggressive. "
        "A calmer tone usually keeps the conversation productive."
    ),
    Category.CONDESCENSION: (
        ":warning: <@{user_id}>, your message may come across as condescending. "
        "Consider rephrasing to acknowledge the other person's perspective."
    ),
}


def render_warning(category: Category, user_id: str) -> str:
    """Render the warning template for ``category`` with the offending user mentioned."""

    template = WARNING_TEMPLATES.get(category)
    if template is None:
        return WARNING_TEMPLATES[Category.AGGRESSION].format(user_id=user_id)
    return template.format(user_id=user_id)
