"""
Stream Manager for Expert Agent Service

스트림 상태 관리 및 연속성 처리
"""

import asyncio
import json
from datetime import datetime, timedelta
from logging import getLogger
from typing import Any, Dict, Optional, Set
from uuid import uuid4

logger = getLogger("stream_manager")


class StreamState:
    """스트림 상태 정보"""
    
    def __init__(self, chat_group_id: str, agent_code: str, user_id: str):
        self.chat_group_id = chat_group_id
        self.agent_code = agent_code
        self.user_id = user_id
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.is_active = True
        self.current_node = None
        self.current_state = None
        self.stream_generator = None
        self.connected_clients: Set[str] = set()
        self.stream_id = str(uuid4())
        
    def add_client(self, client_id: str):
        """클라이언트 연결 추가"""
        self.connected_clients.add(client_id)
        self.last_activity = datetime.now()
        
    def remove_client(self, client_id: str):
        """클라이언트 연결 제거"""
        self.connected_clients.discard(client_id)
        self.last_activity = datetime.now()
        
    def has_clients(self) -> bool:
        """연결된 클라이언트가 있는지 확인"""
        return len(self.connected_clients) > 0
        
    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """스트림이 만료되었는지 확인"""
        return datetime.now() - self.last_activity > timedelta(minutes=timeout_minutes)
        
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "chat_group_id": self.chat_group_id,
            "agent_code": self.agent_code,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_active": self.is_active,
            "current_node": self.current_node,
            "connected_clients": list(self.connected_clients),
            "stream_id": self.stream_id
        }


class StreamManager:
    """스트림 상태 관리자"""
    
    def __init__(self):
        self._streams: Dict[str, StreamState] = {}
        self._cleanup_task = None
        self._cleanup_interval = 300  # 5분마다 정리
        
    async def start_cleanup_task(self):
        """정리 작업 시작"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_streams())
            
    async def _cleanup_expired_streams(self):
        """만료된 스트림 정리"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                current_time = datetime.now()
                expired_streams = []
                
                for chat_group_id, stream_state in self._streams.items():
                    if stream_state.is_expired() and not stream_state.has_clients():
                        expired_streams.append(chat_group_id)
                        
                for chat_group_id in expired_streams:
                    await self.remove_stream(chat_group_id)
                    logger.info(f"만료된 스트림 정리: {chat_group_id}")
                    
            except Exception as e:
                logger.error(f"스트림 정리 중 오류: {e}")
                
    def get_stream(self, chat_group_id: str) -> Optional[StreamState]:
        """스트림 상태 조회"""
        return self._streams.get(chat_group_id)
        
    def create_stream(self, chat_group_id: str, agent_code: str, user_id: str) -> StreamState:
        """새 스트림 상태 생성"""
        if chat_group_id in self._streams:
            # 기존 스트림이 있으면 업데이트
            stream_state = self._streams[chat_group_id]
            stream_state.last_activity = datetime.now()
            stream_state.is_active = True
            logger.info(f"기존 스트림 재활성화: {chat_group_id}")
        else:
            # 새 스트림 생성
            stream_state = StreamState(chat_group_id, agent_code, user_id)
            self._streams[chat_group_id] = stream_state
            logger.info(f"새 스트림 생성: {chat_group_id}")
            
        return stream_state
        
    async def remove_stream(self, chat_group_id: str):
        """스트림 상태 제거"""
        if chat_group_id in self._streams:
            stream_state = self._streams[chat_group_id]
            # 활성 스트림 제너레이터가 있으면 정리
            if stream_state.stream_generator:
                try:
                    if hasattr(stream_state.stream_generator, 'aclose'):
                        await stream_state.stream_generator.aclose()
                except Exception as e:
                    logger.warning(f"스트림 제너레이터 정리 중 오류: {e}")
                    
            del self._streams[chat_group_id]
            logger.info(f"스트림 상태 제거: {chat_group_id}")
            
    def add_client_to_stream(self, chat_group_id: str, client_id: str) -> bool:
        """스트림에 클라이언트 추가"""
        stream_state = self.get_stream(chat_group_id)
        if stream_state:
            stream_state.add_client(client_id)
            return True
        return False
        
    def remove_client_from_stream(self, chat_group_id: str, client_id: str):
        """스트림에서 클라이언트 제거"""
        stream_state = self.get_stream(chat_group_id)
        if stream_state:
            stream_state.remove_client(client_id)
            
    def update_stream_state(self, chat_group_id: str, current_node: str = None, current_state: Dict[str, Any] = None):
        """스트림 상태 업데이트"""
        stream_state = self.get_stream(chat_group_id)
        if stream_state:
            if current_node:
                stream_state.current_node = current_node
            if current_state:
                stream_state.current_state = current_state
            stream_state.last_activity = datetime.now()
            
    def set_stream_generator(self, chat_group_id: str, generator):
        """스트림 제너레이터 설정"""
        stream_state = self.get_stream(chat_group_id)
        if stream_state:
            stream_state.stream_generator = generator
            
    def get_active_streams(self) -> Dict[str, StreamState]:
        """활성 스트림 목록 조회"""
        return {k: v for k, v in self._streams.items() if v.is_active}
        
    def get_stream_info(self, chat_group_id: str) -> Optional[Dict[str, Any]]:
        """스트림 정보 조회"""
        stream_state = self.get_stream(chat_group_id)
        if stream_state:
            return stream_state.to_dict()
        return None
        
    async def cleanup(self):
        """매니저 정리"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
                
        # 모든 스트림 정리
        for chat_group_id in list(self._streams.keys()):
            await self.remove_stream(chat_group_id)


# 전역 스트림 매니저 인스턴스
stream_manager = StreamManager()
