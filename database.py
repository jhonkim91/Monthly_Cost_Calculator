# database.py
import streamlit as st
from supabase import create_client, Client

# ─────────────────────────────────────────
# 테이블명 상수 (mcb_ 접두사로 기존 테이블과 구분)
# ─────────────────────────────────────────
TB_USERS         = "mcb_users"
TB_LOANS         = "mcb_loans"
TB_UTILITIES     = "mcb_utilities"
TB_SUBSCRIPTIONS = "mcb_subscriptions"
TB_ETC           = "mcb_etc_fixed"

# ─────────────────────────────────────────
# Supabase 클라이언트 초기화 (1회만 실행)
# ─────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


# ══════════════════════════════════════════
# 👤 사용자
# ══════════════════════════════════════════
def load_user(user_name: str) -> dict:
    """사용자 불러오기 — 없으면 자동 생성"""
    sb = get_supabase()
    result = sb.table(TB_USERS).select("*").eq("user_name", user_name).execute()
    if result.data:
        return result.data[0]
    # 신규 사용자 자동 생성
    new_user = {"user_name": user_name, "income": 0}
    sb.table(TB_USERS).insert(new_user).execute()
    return new_user

def save_income(user_name: str, income: int):
    """월 소득 저장"""
    sb = get_supabase()
    sb.table(TB_USERS).upsert(
        {"user_name": user_name, "income": income},
        on_conflict="user_name"
    ).execute()


# ══════════════════════════════════════════
# 🏦 대출
# ══════════════════════════════════════════
def load_loans(user_name: str) -> list:
    """대출 목록 불러오기"""
    sb = get_supabase()
    result = sb.table(TB_LOANS).select("*").eq("user_name", user_name).execute()
    return result.data or []

def save_loan(user_name: str, loan: dict):
    """대출 추가"""
    sb = get_supabase()
    sb.table(TB_LOANS).insert({
        "user_name":          user_name,
        "name":               loan["name"],
        "original_principal": int(loan["original_principal"]),
        "current_principal":  int(loan["current_principal"]),
        "rate":               float(loan["rate"]),
        "original_months":    int(loan["original_months"]),
        "remaining_months":   int(loan["remaining_months"]),
        "monthly_payment":    int(loan["monthly_payment"]),
        "prepayments":        loan.get("prepayments", [])
    }).execute()

def update_loan(loan_id: str, loan: dict):
    """중도상환 후 대출 정보 업데이트"""
    sb = get_supabase()
    sb.table(TB_LOANS).update({
        "current_principal": int(loan["current_principal"]),
        "remaining_months":  int(loan["remaining_months"]),
        "monthly_payment":   int(loan["monthly_payment"]),
        "prepayments":       loan.get("prepayments", [])
    }).eq("id", loan_id).execute()

def delete_loan(loan_id: str):
    """대출 삭제"""
    sb = get_supabase()
    sb.table(TB_LOANS).delete().eq("id", loan_id).execute()


# ══════════════════════════════════════════
# 🔌 공과금
# ══════════════════════════════════════════
def load_utilities(user_name: str) -> dict:
    """공과금 불러오기"""
    sb = get_supabase()
    result = sb.table(TB_UTILITIES).select("*").eq("user_name", user_name).execute()
    # 기본값 세팅
    default = {
        "전기세": 0, "가스비": 0, "수도세": 0,
        "인터넷": 0, "핸드폰": 0, "관리비": 0
    }
    if result.data:
        for row in result.data:
            default[row["category"]] = row["amount"]
    return default

def save_utility(user_name: str, category: str, amount: int):
    """공과금 저장 — 있으면 업데이트, 없으면 삽입"""
    sb = get_supabase()
    existing = sb.table(TB_UTILITIES).select("id") \
        .eq("user_name", user_name) \
        .eq("category", category) \
        .execute()

    if existing.data:
        sb.table(TB_UTILITIES).update({"amount": amount}) \
            .eq("user_name", user_name) \
            .eq("category", category) \
            .execute()
    else:
        sb.table(TB_UTILITIES).insert({
            "user_name": user_name,
            "category":  category,
            "amount":    amount
        }).execute()

def delete_utility(user_name: str, category: str):
    """공과금 항목 삭제 (직접 추가한 항목용)"""
    sb = get_supabase()
    sb.table(TB_UTILITIES).delete() \
        .eq("user_name", user_name) \
        .eq("category", category) \
        .execute()


# ══════════════════════════════════════════
# 📱 구독 서비스
# ══════════════════════════════════════════
def load_subscriptions(user_name: str) -> list:
    """구독 목록 불러오기"""
    sb = get_supabase()
    result = sb.table(TB_SUBSCRIPTIONS).select("*").eq("user_name", user_name).execute()
    return result.data or []

def save_subscription(user_name: str, sub: dict):
    """구독 추가"""
    sb = get_supabase()
    sb.table(TB_SUBSCRIPTIONS).insert({
        "user_name": user_name,
        "name":      sub["name"],
        "amount":    int(sub["amount"]),
        "note":      sub.get("note", "")
    }).execute()

def delete_subscription(sub_id: str):
    """구독 삭제"""
    sb = get_supabase()
    sb.table(TB_SUBSCRIPTIONS).delete().eq("id", sub_id).execute()


# ══════════════════════════════════════════
# 📋 기타 고정비
# ══════════════════════════════════════════
def load_etc_fixed(user_name: str) -> list:
    """기타 고정비 불러오기"""
    sb = get_supabase()
    result = sb.table(TB_ETC).select("*").eq("user_name", user_name).execute()
    return result.data or []

def save_etc_fixed(user_name: str, item: dict):
    """기타 고정비 추가"""
    sb = get_supabase()
    sb.table(TB_ETC).insert({
        "user_name": user_name,
        "name":      item["name"],
        "amount":    int(item["amount"]),
        "note":      item.get("note", "")
    }).execute()

def delete_etc_fixed(item_id: str):
    """기타 고정비 삭제"""
    sb = get_supabase()
    sb.table(TB_ETC).delete().eq("id", item_id).execute()


# ══════════════════════════════════════════
# 🗑️ 전체 초기화
# ══════════════════════════════════════════
def delete_all_data(user_name: str):
    """해당 사용자의 모든 데이터 삭제"""
    sb = get_supabase()
    sb.table(TB_LOANS).delete().eq("user_name", user_name).execute()
    sb.table(TB_UTILITIES).delete().eq("user_name", user_name).execute()
    sb.table(TB_SUBSCRIPTIONS).delete().eq("user_name", user_name).execute()
    sb.table(TB_ETC).delete().eq("user_name", user_name).execute()
    sb.table(TB_USERS).update({"income": 0}).eq("user_name", user_name).execute()
