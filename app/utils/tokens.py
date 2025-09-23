def count_tokens(text: str) -> int:
    """
    Super-lightweight token estimate to avoid heavy deps.
    Replace with tiktoken if/when you want precision.
    """
    return max(1, len(text) // 4)
