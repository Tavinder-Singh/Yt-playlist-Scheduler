import sqlite3
import streamlit as st
from pytubefix import Playlist
from datetime import timedelta
import concurrent.futures

# Remove deploy button and menu
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# Database Setup
def init_db():
    conn = sqlite3.connect("schedule.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            schedule_name TEXT NOT NULL,
            schedule TEXT NOT NULL,
            FOREIGN KEY(username) REFERENCES users(username)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Authentication System
def register_user(username, password):
    conn = sqlite3.connect("schedule.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        st.success("User registered successfully! Please log in.")
    except sqlite3.IntegrityError:
        st.error("Username already exists! Please choose another.")
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = sqlite3.connect("schedule.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    return user is not None

def delete_user_account(username):
    conn = sqlite3.connect("schedule.db")
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM schedules WHERE username = ?", (username,))
        cursor.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error deleting account: {e}")
        return False
    finally:
        conn.close()

def save_schedule(username, schedule_name, schedule):
    conn = sqlite3.connect("schedule.db")
    cursor = conn.cursor()
    try:
        # Check if schedule exists
        cursor.execute("SELECT id FROM schedules WHERE username = ? AND schedule_name = ?", 
                      (username, schedule_name))
        if cursor.fetchone():
            # Update existing schedule
            cursor.execute("""
                UPDATE schedules 
                SET schedule = ?
                WHERE username = ? AND schedule_name = ?
            """, (str(schedule), username, schedule_name))
        else:
            # Insert new schedule
            cursor.execute("""
                INSERT INTO schedules (username, schedule_name, schedule) 
                VALUES (?, ?, ?)
            """, (username, schedule_name, str(schedule)))
        conn.commit()
        st.success("Schedule saved successfully!")
    except Exception as e:
        st.error(f"Error saving schedule: {e}")
    finally:
        conn.close()

def fetch_schedules(username):
    conn = sqlite3.connect("schedule.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT schedule_name, schedule FROM schedules WHERE username = ?", (username,))
        schedules = cursor.fetchall()
        return {name: eval(schedule) for name, schedule in schedules}
    except Exception as e:
        st.error(f"Error fetching schedules: {e}")
        return {}
    finally:
        conn.close()

def delete_schedule(username, schedule_name):
    conn = sqlite3.connect("schedule.db")
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM schedules WHERE username = ? AND schedule_name = ?", (username, schedule_name))
        conn.commit()
        st.success("Schedule deleted successfully!")
    except Exception as e:
        st.error(f"Error deleting schedule: {e}")
    finally:
        conn.close()
        st.rerun()

# Video processing functions
def fetch_video_details(video):
    try:
        return {
            "title": video.title,
            "duration": video.length,
            "link": video.watch_url,
            "completed": False  # Initialize as not completed
        }
    except Exception as e:
        st.error(f"Error processing video: {e}")
        return None

def fetch_playlist_details(playlist_url):
    try:
        if not playlist_url.strip():
            st.error("Please enter a playlist URL")
            return []
            
        with st.spinner('🔍 Fetching playlist videos...'):
            playlist = Playlist(playlist_url)
            if not playlist.video_urls:
                st.warning("Playlist is empty or private. Please check the URL.")
                return []
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                results = list(executor.map(fetch_video_details, playlist.videos))
        
        return [video for video in results if video]
    except Exception as e:
        st.error(f"Error loading playlist: {str(e)}")
        return []

# Schedule creation
def create_schedule_time_based(video_details, daily_time_minutes):
    daily_time_seconds = (daily_time_minutes - 10) * 60
    schedule, day, current_day_videos, current_day_duration = {}, 1, [], 0

    with st.spinner('⏳ Creating time-based schedule...'):
        for video in video_details:
            video_entry = {
                "title": video['title'],
                "duration": str(timedelta(seconds=video['duration'])),
                "link": video['link'],
                "completed": False  # Ensure completed flag is included
            }
            if current_day_duration + video["duration"] <= daily_time_seconds:
                current_day_videos.append(video_entry)
                current_day_duration += video["duration"]
            else:
                schedule[f"Day {day}"] = current_day_videos
                day += 1
                current_day_videos = [video_entry]
                current_day_duration = video["duration"]

        if current_day_videos:
            schedule[f"Day {day}"] = current_day_videos

    return schedule

def create_schedule_day_based(video_details, num_days):
    total_duration = sum(video["duration"] for video in video_details)
    avg_daily_duration = total_duration // num_days
    schedule, day, current_day_videos, current_day_duration = {}, 1, [], 0

    with st.spinner('⏳ Creating day-based schedule...'):
        for video in video_details:
            video_entry = {
                "title": video['title'],
                "duration": str(timedelta(seconds=video['duration'])),
                "link": video['link'],
                "completed": False  # Ensure completed flag is included
            }
            if day < num_days and current_day_duration + video["duration"] > avg_daily_duration:
                schedule[f"Day {day}"] = current_day_videos
                day += 1
                current_day_videos, current_day_duration = [], 0
            current_day_videos.append(video_entry)
            current_day_duration += video["duration"]

        if current_day_videos:
            schedule[f"Day {day}"] = current_day_videos

    return schedule

# Main application
def main():
    st.title("📚 YouTube Playlist Study Scheduler")

    # Login/Register section
    if "user" not in st.session_state:
        st.subheader("🔑 Login / Register")
        choice = st.radio("Select Option", ["Login", "Register"], horizontal=True)
        
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.button("Submit"):
            if choice == "Login":
                if authenticate_user(username, password):
                    st.session_state["user"] = username
                    st.success(f"Welcome {username}!")
                    st.rerun()
                else:
                    st.error("Invalid credentials! Try again.")
            else:
                register_user(username, password)
        return

    # Logged-in section
    st.sidebar.write(f"👤 Logged in as *{st.session_state['user']}*")
    if st.sidebar.button("Logout"):
        del st.session_state["user"]
        st.rerun()
        
    if st.sidebar.button("❌ Delete Account", type="primary"):
        if delete_user_account(st.session_state["user"]):
            del st.session_state["user"]
            st.rerun()

    tab1, tab2 = st.tabs(["📅 Create Schedule", "📖 My Schedules"])

    # Create Schedule Tab
    with tab1:
        playlist_url = st.text_input("Enter YouTube Playlist URL:", placeholder="https://www.youtube.com/playlist?list=...")
        start_video = st.number_input("Start from video number:", min_value=1, value=1)

        option = st.radio("Choose schedule type", ["Time-based", "Day-based"], horizontal=True)
        schedule_name = st.text_input("Enter Schedule Name:")

        if option == "Time-based":
            daily_time = st.number_input("Daily study time (in minutes)", min_value=20, value=60)
        else:
            num_days = st.number_input("Number of days to complete", min_value=1, value=7)

        if st.button("Generate Schedule"):
            if not playlist_url:
                st.error("Please enter a playlist URL")
            elif not schedule_name:
                st.error("Please enter a schedule name")
            else:
                with st.spinner('🚀 Generating your schedule...'):
                    videos = fetch_playlist_details(playlist_url)[start_video-1:]
                    if videos:
                        if option == "Time-based":
                            schedule = create_schedule_time_based(videos, daily_time)
                        else:
                            schedule = create_schedule_day_based(videos, num_days)
                        save_schedule(st.session_state["user"], schedule_name, schedule)

    # My Schedules Tab
    with tab2:
        schedules = fetch_schedules(st.session_state["user"])
        if schedules:
            selected_schedule = st.selectbox("Select Schedule", list(schedules.keys()))
            if selected_schedule:
                schedule_data = schedules[selected_schedule]
                
                st.write(f"### 📅 {selected_schedule}")
                
                # Progress tracking
                all_videos = [video for day in schedule_data.values() for video in day]
                total_videos = len(all_videos)
                completed_videos = sum(1 for video in all_videos if video.get('completed', False))
                
                st.progress(completed_videos / total_videos if total_videos > 0 else 0)
                st.caption(f"Completed: {completed_videos}/{total_videos} videos ({int(100*completed_videos/total_videos)}%)")
                
                # Track if any checkbox changes
                status_changed = False
                
                for day, videos in schedule_data.items():
                    with st.expander(f"{day} - {len(videos)} videos"):
                        for video in videos:
                            new_status = st.checkbox(
                                f"[{video['title']} ({video['duration']})]({video['link']})",
                                value=video.get('completed', False),
                                key=f"{selected_schedule}_{day}_{video['title']}"
                            )
                            if new_status != video.get('completed', False):
                                video['completed'] = new_status
                                status_changed = True
                
                # Update database if status changed
                if status_changed:
                    save_schedule(st.session_state["user"], selected_schedule, schedule_data)
                    st.rerun()

                if st.button("🗑 Delete Schedule", key=f"delete_{selected_schedule}"):
                    delete_schedule(st.session_state["user"], selected_schedule)
        else:
            st.info("No schedules found. Create one in the 'Create Schedule' tab.")

if __name__ == "__main__":
    main()
