"""AI provider layer.

Business logic never calls an AI SDK directly. All AI interaction happens
through the :class:`AIProvider` interface, so the provider can be swapped
(OpenAI, Anthropic, local, mock) without touching handlers or services.
"""
