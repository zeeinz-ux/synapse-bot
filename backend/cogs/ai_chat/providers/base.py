from typing import List, Dict, AsyncGenerator


class AIProvider:
    name: str = ""

    def __init__(self, session, api_key: str):
        self.session = session
        self.api_key = api_key

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def call(
        self,
        user_message: str,
        history: List[Dict],
        system_prompt: str,
        temperature: float = 0.75,
        images: list[dict] | None = None,
    ) -> tuple[str, bool]:
        raise NotImplementedError

    async def stream(
        self,
        user_message: str,
        history: List[Dict],
        system_prompt: str,
        temperature: float = 0.75,
        images: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        raise NotImplementedError
