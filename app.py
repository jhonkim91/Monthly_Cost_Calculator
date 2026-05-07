import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO
import json
import math
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

# ─────────────────────────────────────────
# 대출 계산 상수 & 함수
# ─────────────────────────────────────────
METHOD_EQUAL_PAYMENT   = "원리금균등상환"
METHOD_EQUAL_PRINCIPAL = "원금균등상환"
METHOD_BULLET          = "만기일시상환"
REPAY_METHODS = [METHOD_EQUAL_PAYMENT, METHOD_EQUAL_PRINCIPAL, METHOD_BULLET]

LENDER_LIST = [
    "직접입력",
    "── 시중은행 ──",
    "KB국민은행", "신한은행", "하나은행", "우리은행",
    "NH농협은행", "IBK기업은행", "SC제일은행", "씨티은행",
    "── 인터넷은행 ──",
    "카카오뱅크", "케이뱅크", "토스뱅크",
    "── 저축은행 ──",
    "SBI저축은행", "OK저축은행", "웰컴저축은행",
    "── 보험/카드사 ──",
    "삼성생명", "한화생명", "교보생명",
    "삼성카드", "현대카드", "롯데카드",
    "── 정책금융 ──",
    "주택도시기금", "한국장학재단", "신용보증기금",
    "── 기타 ──",
    "새마을금고", "신협", "우체국", "기타"
]

def calc_equal_payment(principal, annual_rate, months):
    if months <= 0: return 0.0
    if annual_rate == 0: return principal / months
    r = annual_rate / 100 / 12
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)

def calc_equal_principal(principal, annual_rate, months, current_month=1):
    monthly_principal = principal / months
    r = annual_rate / 100 / 12
    remaining = principal - monthly_principal * (current_month - 1)
    interest = remaining * r
    return {
        "monthly_principal": monthly_principal,
        "interest": interest,
        "total": monthly_principal + interest,
        "remaining": remaining - monthly_principal
    }

def calc_bullet(principal, annual_rate):
    return principal * (annual_rate / 100 / 12)

def calc_loan_status(loan):
    start_date = datetime.strptime(loan["start_date"], "%Y-%m-%d").date()
    today = date.today()
    diff = relativedelta(today, start_date)
    elapsed_months = min(
        diff.years * 12 + diff.months,
        loan["original_months"]
    )
    principal   = loan["original_principal"]
    annual_rate = loan["rate"]
    method      = loan.get("repay_method", METHOD_EQUAL_PAYMENT)
    r           = annual_rate / 100 / 12

    total_paid_principal = 0.0
    total_paid_interest  = 0.0
    current_balance      = float(principal)

    prepayments  = sorted(
        loan.get("prepayments", []), key=lambda x: x["date"]
    )
    prepay_index = 0

    for month in range(1, elapsed_months + 1):
        cur_date = (start_date + relativedelta(months=month)).isoformat()
        while prepay_index < len(prepayments):
            pp = prepayments[prepay_index]
            if pp["date"] <= cur_date:
                current_balance = max(0, current_balance - pp["amount"])
                prepay_index += 1
            else:
                break

        if current_balance <= 0:
            break

        remaining_m = loan["original_months"] - month + 1

        if method == METHOD_EQUAL_PAYMENT:
            if remaining_m <= 0: break
            mp = calc_equal_payment(current_balance, annual_rate, remaining_m)
            interest_part  = current_balance * r
            principal_part = min(mp - interest_part, current_balance)

        elif method == METHOD_EQUAL_PRINCIPAL:
            principal_part = principal / loan["original_months"]
            interest_part  = current_balance * r

        else:
            interest_part  = current_balance * r
            principal_part = (current_balance
                              if month == loan["original_months"] else 0.0)

        total_paid_principal += principal_part
        total_paid_interest  += interest_part
        current_balance       = max(0, current_balance - principal_part)

    remaining_months = max(0, loan["original_months"] - elapsed_months)

    if current_balance <= 0:
        current_monthly = 0.0
    elif method == METHOD_EQUAL_PAYMENT:
        current_monthly = calc_equal_payment(
            current_balance, annual_rate, max(1, remaining_months)
        )
    elif method == METHOD_EQUAL_PRINCIPAL:
        current_monthly = (
            principal / loan["original_months"] + current_balance * r
        )
    else:
        current_monthly = calc_bullet(current_balance, annual_rate)

    return {
        "elapsed_months":       elapsed_months,
        "remaining_months":     remaining_months,
        "current_balance":      current_balance,
        "total_paid_principal": total_paid_principal,
        "total_paid_interest":  total_paid_interest,
        "current_monthly":      current_monthly,
        "start_date":           start_date,
        "today":                today,
    }

def generate_schedule(loan, max_months=None):
    principal   = loan["current_principal"]
    annual_rate = loan["rate"]
    months      = loan["remaining_months"]
    method      = loan.get("repay_method", METHOD_EQUAL_PAYMENT)
    r           = annual_rate / 100 / 12
    if max_months:
        months = min(months, max_months)

    schedule = []
    balance  = float(principal)
    orig_mp  = (float(loan["original_principal"]) / loan["original_months"]
                if method == METHOD_EQUAL_PRINCIPAL else 0)

    for mo in range(1, months + 1):
        if balance <= 0: break
        rem = loan["remaining_months"] - mo + 1

        if method == METHOD_EQUAL_PAYMENT:
            mp             = calc_equal_payment(balance, annual_rate, max(1, rem))
            interest_part  = balance * r
            principal_part = min(mp - interest_part, balance)

        elif method == METHOD_EQUAL_PRINCIPAL:
            principal_part = orig_mp
            interest_part  = balance * r
            mp             = principal_part + interest_part

        else:
            interest_part  = balance * r
            principal_part = balance if mo == months else 0.0
            mp             = interest_part + principal_part

        balance -= principal_part
        balance  = max(0, balance)

        schedule.append({
            "회차":     f"{mo}회",
            "월 납입금": mp,
            "원금":     principal_part,
            "이자":     interest_part,
            "잔여 원금": balance
        })
    return schedule

# ─────────────────────────────────────────
# DB & 인증 import
# ─────────────────────────────────────────
from database import (
    load_user, save_income,
    load_loans, save_loan, update_loan, delete_loan,
    load_utilities, save_utility, delete_utility,
    load_subscriptions, save_subscription, delete_subscription,
    load_etc_fixed, save_etc_fixed, delete_etc_fixed,
    delete_all_data
)
from auth import is_logged_in, get_current_user, logout
from login_page import show_login_page

# ─────────────────────────────────────────
# 로그인 게이트
# ─────────────────────────────────────────
if not is_logged_in():
    show_login_page()
    st.stop()

# ─────────────────────────────────────────
# 이 아래부터는 로그인된 사용자만 접근 가능
# ─────────────────────────────────────────

# ─────────────────────────────────────────
# 페이지 기본 설정
# ─────────────────────────────────────────
st.set_page_config(
    page_title="월 고정비용 계산기",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────
# CSS 스타일링
# ─────────────────────────────────────────
st.markdown("""
<style>
/* ── 전체 레이아웃 ── */
.main .block-container {
    padding: 1rem 1rem 2rem 1rem !important;
    max-width: 100% !important;
}

/* ── 모바일 폰트 크기 ── */
@media (max-width: 768px) {
    h1 { font-size: 1.4rem !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1.0rem !important; }
    .metric-value { font-size: 1.2rem !important; }

    /* 모바일에서 컬럼 세로 배치 */
    [data-testid="column"] {
        width: 100% !important;
        flex: 100% !important;
        min-width: 100% !important;
    }

    /* 버튼 풀 너비 */
    .stButton > button {
        width: 100% !important;
        padding: 0.6rem !important;
        font-size: 0.95rem !important;
    }

    /* 입력창 여백 */
    .stTextInput input,
    .stNumberInput input,
    .stSelectbox select {
        font-size: 1rem !important;
        padding: 0.5rem !important;
    }

    /* 탭 버튼 */
    .stTabs [data-baseweb="tab"] {
        font-size: 0.8rem !important;
        padding: 6px 8px !important;
    }

    /* 사이드바 숨기기 옵션 */
    [data-testid="stSidebar"] {
        min-width: 0 !important;
    }
}

/* ── 카드 스타일 ── */
.metric-card {
    background: white;
    padding: 0.8rem;
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    text-align: center;
    margin: 4px;
}
.metric-value {
    font-size: 1.6rem;
    font-weight: bold;
    color: #1f77b4;
}
.metric-label {
    font-size: 0.85rem;
    color: #888;
}

/* ── 색상 클래스 ── */
.danger  { color: #e74c3c !important; }
.warning { color: #f39c12 !important; }
.success { color: #27ae60 !important; }

/* ── 탭 스타일 ── */
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [data-baseweb="tab"] {
    background: #e8f4fd;
    border-radius: 8px 8px 0 0;
    font-weight: bold;
}

/* ── 구분선 여백 ── */
hr { margin: 0.8rem 0 !important; }

/* ── expander 스타일 ── */
.streamlit-expanderHeader {
    font-weight: bold;
    font-size: 0.95rem;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# 세션 상태 초기화
# ─────────────────────────────────────────
def init_session():
    if "user_loaded" not in st.session_state:
        st.session_state.user_loaded = False
    if "current_user" not in st.session_state:
        st.session_state.current_user = None
    if "income" not in st.session_state:
        st.session_state.income = 0
    if "loans" not in st.session_state:
        st.session_state.loans = []
    if "utilities" not in st.session_state:
        st.session_state.utilities = {
            "전기세": 0, "가스비": 0, "수도세": 0,
            "인터넷": 0, "핸드폰": 0, "관리비": 0
        }
    if "subscriptions" not in st.session_state:
        st.session_state.subscriptions = []
    if "etc_fixed" not in st.session_state:
        st.session_state.etc_fixed = []

    # 로그인된 유저가 있고 아직 DB 로드 안 했으면 불러오기
    if st.session_state.current_user and not st.session_state.user_loaded:
        uname = st.session_state.current_user
        user  = load_user(uname)
        st.session_state.income        = user.get("income", 0)
        st.session_state.loans         = load_loans(uname)
        st.session_state.utilities     = load_utilities(uname)
        st.session_state.subscriptions = load_subscriptions(uname)
        st.session_state.etc_fixed     = load_etc_fixed(uname)
        st.session_state.user_loaded   = True

init_session()

# ─────────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────────
def calc_monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    """원리금균등상환 월 납입금 계산"""
    if annual_rate == 0:
        return principal / months if months > 0 else 0
    r = annual_rate / 100 / 12  # 월이자율
    if months == 0:
        return 0
    payment = principal * r * (1 + r) ** months / ((1 + r) ** months - 1)
    return payment

def format_currency(amount: float) -> str:
    """금액 포맷"""
    return f"₩{amount:,.0f}"

def get_total_loans():
    return sum(loan["monthly_payment"] for loan in st.session_state.loans)

def get_total_utilities():
    return sum(st.session_state.utilities.values())

def get_total_subscriptions():
    return sum(sub["amount"] for sub in st.session_state.subscriptions)

def get_total_etc():
    return sum(item["amount"] for item in st.session_state.etc_fixed)

def get_grand_total():
    return get_total_loans() + get_total_utilities() + get_total_subscriptions() + get_total_etc()

# ─────────────────────────────────────────
# 사이드바 — 월 소득 입력
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("## 👤 내 계정")
    st.success(f"✅ {get_current_user()}")

    if st.button("🚪 로그아웃", use_container_width=True):
        logout()
        st.rerun()

    st.divider()

    st.markdown("## 👤 기본 정보")
    name = st.text_input("이름 (선택)", placeholder="홍길동")
    month = st.selectbox("기준 월", [f"{i}월" for i in range(1, 13)],
                         index=datetime.now().month - 1)
    year = st.number_input("기준 연도", min_value=2020, max_value=2030,
                           value=datetime.now().year)

    st.divider()
    st.markdown("## 💵 월 소득")
    st.session_state.income = st.number_input(
        "세후 월 소득 (원)", min_value=0,
        value=st.session_state.income,
        step=10000, format="%d"
    )

    total  = get_grand_total()
    income = st.session_state.income
    ratio  = (total / income * 100) if income > 0 else 0

    st.divider()
    st.markdown("## 📊 빠른 요약")

    color = "danger" if ratio > 60 else "warning" if ratio > 40 else "success"
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">총 고정비</div>
        <div class="metric-value">{format_currency(total)}</div>
    </div>
    """, unsafe_allow_html=True)

    if income > 0:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">소득 대비 고정비 비율</div>
            <div class="metric-value {color}">{ratio:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

        if ratio > 60:
            st.error("⚠️ 고정비 비율이 60%를 초과했습니다!")
        elif ratio > 40:
            st.warning("💡 고정비 비율이 높습니다. 점검이 필요해요.")
        else:
            st.success("✅ 고정비 비율이 양호합니다!")


# ─────────────────────────────────────────
# 메인 헤더
# ─────────────────────────────────────────
st.markdown("""
<div style='text-align:center; padding: 1rem 0;'>
    <h1>💰 월 고정비용 계산기</h1>
    <p style='color:#666;'>대출 · 공과금 · 구독 서비스 · 기타 고정비를 한 눈에 관리하세요</p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
# 탭 구성
# ─────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 대시보드", "🏦 대출 관리", "🔌 공과금 & 구독", "📁 저장 & 내보내기"
])

# ══════════════════════════════════════════
# TAB 1: 대시보드
# ══════════════════════════════════════════
with tab1:
    st.markdown(f"### 📅 {year}년 {month} 고정비 현황")

    # KPI 카드 4개
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🏦 대출 상환", format_currency(get_total_loans()),
                  delta=f"총 {len(st.session_state.loans)}건")
    with col2:
        st.metric("🔌 공과금", format_currency(get_total_utilities()))
    with col3:
        st.metric("📱 구독 서비스", format_currency(get_total_subscriptions()),
                  delta=f"총 {len(st.session_state.subscriptions)}건")
    with col4:
        st.metric("📋 기타 고정비", format_currency(get_total_etc()))

    st.divider()

    col_left, col_right = st.columns([1, 1])

    with col_left:
        # 도넛 차트
        categories = ["대출 상환", "공과금", "구독 서비스", "기타 고정비"]
        values = [get_total_loans(), get_total_utilities(),
                  get_total_subscriptions(), get_total_etc()]

        if sum(values) > 0:
            fig_pie = px.pie(
                values=values,
                names=categories,
                title="📌 고정비 항목별 비중",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie.update_layout(showlegend=True, height=380)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("💡 항목을 입력하면 차트가 표시됩니다.")

    with col_right:
        # 소득 vs 고정비 게이지
        if st.session_state.income > 0:
            remaining = st.session_state.income - get_grand_total()
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=ratio,
                title={"text": "소득 대비 고정비 비율 (%)"},
                delta={"reference": 40, "valueformat": ".1f"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "#1f77b4"},
                    "steps": [
                        {"range": [0, 40], "color": "#d4edda"},
                        {"range": [40, 60], "color": "#fff3cd"},
                        {"range": [60, 100], "color": "#f8d7da"},
                    ],
                    "threshold": {
                        "line": {"color": "red", "width": 4},
                        "thickness": 0.75,
                        "value": 60
                    }
                }
            ))
            fig_gauge.update_layout(height=380)
            st.plotly_chart(fig_gauge, use_container_width=True)
            st.metric("💸 가처분 소득 (월)", format_currency(remaining))
        else:
            st.info("💡 사이드바에서 월 소득을 입력하면 비율 게이지가 표시됩니다.")

    # 상세 내역 테이블
    st.divider()
    st.markdown("#### 📋 전체 고정비 내역")
    
    all_items = []
    for loan in st.session_state.loans:
        all_items.append({"카테고리": "🏦 대출", "항목": loan["name"],
                          "월 금액 (원)": loan["monthly_payment"],
                          "비고": f"잔여 {loan['remaining_months']}개월"})
    for k, v in st.session_state.utilities.items():
        if v > 0:
            all_items.append({"카테고리": "🔌 공과금", "항목": k,
                              "월 금액 (원)": v, "비고": "-"})
    for sub in st.session_state.subscriptions:
        all_items.append({"카테고리": "📱 구독", "항목": sub["name"],
                          "월 금액 (원)": sub["amount"], "비고": sub.get("note", "-")})
    for etc in st.session_state.etc_fixed:
        all_items.append({"카테고리": "📋 기타", "항목": etc["name"],
                          "월 금액 (원)": etc["amount"], "비고": etc.get("note", "-")})

    if all_items:
        df = pd.DataFrame(all_items)
        df["월 금액 (원)"] = df["월 금액 (원)"].apply(lambda x: f"₩{x:,.0f}")
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        st.markdown(f"""
        <div style='text-align:right; font-size:1.3rem; font-weight:bold; 
                    padding: 0.5rem; background:#eaf4fb; border-radius:8px;'>
            합계: {format_currency(get_grand_total())}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("📝 아직 입력된 항목이 없습니다. 각 탭에서 항목을 추가해보세요!")


# ══════════════════════════════════════════
# TAB 2: 대출 관리 — 전체 교체
# ══════════════════════════════════════════
with tab2:
    st.markdown("### 🏦 대출 관리")

    # ── 대출 추가 폼 ──────────────────────────
    with st.expander("➕ 대출 항목 추가",
                     expanded=len(st.session_state.loans) == 0):

        # 1행 — 대출명 / 금융기관
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            loan_name = st.text_input("대출명",
                                      placeholder="예: 전세자금대출",
                                      key="loan_name_input")
        with r1c2:
            lender_select = st.selectbox("금융기관", LENDER_LIST,
                                          key="lender_select")
            if lender_select == "직접입력" or lender_select.startswith("──"):
                lender_custom = st.text_input("금융기관 직접입력",
                                              key="lender_custom",
                                              placeholder="예: OO캐피탈")
                lender = lender_custom
            else:
                lender = lender_select

        # 2행 — 상환방식 / 대출 시작일
        r2c1, r2c2 = st.columns(2)
        with r2c1:
            repay_method = st.selectbox(
                "상환 방식",
                REPAY_METHODS,
                key="repay_method",
                help="원리금균등: 매월 동일 납입 | 원금균등: 초기 납입 높고 점점 감소 | 만기일시: 매월 이자만, 만기에 원금 전액"
            )
        with r2c2:
            start_date = st.date_input("대출 시작일",
                                        value=date.today(),
                                        key="loan_start_date")

        # 3행 — 원금 / 금리 / 기간
        r3c1, r3c2, r3c3 = st.columns(3)
        with r3c1:
            loan_principal = st.number_input(
                "최초 대출 원금 (원)",
                min_value=0, step=100000, format="%d",
                key="loan_principal"
            )
        with r3c2:
            loan_rate = st.number_input(
                "연 금리 (%)",
                min_value=0.0, max_value=50.0,
                value=4.5, step=0.1, format="%.2f",
                key="loan_rate"
            )
        with r3c3:
            loan_months = st.number_input(
                "총 상환 기간 (개월)",
                min_value=1, max_value=480,
                value=120, step=1,
                key="loan_months"
            )

        # 미리보기
        if loan_principal > 0:
            if repay_method == METHOD_EQUAL_PAYMENT:
                preview = calc_equal_payment(loan_principal,
                                              loan_rate, loan_months)
                st.info(f"📌 월 납입금 (원리금균등): **{format_currency(preview)}**")

            elif repay_method == METHOD_EQUAL_PRINCIPAL:
                first  = calc_equal_principal(loan_principal,
                                               loan_rate, loan_months, 1)
                last_m = calc_equal_principal(loan_principal,
                                               loan_rate, loan_months,
                                               loan_months)
                st.info(
                    f"📌 원금균등 — "
                    f"첫 달: **{format_currency(first['total'])}** / "
                    f"마지막 달: **{format_currency(last_m['total'])}**"
                )
            else:
                monthly_interest = calc_bullet(loan_principal, loan_rate)
                st.info(
                    f"📌 만기일시 — "
                    f"매월 이자: **{format_currency(monthly_interest)}** / "
                    f"만기 상환 원금: **{format_currency(loan_principal)}**"
                )

        if st.button("✅ 대출 추가", key="add_loan", type="primary"):
            if not loan_name:
                st.error("대출명을 입력해주세요.")
            elif loan_principal <= 0:
                st.error("대출 원금을 입력해주세요.")
            else:
                if repay_method == METHOD_EQUAL_PAYMENT:
                    monthly = calc_equal_payment(loan_principal,
                                                  loan_rate, loan_months)
                elif repay_method == METHOD_EQUAL_PRINCIPAL:
                    first   = calc_equal_principal(loan_principal,
                                                    loan_rate, loan_months, 1)
                    monthly = first["total"]
                else:
                    monthly = calc_bullet(loan_principal, loan_rate)

                new_loan = {
                    "name":               loan_name,
                    "lender":             lender,
                    "repay_method":       repay_method,
                    "start_date":         str(start_date),
                    "original_principal": loan_principal,
                    "current_principal":  loan_principal,
                    "rate":               loan_rate,
                    "original_months":    loan_months,
                    "remaining_months":   loan_months,
                    "monthly_payment":    monthly,
                    "prepayments":        []
                }
                st.session_state.loans.append(new_loan)
                if st.session_state.get("current_user"):
                    save_loan(st.session_state.current_user, new_loan)
                st.success(f"✅ '{loan_name}' 추가 완료!")
                st.rerun()

    # ── 등록된 대출 목록 ──────────────────────
    if st.session_state.loans:
        for i, loan in enumerate(st.session_state.loans):

            # 현재 날짜 기준 실시간 현황 계산
            if loan.get("start_date"):
                status = calc_loan_status(loan)
                # 세션 값 자동 업데이트
                loan["current_principal"] = status["current_balance"]
                loan["remaining_months"]  = status["remaining_months"]
                loan["monthly_payment"]   = status["current_monthly"]
            else:
                status = None

            method_icon = {"원리금균등상환": "📊",
                           "원금균등상환":   "📉",
                           "만기일시상환":   "🏁"}.get(
                loan.get("repay_method", ""), "📊")

            st.markdown(f"---")
            st.markdown(
                f"#### {method_icon} {loan['name']} "
                f"<span style='font-size:0.8rem; color:#888; "
                f"background:#f0f0f0; padding:2px 8px; "
                f"border-radius:10px;'>"
                f"{loan.get('lender','미입력')} · "
                f"{loan.get('repay_method','')}</span>",
                unsafe_allow_html=True
            )

            # ── 현재 날짜 기준 현황 카드 ──────────
            if status:
                elapsed = status["elapsed_months"]
                remaining = status["remaining_months"]
                progress = elapsed / loan["original_months"] \
                           if loan["original_months"] > 0 else 0

                # 진행률 바
                st.markdown(f"""
                <div style='margin:8px 0;'>
                    <div style='display:flex; justify-content:space-between;
                                font-size:0.85rem; color:#666;'>
                        <span>🗓️ 시작: {status['start_date']}</span>
                        <span>📅 오늘: {status['today']}</span>
                    </div>
                    <div style='background:#e0e0e0; border-radius:10px;
                                height:12px; margin:4px 0;'>
                        <div style='background:linear-gradient(90deg,#1f77b4,#2ecc71);
                                    width:{min(progress*100, 100):.1f}%;
                                    height:12px; border-radius:10px;'></div>
                    </div>
                    <div style='display:flex; justify-content:space-between;
                                font-size:0.85rem; color:#666;'>
                        <span>경과 {elapsed}개월</span>
                        <span>잔여 {remaining}개월</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # 지표 5개
                mc1, mc2, mc3, mc4, mc5 = st.columns(5)
                mc1.metric("💳 이번 달 납입금",
                           format_currency(status["current_monthly"]))
                mc2.metric("📦 현재 잔여 원금",
                           format_currency(status["current_balance"]))
                mc3.metric("💸 납입한 이자",
                           format_currency(status["total_paid_interest"]))
                mc4.metric("✅ 상환한 원금",
                           format_currency(status["total_paid_principal"]))
                mc5.metric("⏳ 잔여 기간",
                           f"{remaining}개월")

            else:
                # start_date 없는 구버전 대출
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("💳 월 납입금",
                           format_currency(loan["monthly_payment"]))
                mc2.metric("📦 잔여 원금",
                           format_currency(loan["current_principal"]))
                mc3.metric("⏳ 잔여 기간",
                           f"{loan['remaining_months']}개월")

            # ── 중도 상환 ──────────────────────────
            with st.expander(f"💰 중도 상환 입력"):
                import math as _math
                pp1, pp2 = st.columns(2)
                with pp1:
                    prepay_amount = st.number_input(
                        "중도 상환 금액 (원)",
                        min_value=0,
                        max_value=int(loan["current_principal"]),
                        step=100000, format="%d",
                        key=f"prepay_amount_{i}"
                    )
                    prepay_date = st.date_input(
                        "중도 상환일",
                        value=date.today(),
                        key=f"prepay_date_{i}"
                    )
                with pp2:
                    prepay_type = st.radio(
                        "중도 상환 후 선택",
                        ["💳 납입금 감소 (기간 유지)",
                         "⏳ 기간 단축 (납입금 유지)"],
                        key=f"prepay_type_{i}"
                    )
                    prepay_fee_rate = st.number_input(
                        "중도 상환 수수료율 (%)",
                        min_value=0.0, max_value=5.0,
                        value=1.2, step=0.1, format="%.1f",
                        key=f"prepay_fee_{i}"
                    )

                if prepay_amount > 0:
                    fee = prepay_amount * prepay_fee_rate / 100
                    new_p = loan["current_principal"] - prepay_amount
                    if "납입금 감소" in prepay_type:
                        new_mp = calc_equal_payment(
                            new_p, loan["rate"], loan["remaining_months"])
                        st.success(
                            f"수수료: **{format_currency(fee)}** | "
                            f"새 월납입금: **{format_currency(new_mp)}**"
                        )
                    else:
                        if loan["rate"] > 0:
                            r = loan["rate"] / 100 / 12
                            new_m = _math.ceil(
                                -_math.log(
                                    1 - new_p * r / loan["monthly_payment"]
                                ) / _math.log(1 + r)
                            ) if loan["monthly_payment"] > new_p * r else 1
                        else:
                            new_m = _math.ceil(
                                new_p / loan["monthly_payment"]
                            )
                        saved = loan["remaining_months"] - new_m
                        st.success(
                            f"수수료: **{format_currency(fee)}** | "
                            f"새 잔여기간: **{new_m}개월** "
                            f"(↓{saved}개월 단축)"
                        )

                if st.button("✅ 중도 상환 확정",
                             key=f"apply_prepay_{i}", type="primary"):
                    if prepay_amount > 0:
                        import math as _math
                        fee    = prepay_amount * prepay_fee_rate / 100
                        new_p  = loan["current_principal"] - prepay_amount
                        loan["prepayments"].append({
                            "date":             str(prepay_date),
                            "amount":           prepay_amount,
                            "fee":              fee,
                            "type":             prepay_type,
                            "before_principal": loan["current_principal"],
                            "before_monthly":   loan["monthly_payment"],
                        })
                        loan["current_principal"] = new_p
                        if "납입금 감소" in prepay_type:
                            loan["monthly_payment"] = calc_equal_payment(
                                new_p, loan["rate"],
                                loan["remaining_months"])
                        else:
                            if loan["rate"] > 0:
                                r = loan["rate"] / 100 / 12
                                loan["remaining_months"] = _math.ceil(
                                    -_math.log(
                                        1 - new_p * r / loan["monthly_payment"]
                                    ) / _math.log(1 + r)
                                )
                        if loan.get("id") and st.session_state.get("current_user"):
                            update_loan(loan["id"], loan)
                        st.rerun()

            # ── 상환 스케줄 ────────────────────────
            with st.expander(f"📅 상환 스케줄 (향후 12개월)"):
                schedule = generate_schedule(loan, max_months=12)
                if schedule:
                    df_sch = pd.DataFrame(schedule)
                    for col in ["월 납입금", "원금", "이자", "잔여 원금"]:
                        df_sch[col] = df_sch[col].apply(
                            lambda x: f"₩{x:,.0f}")
                    st.dataframe(df_sch, use_container_width=True,
                                 hide_index=True)

            # ── 중도 상환 이력 ─────────────────────
            if loan.get("prepayments"):
                with st.expander(
                    f"📜 중도 상환 이력 ({len(loan['prepayments'])}건)"
                ):
                    hist = []
                    for p in loan["prepayments"]:
                        hist.append({
                            "날짜":          p["date"],
                            "상환금액":      format_currency(p["amount"]),
                            "수수료":        format_currency(p["fee"]),
                            "방식":          "납입금감소"
                                             if "납입금" in p["type"]
                                             else "기간단축",
                            "상환전 원금":   format_currency(
                                             p["before_principal"]),
                        })
                    st.dataframe(pd.DataFrame(hist),
                                 use_container_width=True,
                                 hide_index=True)

            # ── 삭제 ───────────────────────────────
            if st.button(f"🗑️ '{loan['name']}' 삭제",
                         key=f"del_loan_{i}"):
                if loan.get("id") and st.session_state.get("current_user"):
                    delete_loan(loan["id"])
                st.session_state.loans.pop(i)
                st.rerun()

        st.divider()
        st.markdown(
            f"<div style='text-align:right; font-size:1.2rem; "
            f"font-weight:bold; color:#1f77b4;'>"
            f"대출 합계: {format_currency(get_total_loans())} / 월"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.info("📝 아직 등록된 대출이 없습니다.")

# ══════════════════════════════════════════
# TAB 3: 공과금 & 구독
# ══════════════════════════════════════════
with tab3:
    st.markdown("### 🔌 공과금 & 구독 서비스")

    # 공과금
    st.markdown("#### 🏠 공과금")
    cols = st.columns(3)
    utility_icons = {
        "전기세": "⚡", "가스비": "🔥", "수도세": "💧",
        "인터넷": "🌐", "핸드폰": "📱", "관리비": "🏢"
    }
    for idx, (key, icon) in enumerate(utility_icons.items()):
        with cols[idx % 3]:
            st.session_state.utilities[key] = st.number_input(
                f"{icon} {key} (원)", min_value=0,
                value=st.session_state.utilities[key],
                step=1000, format="%d", key=f"util_{key}"
            )

    # 기타 공과금 추가
    with st.expander("➕ 공과금 직접 추가"):
        uc1, uc2, uc3 = st.columns([2, 2, 1])
        with uc1:
            new_util_name = st.text_input("항목명", key="new_util_name",
                                          placeholder="예: TV수신료")
        with uc2:
            new_util_amount = st.number_input("금액 (원)", min_value=0,
                                              step=1000, format="%d",
                                              key="new_util_amount")
        with uc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("추가", key="add_util"):
                if new_util_name and new_util_amount > 0:
                    st.session_state.utilities[new_util_name] = new_util_amount
                    st.rerun()

    st.markdown(f"**공과금 소계: {format_currency(get_total_utilities())}**")

    st.divider()

    # 구독 서비스
    st.markdown("#### 📱 구독 서비스")

    # 자주 쓰는 구독 서비스 프리셋
    preset_subs = {
        "Netflix": 17000, "YouTube Premium": 14900, "Spotify": 10900,
        "Coupang Rocket WOW": 7890, "Naver Plus": 4900, "Kakao": 3900,
        "Disney+": 13900, "Tving": 13900, "Wavve": 10900,
        "Apple Music": 10900, "ChatGPT Plus": 27000, "기타 구독": 0
    }

    with st.expander("➕ 구독 서비스 추가", expanded=True):
        sc1, sc2, sc3 = st.columns([2, 2, 2])
        with sc1:
            sub_name = st.selectbox("서비스 선택", ["직접 입력"] + list(preset_subs.keys()),
                                    key="sub_name_select")
        with sc2:
            if sub_name == "직접 입력":
                sub_name_custom = st.text_input("서비스명 입력", key="sub_name_custom")
                sub_amount = st.number_input("월 금액 (원)", min_value=0,
                                             step=100, format="%d", key="sub_amount_custom")
            else:
                sub_name_custom = sub_name
                sub_amount = st.number_input("월 금액 (원)", min_value=0,
                                             value=preset_subs[sub_name],
                                             step=100, format="%d", key="sub_amount_preset")
        with sc3:
            sub_note = st.text_input("메모 (선택)", key="sub_note",
                                     placeholder="예: 가족 요금제")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✅ 구독 추가", key="add_sub", type="primary"):
                name_to_add = sub_name_custom if sub_name == "직접 입력" else sub_name_custom
                if name_to_add and sub_amount > 0:
                    st.session_state.subscriptions.append({
                        "name": name_to_add,
                        "amount": sub_amount,
                        "note": sub_note
                    })
                    st.rerun()

    if st.session_state.subscriptions:
        for i, sub in enumerate(st.session_state.subscriptions):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            c1.write(f"📌 {sub['name']}")
            c2.write(format_currency(sub["amount"]))
            c3.write(sub.get("note", "-"))
            if c4.button("🗑️", key=f"del_sub_{i}"):
                st.session_state.subscriptions.pop(i)
                st.rerun()
        st.markdown(f"**구독 소계: {format_currency(get_total_subscriptions())}**")

    st.divider()

    # 기타 고정비
    st.markdown("#### 📋 기타 고정비")
    with st.expander("➕ 기타 고정비 추가"):
        ec1, ec2, ec3 = st.columns([2, 2, 1])
        with ec1:
            etc_name = st.text_input("항목명", key="etc_name",
                                     placeholder="예: 헬스장, 주차비, 보험료")
        with ec2:
            etc_amount = st.number_input("월 금액 (원)", min_value=0,
                                         step=1000, format="%d", key="etc_amount")
        with ec3:
            etc_note = st.text_input("메모", key="etc_note", placeholder="선택")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✅ 추가", key="add_etc"):
                if etc_name and etc_amount > 0:
                    st.session_state.etc_fixed.append({
                        "name": etc_name,
                        "amount": etc_amount,
                        "note": etc_note
                    })
                    st.rerun()

    if st.session_state.etc_fixed:
        for i, item in enumerate(st.session_state.etc_fixed):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            c1.write(f"📌 {item['name']}")
            c2.write(format_currency(item["amount"]))
            c3.write(item.get("note", "-"))
            if c4.button("🗑️", key=f"del_etc_{i}"):
                st.session_state.etc_fixed.pop(i)
                st.rerun()
        st.markdown(f"**기타 소계: {format_currency(get_total_etc())}**")

# ══════════════════════════════════════════
# TAB 4: 저장 & 내보내기
# ══════════════════════════════════════════
with tab4:
    st.markdown("### 📁 저장 & 내보내기")

    # CSV 내보내기
    st.markdown("#### 📥 CSV 다운로드")
    
    all_export = []
    for loan in st.session_state.loans:
        all_export.append({"카테고리": "대출", "항목": loan["name"],
                           "월 금액(원)": loan["monthly_payment"],
                           "비고": f"잔여 {loan['remaining_months']}개월 / 금리 {loan['rate']}%"})
    for k, v in st.session_state.utilities.items():
        if v > 0:
            all_export.append({"카테고리": "공과금", "항목": k,
                               "월 금액(원)": v, "비고": ""})
    for sub in st.session_state.subscriptions:
        all_export.append({"카테고리": "구독", "항목": sub["name"],
                           "월 금액(원)": sub["amount"],
                           "비고": sub.get("note", "")})
    for etc in st.session_state.etc_fixed:
        all_export.append({"카테고리": "기타", "항목": etc["name"],
                           "월 금액(원)": etc["amount"],
                           "비고": etc.get("note", "")})

    if all_export:
        df_export = pd.DataFrame(all_export)
        df_export.loc[len(df_export)] = ["", "[ 합 계 ]",
                                          get_grand_total(), ""]
        
        csv_buffer = StringIO()
        df_export.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
        
        st.download_button(
            label="📥 CSV 다운로드",
            data=csv_buffer.getvalue().encode("utf-8-sig"),
            file_name=f"월고정비_{year}_{month}.csv",
            mime="text/csv",
            type="primary"
        )
        st.dataframe(df_export, use_container_width=True, hide_index=True)
    else:
        st.info("내보낼 데이터가 없습니다. 먼저 항목을 입력해주세요.")

    st.divider()

    # JSON 저장 & 불러오기
    st.markdown("#### 💾 데이터 저장 / 불러오기 (JSON)")
    
    save_col, load_col = st.columns(2)
    
    with save_col:
        st.markdown("**💾 현재 데이터 저장**")
        save_data = {
            "income": st.session_state.income,
            "loans": st.session_state.loans,
            "utilities": st.session_state.utilities,
            "subscriptions": st.session_state.subscriptions,
            "etc_fixed": st.session_state.etc_fixed,
            "saved_at": datetime.now().isoformat()
        }
        json_str = json.dumps(save_data, ensure_ascii=False, indent=2)
        st.download_button(
            label="📦 JSON 저장",
            data=json_str.encode("utf-8"),
            file_name=f"월고정비_{year}_{month}.json",
            mime="application/json"
        )

    with load_col:
        st.markdown("**📂 저장된 데이터 불러오기**")
        uploaded = st.file_uploader("JSON 파일 업로드", type=["json"])
        if uploaded:
            try:
                loaded = json.load(uploaded)
                st.session_state.income = loaded.get("income", 0)
                st.session_state.loans = loaded.get("loans", [])
                st.session_state.utilities = loaded.get("utilities", {})
                st.session_state.subscriptions = loaded.get("subscriptions", [])
                st.session_state.etc_fixed = loaded.get("etc_fixed", [])
                st.success("✅ 데이터를 성공적으로 불러왔습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"파일 오류: {e}")

    st.divider()
    
    # 전체 초기화
    st.markdown("#### 🗑️ 데이터 초기화")
    if st.button("⚠️ 전체 초기화", type="secondary"):
        st.session_state.loans = []
        st.session_state.utilities = {
            "전기세": 0, "가스비": 0, "수도세": 0,
            "인터넷": 0, "핸드폰": 0, "관리비": 0
        }
        st.session_state.subscriptions = []
        st.session_state.income = 0
        st.session_state.etc_fixed = []
        st.success("초기화 완료!")
        st.rerun()
