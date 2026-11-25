import streamlit as st
from app import render_learner
from admin_app import render_admin

st.set_page_config(page_title="ListenUp | Portal", page_icon="🎧", layout="wide")

if "current_page" not in st.session_state:
    st.session_state.current_page = "home"

def go_to(page_name):
    st.session_state.current_page = page_name
    st.rerun()

if st.session_state.current_page == "home":
    st.title("🎧 Welcome to ListenUp")
    st.markdown("### Please select your role to continue")
    
    col1, col2 = st.columns(2)
    with col1:
        st.button("Enter Student Portal", on_click=go_to, args=("student",), use_container_width=True, type="primary")
    with col2:
        st.button("Enter Professor Portal", on_click=go_to, args=("professor",), use_container_width=True, type="primary")

elif st.session_state.current_page == "student":
    if st.button("⬅ Back to Role Selection"):
        go_to("home")
    st.markdown("---")
    render_learner()

elif st.session_state.current_page == "professor":
    if st.button("⬅ Back to Role Selection"):
        go_to("home")
    st.markdown("---")
    render_admin()