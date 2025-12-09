import streamlit as st
import requests
import json
import time
import threading
from pathlib import Path
from datetime import datetime
import subprocess
import sys

# ----------------- CONFIG -----------------
# Time string passed to schedule.every().day.at(...).
# By default it's "02:00" which means 02:00 server local time.
# If your server runs in UTC and you want 02:00 Vietnam (UTC+7),
# set SCHEDULE_TIME = "19:00"  (19:00 UTC == 02:00 UTC+7).
SCHEDULE_TIME = "02:00"

TOKENS_FILE = Path("tokens.json")
LOG_FILE = Path("run_tokens.log")

API_URL = "https://eventista-platform-api.1vote.vn/v2/web/tenant/nFkFqZ/event/EVENT_FiZrv/voting-free"
# -------------------------------------------

st.set_page_config(page_title="Auto Voting (always-on scheduler)", layout="centered")

# Ensure schedule package
try:
    import schedule
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "schedule"])
    import schedule

# ----------------- Helpers -----------------
def load_tokens():
    if TOKENS_FILE.exists():
        try:
            return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_tokens(tokens):
    TOKENS_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")

def append_log(text):
    line = f"{datetime.now().isoformat()} - {text}\n"
    if LOG_FILE.exists():
        LOG_FILE.write_text(LOG_FILE.read_text(encoding="utf-8") + line, encoding="utf-8")
    else:
        LOG_FILE.write_text(line, encoding="utf-8")
# -------------------------------------------

# ---------------- API calls ----------------
def build_headers(token):
    from uuid import uuid4
    return {
        "apigw-requestid": str(uuid4()).replace("-", "")[:16],
        "Origin": "https://giaithuongngoisaoxanh.1vote.vn",
        "Referer": "https://giaithuongngoisaoxanh.1vote.vn/",
        "x-eventista-check-token": "",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

def run_request_for_token(token):
    payload = {
        "paymentType":"free",
        "pointPackageId":"FREE",
        "productGroupId":"JPYxH",
        "productId":"8FJf",
        "source":{
            "screen":"candidate-detail",
            "pointPackage":{"amount":0,"id":"FREE","point":"100"}
        }
    }
    try:
        r = requests.post(API_URL, json=payload, headers=build_headers(token), timeout=30)
        append_log(f"token[:8]={token[:8]}... status={r.status_code} body={r.text[:300]}")
        try:
            return True, r.status_code, r.json()
        except Exception:
            return True, r.status_code, r.text
    except Exception as e:
        append_log(f"token[:8]={token[:8]}... EXCEPTION: {e}")
        return False, None, str(e)
# -------------------------------------------

# -------------- Run all tokens -------------
def run_all_tokens():
    tokens = load_tokens()
    append_log(f"RUN ALL start tokens_count={len(tokens)}")
    results = []
    for t in tokens:
        ok, status, body = run_request_for_token(t)
        results.append({"token_prefix": t[:8]+"...", "ok": ok, "status": status, "body": body})
    append_log("RUN ALL end")
    return results
# -------------------------------------------

# ---------------- Scheduler job -------------
def job_run_all():
    append_log("JOB_RUN_ALL triggered by scheduler")
    run_all_tokens()

def scheduler_loop(stop_event):
    schedule.clear()
    schedule.every().day.at(SCHEDULE_TIME).do(job_run_all)
    append_log(f"Scheduler thread started, scheduled daily at {SCHEDULE_TIME} (server local time).")
    while not stop_event.is_set():
        schedule.run_pending()
        time.sleep(5)
    append_log("Scheduler thread stopping")
# -------------------------------------------

# ---------------- session management ----------
if "scheduler_thread_started" not in st.session_state:
    # start scheduler thread immediately and keep in session_state
    stop_evt = threading.Event()
    th = threading.Thread(target=scheduler_loop, args=(stop_evt,), daemon=True)
    th.start()
    st.session_state.scheduler_thread_started = True
    st.session_state.scheduler_stop_event = stop_evt
    append_log("UI: Scheduler auto-started on app start")
# ----------------------------------------------

# ----------------- UI ------------------------
st.title("🔁 Auto Voting Token Runner — Scheduler always ON")
st.markdown(
    "Scheduler **mặc định khởi động tự động** khi app chạy. "
    f"Sẽ thực hiện `run_all_tokens()` mỗi ngày lúc **{SCHEDULE_TIME}** (server local time)."
)
tokens = load_tokens()

# Add tokens
st.subheader("➕ Thêm token (mỗi dòng 1 token)")
token_input = st.text_area("Nhập token...", height=160, placeholder="Paste tokens, one per line")
if st.button("Lưu token"):
    new = [t.strip() for t in token_input.splitlines() if t.strip()]
    if not new:
        st.warning("Chưa nhập token nào.")
    else:
        existing = set(tokens)
        added = 0
        for t in new:
            if t not in existing:
                tokens.append(t)
                existing.add(t)
                added += 1
        save_tokens(tokens)
        append_log(f"UI: Added {added} tokens")
        st.success(f"Đã thêm {added} token. Tổng: {len(tokens)}")
        st.rerun()  # safe in modern Streamlit

st.write("---")
st.subheader(f"📋 Danh sách token ({len(tokens)})")
if tokens:
    for i, t in enumerate(tokens):
        cols = st.columns([7,1,1])
        cols[0].code(t)
        if cols[1].button("Xóa", key=f"del_{i}"):
            tokens.pop(i)
            save_tokens(tokens)
            append_log(f"UI: Deleted token index {i}")
            st.rerun()
        if cols[2].button("Test", key=f"test_{i}"):
            ok, status, body = run_request_for_token(t)
            if ok:
                st.success(f"OK — status {status}")
                st.json(body)
            else:
                st.error("Lỗi khi test")
                st.text(body)
else:
    st.info("Chưa có token.")

st.write("---")
st.subheader("▶ Thao tác")
if st.button("Chạy tất cả token ngay"):
    with st.spinner("Đang chạy..."):
        results = run_all_tokens()
    st.success("Hoàn thành")
    st.json(results)

st.write("---")
st.subheader("📄 Log")
if LOG_FILE.exists():
    st.download_button("Tải log", LOG_FILE.read_text(encoding="utf-8"), "run_tokens.log")
else:
    st.info("Chưa có log.")
# -------------------------------------------
