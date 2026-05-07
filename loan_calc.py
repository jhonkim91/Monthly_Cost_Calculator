# loan_calc.py
import math
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

# ─────────────────────────────────────────
# 상환 방식 상수
# ─────────────────────────────────────────
METHOD_EQUAL_PAYMENT    = "원리금균등상환"   # 매월 동일금액
METHOD_EQUAL_PRINCIPAL  = "원금균등상환"     # 원금 고정, 이자 감소
METHOD_BULLET           = "만기일시상환"     # 매월 이자만, 만기에 원금

REPAY_METHODS = [METHOD_EQUAL_PAYMENT, METHOD_EQUAL_PRINCIPAL, METHOD_BULLET]

# 자주 쓰는 금융기관 목록
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


# ══════════════════════════════════════════
# 핵심 계산 함수들
# ══════════════════════════════════════════

def calc_equal_payment(principal: float, annual_rate: float, months: int) -> float:
    """① 원리금균등상환 — 매월 동일 납입금"""
    if months <= 0:
        return 0.0
    if annual_rate == 0:
        return principal / months
    r = annual_rate / 100 / 12
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def calc_equal_principal(principal: float, annual_rate: float,
                          months: int, current_month: int = 1) -> dict:
    """② 원금균등상환 — 해당 회차의 납입 정보 반환"""
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


def calc_bullet(principal: float, annual_rate: float) -> float:
    """③ 만기일시상환 — 매월 이자만 납입"""
    r = annual_rate / 100 / 12
    return principal * r


# ══════════════════════════════════════════
# 현재 날짜 기준 대출 현황 계산
# ══════════════════════════════════════════

def calc_loan_status(loan: dict) -> dict:
    """
    대출 시작일 기준으로 오늘까지의 실제 납입 현황 계산
    - 경과 개월 수
    - 현재 잔여 원금
    - 현재까지 납입한 이자 총액
    - 남은 개월 수
    """
    start_date = datetime.strptime(loan["start_date"], "%Y-%m-%d").date()
    today = date.today()

    # 경과 개월 계산
    diff = relativedelta(today, start_date)
    elapsed_months = diff.years * 12 + diff.months
    elapsed_months = min(elapsed_months, loan["original_months"])

    original_months  = loan["original_months"]
    principal        = loan["original_principal"]
    annual_rate      = loan["rate"]
    method           = loan["repay_method"]
    r                = annual_rate / 100 / 12

    total_paid_principal = 0.0
    total_paid_interest  = 0.0
    current_balance      = principal

    # 중도상환 이력 정렬 (날짜 오름차순)
    prepayments = sorted(
        loan.get("prepayments", []),
        key=lambda x: x["date"]
    )
    prepay_index = 0

    for month in range(1, elapsed_months + 1):
        # 해당 월의 중도상환 처리
        current_month_date = (start_date + relativedelta(months=month)).isoformat()
        while prepay_index < len(prepayments):
            pp = prepayments[prepay_index]
            if pp["date"] <= current_month_date:
                current_balance -= pp["amount"]
                current_balance = max(0, current_balance)
                prepay_index += 1
            else:
                break

        if current_balance <= 0:
            break

        if method == METHOD_EQUAL_PAYMENT:
            # 원리금균등: 현재 잔액 기준으로 남은 기간 재계산
            remaining_m = original_months - month + 1
            if remaining_m <= 0:
                break
            mp = calc_equal_payment(current_balance, annual_rate, remaining_m)
            interest_part   = current_balance * r
            principal_part  = mp - interest_part
            principal_part  = min(principal_part, current_balance)

        elif method == METHOD_EQUAL_PRINCIPAL:
            monthly_p      = principal / original_months
            interest_part  = current_balance * r
            principal_part = monthly_p

        else:  # 만기일시상환
            interest_part  = current_balance * r
            principal_part = 0.0
            if month == original_months:
                principal_part = current_balance

        total_paid_principal += principal_part
        total_paid_interest  += interest_part
        current_balance      -= principal_part
        current_balance       = max(0, current_balance)

    remaining_months = max(0, original_months - elapsed_months)

    # 현재 월 납입금 계산
    if current_balance <= 0:
        current_monthly = 0.0
    elif method == METHOD_EQUAL_PAYMENT:
        current_monthly = calc_equal_payment(
            current_balance, annual_rate, max(1, remaining_months)
        )
    elif method == METHOD_EQUAL_PRINCIPAL:
        monthly_p = principal / original_months
        current_monthly = monthly_p + current_balance * r
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


# ══════════════════════════════════════════
# 전체 상환 스케줄 생성
# ══════════════════════════════════════════

def generate_schedule(loan: dict, max_months: int = None) -> list:
    """회차별 상환 스케줄 생성"""
    principal    = loan["current_principal"]
    annual_rate  = loan["rate"]
    months       = loan["remaining_months"]
    method       = loan["repay_method"]
    r            = annual_rate / 100 / 12

    if max_months:
        months = min(months, max_months)

    schedule     = []
    balance      = principal
    orig_monthly_p = principal / loan["original_months"] \
                     if method == METHOD_EQUAL_PRINCIPAL else 0

    for mo in range(1, months + 1):
        if balance <= 0:
            break

        if method == METHOD_EQUAL_PAYMENT:
            mp             = calc_equal_payment(balance, annual_rate,
                                                 loan["remaining_months"] - mo + 1)
            interest_part  = balance * r
            principal_part = min(mp - interest_part, balance)

        elif method == METHOD_EQUAL_PRINCIPAL:
            principal_part = orig_monthly_p
            interest_part  = balance * r
            mp             = principal_part + interest_part

        else:  # 만기일시상환
            interest_part  = balance * r
            principal_part = balance if mo == months else 0
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
