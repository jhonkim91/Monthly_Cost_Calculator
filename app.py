import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO
import json
from datetime import datetime
# app.py 상단 — 기존 import 아래에 추가
from database import (
    load_user, save_income,
    load_loans, save_loan, update_loan, delete_loan,
    load_utilities, save_utility, delete_utility,
    load_subscriptions, save_subscription, delete_subscription,
    load_etc_fixed, save_etc_fixed, delete_etc_fixed,
    delete_all_data
)
# app.py 맨 위 import 아래에 추가
from auth import is_logged_in, get_current_user, logout
from login_page import show_login_page

# ─────────────────────────────────────────
# 로그인 게이트 — 로그인 안 됐으면 로그인 페이지만 표시
# ─────────────────────────────────────────
if not is_logged_in():
    show_login_page()
    st.stop()  # 로그인 전엔 나머지 앱 실행 안 됨

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
    .main { background-color: #f8f9fa; }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        text-align: center;
        margin: 5px;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: bold;
        color: #1f77b4;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #666;
    }
    .danger { color: #e74c3c !important; }
    .warning { color: #f39c12 !important; }
    .success { color: #27ae60 !important; }
    .section-header {
        background: linear-gradient(90deg, #1f77b4, #2ecc71);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #e8f4fd;
        border-radius: 8px 8px 0 0;
        font-weight: bold;
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
    # 로그인 정보 표시
    st.markdown("## 👤 내 계정")
    st.success(f"✅ {get_current_user()}")

    if st.button("🚪 로그아웃", use_container_width=True):
        logout()
        st.rerun()

    st.divider()
    # ... 이하 기존 사이드바 코드 유지
    st.markdown("## 🔐 사용자")

    input_name = st.text_input(
        "사용자 이름",
        placeholder="예: hong123",
        value=st.session_state.current_user or ""
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📂 불러오기", type="primary", use_container_width=True):
            if input_name.strip():
                st.session_state.current_user = input_name.strip()
                st.session_state.user_loaded  = False  # DB 재로드 트리거
                st.rerun()
            else:
                st.error("이름을 입력해주세요!")
    with col_b:
        if st.button("💾 저장", use_container_width=True):
            if st.session_state.current_user:
                save_income(st.session_state.current_user,
                            st.session_state.income)
                st.success("저장 완료!")
            else:
                st.warning("먼저 불러오기를 눌러주세요.")

    if st.session_state.current_user:
        st.success(f"✅ {st.session_state.current_user}")
    else:
        st.info("이름 입력 후 불러오기를 누르세요")
    st.markdown("## 👤 기본 정보")
    name = st.text_input("이름 (선택)", placeholder="홍길동")
    month = st.selectbox("기준 월", [f"{i}월" for i in range(1, 13)],
                         index=datetime.now().month - 1)
    year = st.number_input("기준 연도", min_value=2020, max_value=2030,
                           value=datetime.now().year)
    
    st.divider()
    st.markdown("## 💵 월 소득")
    st.session_state.income = st.number_input(
        "세후 월 소득 (원)", min_value=0, value=st.session_state.income,
        step=10000, format="%d"
    )
    
    total = get_grand_total()
    income = st.session_state.income
    ratio = (total / income * 100) if income > 0 else 0
    
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
# TAB 2: 대출 관리 (중도 상환 포함 버전)
# ══════════════════════════════════════════
with tab2:
    st.markdown("### 🏦 대출 관리")
    st.caption("원리금균등상환 방식 · 중도 상환 시 잔여 원금 기준으로 자동 재계산됩니다.")

    # ── 대출 추가 폼 ──────────────────────────
    with st.expander("➕ 대출 항목 추가", expanded=len(st.session_state.loans) == 0):
        c1, c2 = st.columns(2)
        with c1:
            loan_name = st.text_input("대출명", placeholder="예: 주택담보대출",
                                      key="loan_name_input")
            loan_principal = st.number_input("최초 대출 원금 (원)", min_value=0,
                                             step=100000, format="%d",
                                             key="loan_principal")
        with c2:
            loan_rate = st.number_input("연 금리 (%)", min_value=0.0,
                                        max_value=50.0, value=4.5,
                                        step=0.1, format="%.2f",
                                        key="loan_rate")
            loan_months = st.number_input("총 상환 개월 수", min_value=1,
                                          max_value=480, value=120,
                                          step=1, key="loan_months")

        if loan_principal > 0:
            preview = calc_monthly_payment(loan_principal, loan_rate, loan_months)
            st.info(f"📌 예상 월 납입금: **{format_currency(preview)}**")

        if st.button("✅ 대출 추가", key="add_loan", type="primary"):
            if not loan_name:
                st.error("대출명을 입력해주세요.")
            elif loan_principal <= 0:
                st.error("대출 잔액을 입력해주세요.")
            else:
                monthly = calc_monthly_payment(loan_principal, loan_rate, loan_months)
                st.session_state.loans.append({
                    "name": loan_name,
                    "original_principal": loan_principal,   # 최초 원금
                    "current_principal": loan_principal,    # 현재 잔여 원금
                    "rate": loan_rate,
                    "original_months": loan_months,         # 최초 개월
                    "remaining_months": loan_months,        # 잔여 개월
                    "monthly_payment": monthly,
                    "prepayments": []                        # 중도 상환 이력
                })
                st.success(f"✅ '{loan_name}' 추가! 월 납입금: {format_currency(monthly)}")
                st.rerun()

    # ── 등록된 대출 목록 ──────────────────────
    if st.session_state.loans:
        for i, loan in enumerate(st.session_state.loans):
            with st.container():
                st.markdown(f"---\n#### 🏦 {loan['name']}")

                # 핵심 지표 4개
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("💳 월 납입금",
                          format_currency(loan["monthly_payment"]))
                m2.metric("📦 잔여 원금",
                          format_currency(loan["current_principal"]),
                          delta=f"-{format_currency(loan['original_principal'] - loan['current_principal'])} 중도상환" 
                          if loan["original_principal"] != loan["current_principal"] else None,
                          delta_color="inverse")
                m3.metric("⏳ 잔여 기간", f"{loan['remaining_months']}개월")
                total_interest = (loan["monthly_payment"] * loan["remaining_months"]
                                  - loan["current_principal"])
                m4.metric("💸 남은 총 이자",
                          format_currency(max(0, total_interest)))

                # ── 중도 상환 입력 ──────────────────
                with st.expander(f"💰 '{loan['name']}' 중도 상환 입력"):
                    st.markdown("중도 상환 후 **납입금을 줄일지** vs **기간을 줄일지** 선택하세요.")

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
                            value=datetime.now().date(),
                            key=f"prepay_date_{i}"
                        )
                    with pp2:
                        prepay_type = st.radio(
                            "중도 상환 후 선택",
                            ["💳 납입금 감소 (기간 유지)", "⏳ 기간 단축 (납입금 유지)"],
                            key=f"prepay_type_{i}"
                        )
                        prepay_fee_rate = st.number_input(
                            "중도 상환 수수료율 (%)",
                            min_value=0.0, max_value=5.0,
                            value=1.2, step=0.1, format="%.1f",
                            key=f"prepay_fee_{i}",
                            help="보통 1~1.5%. 3년 이후 면제되는 경우 많음"
                        )

                    # 미리보기 계산
                    if prepay_amount > 0:
                        fee = prepay_amount * prepay_fee_rate / 100
                        new_principal = loan["current_principal"] - prepay_amount

                        if "납입금 감소" in prepay_type:
                            # 기간 유지, 납입금 감소
                            new_monthly = calc_monthly_payment(
                                new_principal, loan["rate"], loan["remaining_months"]
                            )
                            new_months = loan["remaining_months"]
                            saved_interest = (
                                (loan["monthly_payment"] * loan["remaining_months"] - loan["current_principal"])
                                - (new_monthly * new_months - new_principal)
                            )
                            st.success(f"""
                            **중도 상환 후 예상 결과 (납입금 감소)**
                            - 수수료: **{format_currency(fee)}** ({prepay_fee_rate}%)
                            - 새 월 납입금: **{format_currency(new_monthly)}**
                              (↓ {format_currency(loan['monthly_payment'] - new_monthly)} 감소)
                            - 잔여 기간: **{new_months}개월** (유지)
                            - 절약되는 이자: **{format_currency(max(0, saved_interest))}**
                            """)
                        else:
                            # 납입금 유지, 기간 단축
                            new_monthly = loan["monthly_payment"]
                            r = loan["rate"] / 100 / 12
                            if r > 0:
                                import math
                                new_months = math.ceil(
                                    -math.log(1 - new_principal * r / new_monthly)
                                    / math.log(1 + r)
                                ) if new_monthly > new_principal * r else 1
                            else:
                                new_months = math.ceil(new_principal / new_monthly)
                            saved_months = loan["remaining_months"] - new_months
                            saved_interest = (
                                (loan["monthly_payment"] * loan["remaining_months"] - loan["current_principal"])
                                - (new_monthly * new_months - new_principal)
                            )
                            st.success(f"""
                            **중도 상환 후 예상 결과 (기간 단축)**
                            - 수수료: **{format_currency(fee)}** ({prepay_fee_rate}%)
                            - 새 잔여 기간: **{new_months}개월**
                              (↓ {saved_months}개월 단축)
                            - 월 납입금: **{format_currency(new_monthly)}** (유지)
                            - 절약되는 이자: **{format_currency(max(0, saved_interest))}**
                            """)

                    # 중도 상환 확정 버튼
                    if st.button(f"✅ 중도 상환 확정 적용", key=f"apply_prepay_{i}",
                                 type="primary"):
                        if prepay_amount <= 0:
                            st.error("상환 금액을 입력해주세요.")
                        elif prepay_amount > loan["current_principal"]:
                            st.error("상환 금액이 잔여 원금을 초과합니다.")
                        else:
                            import math
                            fee = prepay_amount * prepay_fee_rate / 100
                            new_principal = loan["current_principal"] - prepay_amount

                            # 이력 저장
                            loan["prepayments"].append({
                                "date": str(prepay_date),
                                "amount": prepay_amount,
                                "fee": fee,
                                "type": prepay_type,
                                "before_principal": loan["current_principal"],
                                "before_monthly": loan["monthly_payment"],
                                "before_months": loan["remaining_months"]
                            })

                            # 원금 차감
                            loan["current_principal"] = new_principal

                            if "납입금 감소" in prepay_type:
                                loan["monthly_payment"] = calc_monthly_payment(
                                    new_principal, loan["rate"], loan["remaining_months"]
                                )
                                # remaining_months 유지
                            else:
                                r = loan["rate"] / 100 / 12
                                if r > 0 and loan["monthly_payment"] > new_principal * r:
                                    loan["remaining_months"] = math.ceil(
                                        -math.log(1 - new_principal * r / loan["monthly_payment"])
                                        / math.log(1 + r)
                                    )
                                else:
                                    loan["remaining_months"] = math.ceil(
                                        new_principal / loan["monthly_payment"]
                                    ) if loan["monthly_payment"] > 0 else 0
                                # monthly_payment 유지

                            st.success(f"✅ 중도 상환 적용 완료! (수수료 {format_currency(fee)} 포함)")
                            st.rerun()

                # ── 중도 상환 이력 ──────────────────
                if loan.get("prepayments"):
                    with st.expander(f"📜 '{loan['name']}' 중도 상환 이력 "
                                     f"({len(loan['prepayments'])}건)"):
                        hist_data = []
                        for p in loan["prepayments"]:
                            hist_data.append({
                                "날짜": p["date"],
                                "상환 금액": format_currency(p["amount"]),
                                "수수료": format_currency(p["fee"]),
                                "방식": "납입금 감소" if "납입금 감소" in p["type"] else "기간 단축",
                                "상환 전 원금": format_currency(p["before_principal"]),
                                "상환 전 월납입금": format_currency(p["before_monthly"]),
                            })
                        st.dataframe(pd.DataFrame(hist_data),
                                     use_container_width=True, hide_index=True)

                # ── 상환 스케줄 테이블 ──────────────
                with st.expander(f"📅 '{loan['name']}' 향후 상환 스케줄 (최대 12개월)"):
                    schedule = []
                    bal = loan["current_principal"]
                    r = loan["rate"] / 100 / 12
                    mp = loan["monthly_payment"]
                    show_months = min(loan["remaining_months"], 12)

                    for mo in range(1, show_months + 1):
                        interest_part = bal * r
                        principal_part = mp - interest_part
                        bal = max(0, bal - principal_part)
                        schedule.append({
                            "회차": f"{mo}회",
                            "월 납입금": format_currency(mp),
                            "이자 부분": format_currency(interest_part),
                            "원금 부분": format_currency(principal_part),
                            "잔여 원금": format_currency(bal)
                        })
                    st.dataframe(pd.DataFrame(schedule),
                                 use_container_width=True, hide_index=True)

                # ── 삭제 버튼 ──────────────────────
                if st.button(f"🗑️ '{loan['name']}' 삭제", key=f"del_loan_{i}"):
                    st.session_state.loans.pop(i)
                    st.rerun()

        st.divider()
        st.markdown(f"""
        <div style='text-align:right; font-size:1.2rem; font-weight:bold;
                    color:#1f77b4; padding:0.5rem;'>
            대출 합계: {format_currency(get_total_loans())} / 월
        </div>
        """, unsafe_allow_html=True)

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
