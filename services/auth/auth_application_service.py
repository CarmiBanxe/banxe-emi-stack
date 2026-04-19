from typing import Any


class AuthApplicationService:
    """Thin application boundary for auth router orchestration."""

    def __init__(
        self,
        token_manager: Any = None,
        iam_port: Any = None,
        sca_service: Any = None,
    ) -> None:
        self.token_manager = token_manager
        self.iam_port = iam_port
        self.sca_service = sca_service

    async def login(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("login orchestration not extracted yet")

    async def refresh(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("refresh orchestration not extracted yet")
