"""
Base Prompt Class

모든 프롬프트의 기본이 되는 추상 클래스
"""

from abc import ABC, abstractmethod
from logging import getLogger
from typing import Any, Dict, List, Optional

logger = getLogger("prompts.base")


class BasePrompt(ABC):
    """프롬프트 기본 클래스"""

    def __init__(self, config: Dict[str, Any] = None):
        """초기화"""
        self.config = config or {}
        self.prompt_id = self.__class__.__name__
        self.version = "1.0.0"

    @abstractmethod
    def generate_system_prompt(self, **kwargs) -> str:
        """시스템 프롬프트 생성"""
        pass

    @abstractmethod
    def generate_user_prompt(self, **kwargs) -> str:
        """사용자 프롬프트 생성"""
        pass

    def generate_full_prompt(self, **kwargs) -> Dict[str, str]:
        """전체 프롬프트 생성"""
        try:
            system_prompt = self.generate_system_prompt(**kwargs)
            user_prompt = self.generate_user_prompt(**kwargs)

            return {
                "system": system_prompt,
                "user": user_prompt,
                "metadata": {
                    "prompt_id": self.prompt_id,
                    "version": self.version,
                    "config": self.config,
                },
            }

        except Exception as e:
            logger.error(f"Failed to generate full prompt: {e}")
            raise

    def validate_input(self, **kwargs) -> bool:
        """입력 유효성 검사"""
        # 기본 구현 - 하위 클래스에서 오버라이드
        return True

    def get_prompt_info(self) -> Dict[str, Any]:
        """프롬프트 정보 반환"""
        return {
            "prompt_id": self.prompt_id,
            "version": self.version,
            "description": self.__doc__ or "No description available",
            "config": self.config,
        }

    def __str__(self) -> str:
        """문자열 표현"""
        return f"{self.prompt_id} (v{self.version})"

    def __repr__(self) -> str:
        """표현식"""
        return f"<{self.__class__.__name__} prompt_id='{self.prompt_id}' version='{self.version}'>"
