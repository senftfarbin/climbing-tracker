import streamlit as st
import streamlit.components.v1 as components
import time
import csv
import os
from datetime import datetime
import gspread
import json

SHEET_URL = "https://docs.google.com/spreadsheets/d/1D8VM5Na1LBIIoMV86Ie8rg6C4jmRceDozupNVydr73w/edit?usp=sharing"


def _get_gs_client() -> gspread.Client:
    """
    Create an authenticated gspread client using Streamlit secrets.
    Supports either:
    - st.secrets["gcp_sa_json"]: full service account JSON as a string
    - [gcp_service_account] table: keys copied from the JSON
    """
    cfg = None

    # Preferred: keep the original JSON exactly as Google gave it
    if "gcp_sa_json" in st.secrets:
        cfg = json.loads(st.secrets["gcp_sa_json"])
    elif "gcp_service_account" in st.secrets:
        cfg = dict(st.secrets["gcp_service_account"])
    else:
        raise RuntimeError(
            "No Google service account config found. "
            "Set either 'gcp_sa_json' or '[gcp_service_account]' in secrets.toml."
        )

    return gspread.service_account_from_dict(cfg)


def save_to_sheets(data) -> None:
    """
    Appends data to Google Sheets. 
    Handles both the 4x4 List and the Hangboard Dictionary.
    """
    client = _get_gs_client()
    sh = client.open_by_url(SHEET_URL)
    ws = sh.sheet1

    # Check if we are being sent a List (4x4) or a Dictionary (Hangboard)
    if isinstance(data, list):
        row_to_send = data
    elif isinstance(data, dict):
        # Convert the old Hangboard dictionary into the new 11-column format
        # [Date, Activity, C1_G, C1_R, C2_G, C2_R, C3_G, C3_R, C4_G, C4_R, Total]
        row_to_send = [
            data.get("date"), 
            data.get("activity"), 
            "-", "-", "-", "-", "-", "-", "-", "-", # Placeholders
            data.get("results")
        ]
    else:
        return # Safety break

    ws.append_row(row_to_send)

st.title("Climbing Tracker")

page = st.sidebar.radio("Workout", ["Max Hang Timer", "4x4 Tracker"])

# Try to keep the screen awake while this page is open (supported browsers only)
components.html(
    """
<script>
let wakeLock = null;

async function requestWakeLock() {
  try {
    if ('wakeLock' in navigator) {
      wakeLock = await navigator.wakeLock.request('screen');

      document.addEventListener('visibilitychange', async () => {
        if (document.visibilityState === 'visible') {
          try {
            wakeLock = await navigator.wakeLock.request('screen');
          } catch (e) {
            console.error(e);
          }
        }
      });
    }
  } catch (err) {
    console.error(err.name, err.message);
  }
}

requestWakeLock();
</script>
""",
    height=0,
    width=0,
)

if page == "Max Hang Timer":
    st.header("Max Hang Timer")
    
    reps = st.slider("Total Hangs Planned", 1, 10, 5)
    weight = st.number_input("Added weight (lbs)", value=0.0, step=0.5)

    if "current_rep" not in st.session_state:
        st.session_state.current_rep = 0
    if "is_resting" not in st.session_state:
        st.session_state.is_resting = False
    if "rest_start_time" not in st.session_state:
        st.session_state.rest_start_time = 0

    st.subheader(f"Progress: {st.session_state.current_rep} / {reps}")

    # --- THE START BUTTON & ACTION ---
    if not st.session_state.is_resting and st.session_state.current_rep < reps:
        if st.button("🚀 START NEXT HANG", use_container_width=True):
            current = st.session_state.current_rep + 1
            placeholder = st.empty()
            bar = st.progress(0) # Create the progress bar
            
            # 1. PREP (5s)
            for t in range(5, -1, -1):
                percent = int(((5 - t) / 5) * 100)
                bar.progress(percent)
                placeholder.metric(f"PREP (Hang {current})", f"{t}s" if t > 0 else "GO!")
                time.sleep(1)
            
            # 2. HANG (7s)
            bar.progress(0) # Reset bar for the hang
            for t in range(7, -1, -1):
                percent = int(((7 - t) / 7) * 100)
                bar.progress(percent)
                placeholder.metric(f"🔥 HANG! 🔥", f"{t}s" if t > 0 else "DONE!")
                time.sleep(1)
            
            # 3. LOGGING
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rep_data = [timestamp, "Hangboard Rep", f"Rep {current}", f"{weight}kg", "-", "-", "-", "-", "-", "-", f"Hang {current}/{reps}"]
            save_to_sheets(rep_data)
            
            # 4. UPDATE STATE
            st.session_state.current_rep += 1
            st.session_state.is_resting = True
            st.session_state.rest_start_time = time.time()
            st.rerun()

    # --- THE REST TIMER ---
    if st.session_state.is_resting:
        placeholder = st.empty()
        bar = st.progress(0) # Rest progress bar
        
        elapsed = time.time() - st.session_state.rest_start_time
        total_rest = 120
        remaining = int(total_rest - elapsed)

        if remaining > 0:
            percent = min(100, int((elapsed / total_rest) * 100))
            bar.progress(percent)
            mins, secs = divmod(remaining, 60)
            placeholder.metric("⏳ RESTING", f"{mins:02d}:{secs:02d}")
            time.sleep(1)
            st.rerun()
        else:
            bar.progress(100)
            st.session_state.is_resting = False
            st.toast("Rest Over! Ready for next hang.", icon="🔔")
            st.rerun()

    if st.button("🔄 Reset Session"):
        st.session_state.current_rep = 0
        st.session_state.is_resting = False
        st.rerun()

elif page == "4x4 Tracker":
    st.header("4x4 Tracker")
    st.caption("Four climbs. One set. Build power-endurance.")

    grades = [f"V{i}" for i in range(0, 11)]

    if "fourbyfour_sets_logged" not in st.session_state:
        st.session_state.fourbyfour_sets_logged = 0

    st.write(f"Sets this session: **{st.session_state.fourbyfour_sets_logged} / 4**")

    cols = st.columns(4)
    # Lists to hold the data we will send to the sheet
    climb_data = [] 
    completed_count = 0

    for idx, col in enumerate(cols, start=1):
        with col:
            st.subheader(f"Climb {idx}")
            grade = st.selectbox("Grade", grades, key=f"4x4_grade_{idx}")
            done = st.checkbox("Completed", key=f"4x4_done_{idx}")
            
            # Store Grade and Result (Sent/Fail) for this specific climb
            climb_data.append(grade)
            climb_data.append("Sent" if done else "Fail")
            if done:
                completed_count += 1

    st.write(f"Completed this set: **{completed_count}/4 climbs**")
    st.progress(int(completed_count / 4 * 100))

    if "fourbyfour_rest_start" not in st.session_state:
        st.session_state.fourbyfour_rest_start = None

    if st.button("Log 4x4 Set"):
        # 1. Create the 11-column Row
        # Format: [Timestamp, Activity, C1_G, C1_R, C2_G, C2_R, C3_G, C3_R, C4_G, C4_R, Total]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_row = [timestamp, "4x4"] + climb_data + [f"{completed_count}/4"]

        try:
            save_to_sheets(final_row)
            st.success("4x4 set logged to Google Sheet with detailed columns!")
            st.session_state.fourbyfour_sets_logged += 1
            
            if st.session_state.fourbyfour_sets_logged >= 4:
                st.balloons()
            
            # Start 3-minute rest timer
            st.session_state.fourbyfour_rest_start = time.time()
        except Exception as e:
            st.error(f"Failed to save to Google Sheets: {e}")

    # --- Rest Timer Display ---
    rest_placeholder = st.empty()
    if st.session_state.get("fourbyfour_rest_start"):
        elapsed = int(time.time() - st.session_state.fourbyfour_rest_start)
        remaining = max(0, 180 - elapsed)

        if remaining > 0:
            mins, secs = divmod(remaining, 60)
            rest_placeholder.warning(f"⏳ REST TIMER: {mins:02d}:{secs:02d}")
            time.sleep(1)
            st.rerun()
        else:
            rest_placeholder.error("🔔 GET READY FOR NEXT SET!")
            st.session_state.fourbyfour_rest_start = None

