# auth.py
import hashlib
import streamlit as st
from datetime import datetime, timedelta
from supabase import create_client, Client

TB_USERS = "mcb_users"

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

# ─────────────────────────────────────────
# PIN 암호화 (SHA-256)
# ─────────────────────────────────────────
def hash_pin(user_name: str, pin: str) -> str:
    """사용자명 + PIN 조합으로 해시 생성 (솔트 역할)"""
    combined = f"{user_name}:{pin}:mcb_salt_2024"
    return hashlib.sha256(combined.encode()).hexdigest()

# ─────────────────────────────────────────
# 회원가입 — PIN 등록
# ─────────────────────────────────────────
def register_user(user_name: str, pin: str) -> dict:
    """신규 사용자 등록"""
    sb = get_supabase()

    # 중복 확인
    existing = sb.table(TB_USERS).select("user_name") \
        .eq("user_name", user_name).execute()
    if existing.data:
        return {"success": False, "message": "이미 사용중인 아이디입니다."}

    # PIN 해시화 후 저장
    pin_hash = hash_pin(user_name, pin)
    sb.table(TB_USERS).insert({
        "user_name": user_name,
        "income": 0,
        "pin_hash": pin_hash,
        "failed_attempts": 0
    }).execute()
    return {"success": True, "message": "회원가입 완료!"}

# ─────────────────────────────────────────
# 로그인 — PIN 검증
# ─────────────────────────────────────────
def login_user(user_name: str, pin: str) -> dict:
    """로그인 처리"""
    sb = get_supabase()

    # 사용자 조회
    result = sb.table(TB_USERS).select("*") \
        .eq("user_name", user_name).execute()

    if not result.data:
        return {"success": False, "message": "존재하지 않는 아이디입니다."}

    user = result.data[0]

    # 계정 잠금 확인
    if user.get("locked_until"):
        locked_until = datetime.fromisoformat(str(user["locked_until"]))
        if datetime.now() < locked_until:
            remaining = int((locked_until - datetime.now()).seconds / 60)
            return {
                "success": False,
                "message": f"🔒 계정이 잠겼습니다. {remaining}분 후 다시 시도하세요."
            }
        else:
            # 잠금 해제
            sb.table(TB_USERS).update({
                "failed_attempts": 0,
                "locked_until": None
            }).eq("user_name", user_name).execute()
            user["failed_attempts"] = 0

    # PIN 검증
    input_hash = hash_pin(user_name, pin)
    if user.get("pin_hash") != input_hash:
        failed = (user.get("failed_attempts") or 0) + 1

        if failed >= 5:
            # 5회 실패 → 30분 잠금
            lock_time = (datetime.now() + timedelta(minutes=30)).isoformat()
            sb.table(TB_USERS).update({
                "failed_attempts": failed,
                "locked_until": lock_time
            }).eq("user_name", user_name).execute()
            return {
                "success": False,
                "message": "🔒 5회 실패! 계정이 30분간 잠겼습니다."
            }
        else:
            sb.table(TB_USERS).update({
                "failed_attempts": failed
            }).eq("user_name", user_name).execute()
            return {
                "success": False,
                "message": f"❌ PIN이 틀렸습니다. ({failed}/5회 실패)"
            }

    # 로그인 성공 → 실패 횟수 초기화
    sb.table(TB_USERS).update({
        "failed_attempts": 0,
        "locked_until": None
    }).eq("user_name", user_name).execute()

    return {"success": True, "message": "로그인 성공!", "user": user}

# ─────────────────────────────────────────
# PIN 변경
# ─────────────────────────────────────────
def change_pin(user_name: str, old_pin: str, new_pin: str) -> dict:
    """PIN 변경"""
    # 기존 PIN 검증
    verify = login_user(user_name, old_pin)
    if not verify["success"]:
        return {"success": False, "message": "현재 PIN이 올바르지 않습니다."}

    sb = get_supabase()
    new_hash = hash_pin(user_name, new_pin)
    sb.table(TB_USERS).update({
        "pin_hash": new_hash
    }).eq("user_name", user_name).execute()
    return {"success": True, "message": "PIN이 변경되었습니다."}

# ─────────────────────────────────────────
# 로그인 상태 확인
# ─────────────────────────────────────────
def is_logged_in() -> bool:
    return st.session_state.get("is_authenticated", False)

def get_current_user() -> str:
    return st.session_state.get("current_user", None)

def logout():
    """로그아웃 — 세션 초기화"""
    keys_to_clear = [
        "is_authenticated", "current_user", "user_loaded",
        "income", "loans", "utilities", "subscriptions", "etc_fixed"
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
