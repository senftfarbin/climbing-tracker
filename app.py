import streamlit as st
import streamlit.components.v1 as components
import time
import csv
import os
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

SHEET_URL = "https://docs.google.com/spreadsheets/d/1D8VM5Na1LBIIoMV86Ie8rg6C4jmRceDozupNVydr73w/edit?usp=sharing"


def _get_gs_client() -> gspread.Client:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    return gspread.authorize(creds)


def save_to_sheets(data: dict) -> None:
    """
    Append a single row with keys: date, activity, results.
    """
    try:
        client = _get_gs_client()
        sh = client.open_by_url(SHEET_URL)
        ws = sh.sheet1

        # If sheet is empty, write header first
        existing = ws.get_all_values()
        if not existing:
            ws.append_row(["Date", "Activity", "Results"])

        ws.append_row([data["date"], data["activity"], data["results"]])
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to save to Google Sheets: {e}")

st.title("Max Hang Tracker")
st.caption("One focused session at a time.")

page = st.sidebar.radio("Page", ["Max Hang Timer", "4x4 Tracker"])

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
    # --- HANGBOARD TIMER ---
    st.header("Max Hang Timer (7s on / 2min off)")
    st.write("Press **Ready** before each hang. The timer runs **5s prep**, **7s hang**, then **2min rest**.")

    reps = st.slider("Number of Hangs", 1, 10, 5)
    weight = st.number_input(
        "Max hang added weight (kg, use negative for assistance)",
        value=0.0,
        step=0.5,
    )

    # Track how many hangs you've already completed
    if "current_rep" not in st.session_state:
        st.session_state.current_rep = 0

    st.write(f"Hangs completed: **{st.session_state.current_rep} / {reps}**")

    col1, col2 = st.columns(2)
    with col1:
        ready = st.button("I'm ready – start next hang")
    with col2:
        reset = st.button("Reset session")

    if reset:
        st.session_state.current_rep = 0

    # If all hangs are done, show completion message
    if st.session_state.current_rep >= reps:
        st.success("All hangs complete! Adjust reps or reset to start a new session.")
    elif ready:
        hang_time = 7
        prep_time = 5
        rest_time = 120
        current = st.session_state.current_rep + 1

        placeholder = st.empty()
        progress_bar = st.progress(0)

        # Prep phase
        st.info(f"Hang {current}: Get ready!")
        for elapsed in range(prep_time):
            remaining = prep_time - elapsed
            placeholder.metric("Prep – hang starts in (seconds)", remaining)
            progress_bar.progress(int((elapsed + 1) / prep_time * 100))
            time.sleep(1)

        # Hang phase
        st.warning(f"Hang {current}: HANG!")
        progress_bar.progress(0)
        for elapsed in range(hang_time):
            remaining = hang_time - elapsed
            placeholder.metric("Hang – seconds remaining", remaining)
            progress_bar.progress(int((elapsed + 1) / hang_time * 100))
            time.sleep(1)

        # Log this completed rep immediately (even if you stop the workout later)
        rep_log_file = "hang_reps.csv"
        rep_file_exists = os.path.exists(rep_log_file)
        with open(rep_log_file, "a", newline="") as f:
            rep_writer = csv.writer(f)
            if not rep_file_exists:
                rep_writer.writerow(["timestamp", "rep_number", "reps_planned", "weight_kg"])
            rep_writer.writerow([datetime.now().isoformat(), current, reps, weight])

        # Rest phase (always give 2 minutes off the board)
        st.info("REST – 2 minutes off the board")
        progress_bar.progress(0)
        for elapsed in range(rest_time):
            remaining = rest_time - elapsed
            placeholder.metric("Rest – seconds remaining", remaining)
            progress_bar.progress(int((elapsed + 1) / rest_time * 100))
            time.sleep(1)

        st.session_state.current_rep += 1

        if st.session_state.current_rep >= reps:
            # Log completed session with timestamp and max hang weight
            log_file = "hang_sessions.csv"
            file_exists = os.path.exists(log_file)
            with open(log_file, "a", newline="") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["timestamp", "reps", "weight_kg"])
                writer.writerow([datetime.now().isoformat(), reps, weight])

            st.balloons()
            st.success("Session Complete! Nice work.")

    # (Sessions and individual hangs are still logged to CSV files in the background.)

    # Optional: log this hangboard session summary to Google Sheets
    if st.button("Log Session to Google Sheet"):
        results_str = f"{st.session_state.current_rep}/{reps} hangs at {weight} kg"
        save_to_sheets(
            {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "activity": "Hangboard",
                "results": results_str,
            }
        )
        st.success("Hangboard session logged to Google Sheet.")

elif page == "4x4 Tracker":
    st.header("4x4 Tracker")
    st.caption("Four climbs. One set. Build power-endurance.")

    grades = [f"V{i}" for i in range(0, 11)]

    # Session set counter
    if "fourbyfour_sets_logged" not in st.session_state:
        st.session_state.fourbyfour_sets_logged = 0

    st.write(f"Sets this session: **{st.session_state.fourbyfour_sets_logged} / 4**")

    # Handle reset of completed checkboxes triggered after logging a set
    if st.session_state.get("reset_4x4_done"):
        for i in range(1, 5):
            st.session_state.pop(f"4x4_done_{i}", None)
        st.session_state.reset_4x4_done = False

    cols = st.columns(4)
    selected_grades = []
    completed_flags = []

    for idx, col in enumerate(cols, start=1):
        with col:
            st.subheader(f"Climb {idx}")
            grade = st.selectbox(
                "Grade",
                grades,
                key=f"4x4_grade_{idx}",
            )
            done = st.checkbox("Completed", key=f"4x4_done_{idx}")
            selected_grades.append(grade)
            completed_flags.append(done)

    completed_count = sum(1 for d in completed_flags if d)
    st.write(f"Completed this set: **{completed_count}/4 climbs**")

    progress = st.progress(int(completed_count / 4 * 100))

    if "fourbyfour_rest_start" not in st.session_state:
        st.session_state.fourbyfour_rest_start = None

    if st.button("Log 4x4 Set"):
        # Log this 4x4 set with timestamp and grades
        set_log_file = "four_by_four_sets.csv"
        file_exists = os.path.exists(set_log_file)
        with open(set_log_file, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(
                    [
                        "timestamp",
                        "climb1_grade",
                        "climb1_completed",
                        "climb2_grade",
                        "climb2_completed",
                        "climb3_grade",
                        "climb3_completed",
                        "climb4_grade",
                        "climb4_completed",
                        "completed_count",
                    ]
                )
            writer.writerow(
                [
                    datetime.now().isoformat(),
                    selected_grades[0],
                    completed_flags[0],
                    selected_grades[1],
                    completed_flags[1],
                    selected_grades[2],
                    completed_flags[2],
                    selected_grades[3],
                    completed_flags[3],
                    completed_count,
                ]
            )

        successful_grades = [
            g for g, done in zip(selected_grades, completed_flags) if done
        ]
        results_str = f"{completed_count}/4 sends"
        if successful_grades:
            st.success(
                f"Logged set with {completed_count} sends: {', '.join(successful_grades)}"
            )
        else:
            st.success("Logged set with no completed climbs. Keep pushing next round!")

        # Increment session set counter
        st.session_state.fourbyfour_sets_logged += 1
        if st.session_state.fourbyfour_sets_logged >= 4:
            st.balloons()
            st.success("4 sets complete for this session! Nice effort.")

        # Send summary row to Google Sheets
        save_to_sheets(
            {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "activity": "4x4",
                "results": results_str,
            }
        )

        # Start 3-minute rest timer
        st.session_state.fourbyfour_rest_start = time.time()

        # Mark that we should reset checkboxes on the next run, then rerun
        st.session_state.reset_4x4_done = True
        st.rerun()

    # Rest timer display using stored start time
    rest_placeholder = st.empty()
    if st.session_state.get("fourbyfour_rest_start"):
        elapsed = int(time.time() - st.session_state.fourbyfour_rest_start)
        total_rest = 180
        remaining = max(0, total_rest - elapsed)

        if remaining > 0:
            mins, secs = divmod(remaining, 60)
            rest_placeholder.info(f"Rest: {mins:02d}:{secs:02d}")
            # Trigger a soft countdown without blocking other interactions too much
            time.sleep(1)
            st.rerun()
        else:
            rest_placeholder.empty()
            st.error("GET READY FOR NEXT SET!")
            st.session_state.fourbyfour_rest_start = None