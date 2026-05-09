"""
유틸리티 함수 모음 (masking 등)
"""
from typing import Any

def mask_sensitive(obj: Any) -> Any:
    """
    민감한 정보(비밀번호, 토큰 등)를 재귀적으로 마스킹합니다.
    Args:
        obj: dict, list, 기타 객체
    Returns:
        마스킹된 객체
    """
    sensitive_keys = {'password', 'password_hash', 'token', 'api_key', 'secret', 'authorization'}
    if isinstance(obj, dict): #obj가 dict인지 확인
        masked = dict(obj)
        for key in list(masked.keys()):
            if any(k in key.lower() for k in sensitive_keys):
                masked[key] = '***REDACTED***'
            elif isinstance(masked[key], (dict, list)):
                masked[key] = mask_sensitive(masked[key])
        return masked
    elif isinstance(obj, list):
        return [mask_sensitive(item) for item in obj]
    return obj