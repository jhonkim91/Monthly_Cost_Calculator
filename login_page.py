# login_page.py
import streamlit as st
from auth import register_user, login_user, change_pin, is_logged_in

def show_login_page():
    """로그인 / 회원가입 페이지"""

    # 중앙 정렬 레이아웃
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("""
        <div style='text-align:center; padding: 2rem 0 1rem 0;'>
            <h1>💰 월 고정비용 계산기</h1>
            <p style='color:#888;'>로그인 후 나만의 고정비를 관리하세요</p>
        </div>
        """, unsafe_allow_html=True)

        # 탭 — 로그인 / 회원가입
        login_tab, register_tab = st.tabs(["🔐 로그인", "✏️ 회원가입"])

        # ── 로그인 탭 ──────────────────────────
        with login_tab:
            st.markdown("<br>", unsafe_allow_html=True)

            login_id = st.text_input(
                "아이디",
                placeholder="아이디 입력",
                key="login_id"
            )
            login_pin = st.text_input(
                "PIN 번호 (4자리)",
                placeholder="● ● ● ●",
                type="password",
                max_chars=4,
                key="login_pin"
            )

            st.markdown("<br>", unsafe_allow_html=True)

            if st.button("🔓 로그인", type="primary",
                         use_container_width=True, key="btn_login"):
                if not login_id or not login_pin:
                    st.error("아이디와 PIN을 모두 입력해주세요.")
                elif len(login_pin) != 4 or not login_pin.isdigit():
                    st.error("PIN은 숫자 4자리여야 합니다.")
                else:
                    with st.spinner("확인 중..."):
                        result = login_user(login_id, login_pin)
                    if result["success"]:
                        st.session_state.is_authenticated = True
                        st.session_state.current_user = login_id
                        st.session_state.user_loaded = False
                        st.success(f"✅ 환영합니다, {login_id}님!")
                        st.rerun()
                    else:
                        st.error(result["message"])

        # ── 회원가입 탭 ────────────────────────
        with register_tab:
            st.markdown("<br>", unsafe_allow_html=True)

            reg_id = st.text_input(
                "아이디 (영문+숫자)",
                placeholder="예: hong123",
                key="reg_id"
            )
            reg_pin = st.text_input(
                "PIN 번호 (숫자 4자리)",
                placeholder="● ● ● ●",
                type="password",
                max_chars=4,
                key="reg_pin"
            )
            reg_pin_confirm = st.text_input(
                "PIN 확인",
                placeholder="● ● ● ●",
                type="password",
                max_chars=4,
                key="reg_pin_confirm"
            )

            st.markdown("<br>", unsafe_allow_html=True)

            if st.button("✅ 회원가입", type="primary",
                         use_container_width=True, key="btn_register"):
                # 유효성 검사
                if not reg_id or not reg_pin or not reg_pin_confirm:
                    st.error("모든 항목을 입력해주세요.")
                elif len(reg_id) < 3:
                    st.error("아이디는 3자 이상이어야 합니다.")
                elif not reg_pin.isdigit() or len(reg_pin) != 4:
                    st.error("PIN은 숫자 4자리여야 합니다.")
                elif reg_pin != reg_pin_confirm:
                    st.error("PIN이 일치하지 않습니다.")
                else:
                    with st.spinner("가입 처리 중..."):
                        result = register_user(reg_id, reg_pin)
                    if result["success"]:
                        st.success("🎉 회원가입 완료! 로그인 탭에서 로그인하세요.")
                    else:
                        st.error(result["message"])

        # PIN 변경 (접기)
        with st.expander("🔑 PIN 변경"):
            cp_id  = st.text_input("아이디", key="cp_id")
            cp_old = st.text_input("현재 PIN", type="password",
                                   max_chars=4, key="cp_old")
            cp_new = st.text_input("새 PIN", type="password",
                                   max_chars=4, key="cp_new")
            cp_new2 = st.text_input("새 PIN 확인", type="password",
                                    max_chars=4, key="cp_new2")
            if st.button("변경하기", key="btn_change_pin"):
                if cp_new != cp_new2:
                    st.error("새 PIN이 일치하지 않습니다.")
                elif not cp_new.isdigit() or len(cp_new) != 4:
                    st.error("PIN은 숫자 4자리여야 합니다.")
                else:
                    result = change_pin(cp_id, cp_old, cp_new)
                    if result["success"]:
                        st.success(result["message"])
                    else:
                        st.error(result["message"])
