CHAT_CALLS = 0


def chat(*_args, **_kwargs) -> str:
    global CHAT_CALLS
    CHAT_CALLS += 1
    raise RuntimeError("LLM is not used by search")
