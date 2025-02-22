# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
from flask_cors import CORS
import os
import datetime
import logging
import traceback
import re
import json

# Import database functions and OpenAI integration
from database import initialize_db, add_workout, get_all_workouts, get_users, add_user, delete_workout
from openai_integration import query_openai
import database  # Import full database module to access USE_SQLITE, cursor, conn, etc.

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app (templates folder is in the same directory)
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=template_dir)
app.config["APPLICATION_ROOT"] = "/"
CORS(app)

# Use a fixed secret key during development if desired, but here using os.urandom(16)
app.secret_key = os.urandom(16)

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for('index'))

# --- Prompt Storage Functions ---
PROMPTS_FILE = "prompts.json"

def load_prompts():
    if not os.path.exists(PROMPTS_FILE):
        default_prompts = {
            "gym_prompt": (
                "Based on my recent gym workout history focusing on strength training.\n"
                "Please suggest a workout plan for today, starting with warm-up and following with the main exercises. "
                "Keep in mind a high-intensity level. Suggest 5 min warm-up & stretching exercises relevant to the main exercises. "
                "Include exactly 5 types of exercises in the main exercises. Each exercise can be from 3 to 5 sets. "
                "The exercises must be limited to 2 body parts per session, for example - chest and back, or shoulders and legs. "
                "Do not suggest the same body parts that were trained in the most recent history. Suggest those that I haven't trained in a while. "
                "When choosing weight for the exercise - take the weight I have done with this exercise in the last historic session and add 1-3 kg. "
                "Give me suggestion in the following format where every set starts from the new line. "
                "In the beginning, tell me briefly and without too much details what I trained last time, and where the focus of today's training should be. "
                "Then give me warm-up exercises. The title saying **Warm-up & Stretching** must be in bold font. "
                "Keep one blank line between warm-up and main exercises. The title saying **Main Exercises** must be in bold font. "
                "Then give me today's program. Indicate which part of the body it works, max number of sets, max number of repetitions and max weight. "
                "List main exercises as single line for each out of 5. For example: Chest - Bench press: ramp to 80kg, 6 reps, 5 sets.\n"
            ),
            "wod_prompt": (
                "You are a professional CrossFit coach, and I am an athlete with 2 years of experience in CrossFit. "
                "Give me a WOD exercise program following the typical structure of a WOD. Include Rx weights and time for exercises where appropriate. "
                "The weights should be in kilograms. The time should be in minutes. "
                "Please provide today's WOD program in exactly 4 complete blocks. Each block should start with 'Block X:' where X is the block number. "
                "Each block must include the following details: Block title, Exercises, Time. The first block is always the warm-up. "
                "The suggestion must take into account my last saved WOD workout below, targeting different muscle groups and considering previous difficulty feedback. "
                "To understand the difficulty feedback, look for one of the following keywords: too easy, easy, perfect, too difficult.\n"
            )
        }
        with open(PROMPTS_FILE, "w") as f:
            json.dump(default_prompts, f, indent=4)
        return default_prompts
    else:
        with open(PROMPTS_FILE, "r") as f:
            return json.load(f)

def save_prompts(prompts):
    with open(PROMPTS_FILE, "w") as f:
        json.dump(prompts, f, indent=4)

# --- Admin Prompts Editing Route ---
@app.route('/prompts', methods=['GET', 'POST'])
def edit_prompts():
    # Only allow if logged in as admin
    if session.get("user_name", "").lower() != "admin":
        flash("Unauthorized access.")
        return redirect('/')
    prompts = load_prompts()
    if request.method == "POST":
        prompts["gym_prompt"] = request.form.get("gym_prompt")
        prompts["wod_prompt"] = request.form.get("wod_prompt")
        save_prompts(prompts)
        flash("Prompts saved successfully.")
        return redirect('/')
    return render_template("prompts.html", prompts=prompts)

# --- Removed DynamoDB Session Management ---
# The DynamoDB session integration has been removed in favor of using the persistent disk on Render.
# (The code block that previously imported boto3, set up a DynamoDBSessionInterface, and assigned it to app.session_interface has been removed.)

# --- Optional: Serve favicon to avoid 404 errors ---
@app.route('/favicon.ico')
def favicon():
    return "", 204

# --- Optional: Handle binary responses for API Gateway ---
@app.after_request
def handle_binary_response(response):
    if 'text/html' in response.headers.get('Content-Type', ''):
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

# --- Jinja Filter for Markdown Bold ---
def markdown_bold(text):
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
app.jinja_env.filters['markdown_bold'] = markdown_bold

# --- Initialize the Database ---
try:
    logger.info("Initializing database...")
    initialize_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {str(e)}")
    logger.error(traceback.format_exc())
    raise

# ------------------------------
# Error Handling
# ------------------------------
@app.errorhandler(Exception)
def handle_error(error):
    logger.error(f"Unhandled error: {str(error)}")
    logger.error(traceback.format_exc())
    return str(error), 500

# ------------------------------
# Index Route & User Selection
# ------------------------------
@app.route('/', methods=["GET", "POST"])
def index():
    logger.info("Starting index route")
    try:
        if request.method == "POST":
            # Retrieve form values
            selected_user = request.form.get("user_select", "")
            new_user = request.form.get("new_user", "").strip()
            
            # If the dropdown selection indicates a new user
            if selected_user == "new":
                if new_user:
                    logger.info(f"Creating new user: {new_user}")
                    user_id = add_user(new_user)
                    session["user_id"] = user_id
                    session["user_name"] = new_user
                    if new_user.lower() == "admin":
                        return redirect(url_for("edit_prompts"))
                    return redirect(url_for("index"))
                else:
                    flash("Please enter a new username.")
                    return redirect(url_for("index"))
            
            # If an existing user was selected
            elif selected_user:
                logger.info(f"Selected existing user: {selected_user}")
                session["user_id"] = int(selected_user)
                users = get_users()
                for user in users:
                    if user["id"] == int(selected_user):
                        session["user_name"] = user["username"]
                        break
                if session.get("user_name", "").lower() == "admin":
                    return redirect(url_for("edit_prompts"))
                return redirect(url_for("index"))
            
            # If nothing was selected but new_user field has a value (fallback)
            elif new_user:
                logger.info(f"Creating new user: {new_user}")
                user_id = add_user(new_user)
                session["user_id"] = user_id
                session["user_name"] = new_user
                if new_user.lower() == "admin":
                    return redirect(url_for("edit_prompts"))
                return redirect(url_for("index"))
            
            else:
                flash("Please select an existing user or enter a new username.")
                return redirect(url_for("index"))
        else:
            logger.info("Processing GET request to index")
            users = get_users()
            return render_template("index.html", users=users, current_user=session.get("user_id"))
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        logger.error(traceback.format_exc())
        flash("An error occurred. Please try again.")
        return render_template("index.html", users=[], current_user=None)

# ------------------------------
# Clear Database Route (Admin Only)
# ------------------------------
@app.route('/clear_database', methods=["POST"])
def clear_database():
    if session.get("user_name", "").lower() != "admin":
        flash("Unauthorized access.")
        return redirect('/')
    
    if database.USE_SQLITE:
        database.cursor.execute("DELETE FROM users")
        database.cursor.execute("DELETE FROM workouts")
        database.conn.commit()
    else:
        # For in-memory storage
        database.users = []
        database.workouts = []
        database.next_workout_id = 1
        database.next_user_id = 1
    
    flash("Database cleared successfully.")
    return redirect(url_for("edit_prompts"))

# ------------------------------
# Gym Workout Routes
# ------------------------------
@app.route('/record', methods=['GET', 'POST'])
def record_workout():
    if request.method == 'POST':
        date_input = request.form.get('date') or datetime.date.today().isoformat()
        # Check if the multi-row fields exist
        if request.form.get('body_part_0') is not None:
            rows_saved = 0
            for i in range(5):
                muscle_group = request.form.get(f'body_part_{i}', '').strip()
                exercise = request.form.get(f'exercise_{i}', '').strip()
                max_weight = request.form.get(f'max_weight_{i}', '').strip()
                sets = request.form.get(f'sets_{i}', '').strip()
                reps = request.form.get(f'reps_{i}', '').strip()
                # Only save if all fields are non-empty
                if muscle_group and exercise and max_weight and sets and reps:
                    details = {
                        "muscle_group": muscle_group,
                        "exercise": exercise,
                        "max_weight": max_weight,
                        "sets": sets,
                        "reps": reps
                    }
                    add_workout(date_input, session.get("user_id"), "gym", details)
                    rows_saved += 1
            if rows_saved:
                flash(f"{rows_saved} gym workout record(s) saved successfully.")
            else:
                flash("No valid workout data provided.")
            return redirect(url_for('gym_history'))
        else:
            # Fallback for a single-entry form (if used)
            muscle_group = request.form.get('muscle_group')
            exercise = request.form.get('exercise')
            max_weight = request.form.get('max_weight')
            sets = request.form.get('sets')
            reps = request.form.get('reps')
            if muscle_group and exercise and max_weight and sets and reps:
                details = {
                    "muscle_group": muscle_group,
                    "exercise": exercise,
                    "max_weight": max_weight,
                    "sets": sets,
                    "reps": reps
                }
                add_workout(date_input, session.get("user_id"), "gym", details)
                flash('Gym workout recorded successfully.')
            else:
                flash('Missing fields for gym workout.')
            return redirect(url_for('gym_history'))
    return render_template('record.html')

@app.route('/gym_history')
def gym_history():
    if "user_id" not in session:
        flash("Please select a user first.")
        return redirect('/')
    all_workouts = get_all_workouts()
    # Filter to only gym workouts for the logged-in user
    gym_workouts = [w for w in all_workouts if w.get("workout_type") == "gym" and w.get("user_id") == session.get("user_id")]
    return render_template('gym_history.html', workouts=gym_workouts)

@app.route('/gym_suggest')
def gym_suggest():
    workouts = get_all_workouts()
    # Filter workouts for the current user and only gym type
    workouts = [w for w in workouts if w["user_id"] == session.get("user_id")]
    gym_workouts = [w for w in workouts if w["workout_type"] == "gym"]
    
    # Sort gym workouts by date descending (assumes ISO format: YYYY-MM-DD)
    gym_workouts = sorted(gym_workouts, key=lambda w: w["date"], reverse=True)
    
    # Take the five most recent workouts
    recent_workouts = gym_workouts[:5]
    history_text = "\n".join([
        f"Date: {w['date']}, Muscle Group: {w['details'].get('muscle_group','')}, "
        f"Exercise: {w['details'].get('exercise','')}, Max Weight: {w['details'].get('max_weight','')}, "
        f"Sets: {w['details'].get('sets','')}, Reps: {w['details'].get('reps','')}"
        for w in recent_workouts
    ])
    
    if gym_workouts:
        max_date = gym_workouts[0]["date"]  # most recent date after sorting
        last_workouts = [w for w in gym_workouts if w["date"] == max_date]
        records = []
        for w in last_workouts:
            records.append({
                "muscle_group": w["details"].get("muscle_group", ""),
                "exercise": w["details"].get("exercise", ""),
                "max_weight": w["details"].get("max_weight", ""),
                "sets": w["details"].get("sets", ""),
                "reps": w["details"].get("reps", "")
            })
        last_session = {"date": max_date, "records": records}
    else:
        last_session = None

    # Load the gym prompt from storage and append the dynamic history text.
    prompts_data = load_prompts()
    gym_prompt = prompts_data.get("gym_prompt", "")
    prompt = (
        gym_prompt +
        "\nHere is my workout history:\n" +
        f"{history_text}\n\nNow, based on the above, please provide today's workout program."
    )
    
    # Log the prompt for debugging
    logger.info("Gym Suggest Prompt: " + prompt)
    
    suggestion = query_openai(prompt)
    return render_template('gym_suggest.html', suggestion=suggestion, last_session=last_session)

# ------------------------------
# WOD (CrossFit) Routes
# ------------------------------
@app.route('/wod_suggest')
def wod_suggest():
    if "user_id" not in session:
        flash("Please select a user first.")
        return redirect('/')
    workouts = get_all_workouts()
    wod_workouts = [w for w in workouts if w["workout_type"] == "wod" and w["user_id"] == session.get("user_id")]
    if wod_workouts:
        sorted_wods = sorted(wod_workouts, key=lambda w: w["id"], reverse=True)
        last_wod = sorted_wods[0]
    else:
        last_wod = None

    if last_wod:
        # Build a history string (for debugging; not used in the template below)
        history_text = (
            f"Date: {last_wod['date']}, "
            f"WOD Workout: {last_wod['details'].get('wod_workout', last_wod['details'].get('exercises', ''))}, "
            f"Feedback: {last_wod['details'].get('wod_difficulty', '')}"
        )
    else:
        history_text = "No recorded WOD session."

    prompts_data = load_prompts()
    wod_prompt = prompts_data.get("wod_prompt", "")
    prompt = wod_prompt + "\nHere is my last saved WOD workout:\n" + f"{history_text}\n\nNow, based on the above, please provide today's complete WOD program. The weight should be in kilograms."

    # Query OpenAI for the suggested WOD program
    suggestion = query_openai(prompt)
    # Use a regex to try to extract blocks (if present)
    pattern = r'(Block\s+\d+:[\s\S]*?)(?=Block\s+\d+:|$)'
    suggestion_blocks = re.findall(pattern, suggestion)
    # Fallback: if no blocks found, use the full suggestion
    if not suggestion_blocks:
        suggestion_blocks = [suggestion]
    saved_wod = "\n".join(suggestion_blocks)
    
    # Log for debugging
    logger.info("WOD Suggest Prompt: " + prompt)
    
    return render_template('wod_suggest.html', 
                           suggestion_blocks=suggestion_blocks, 
                           last_wod=last_wod,
                           saved_wod=saved_wod)

import re

@app.template_filter('extract_blocks')
def extract_blocks(text):
    """
    Extracts Block 2 and Block 3 from the given WOD text.
    Assumes the text contains labels like "Block 2:" and "Block 3:".
    """
    block2 = re.search(r'(Block\s*2:.*?)(?=Block\s*3:|$)', text, re.DOTALL)
    block3 = re.search(r'(Block\s*3:.*?)(?=Block\s*4:|$)', text, re.DOTALL)
    blocks = []
    if block2:
        blocks.append(block2.group(1).strip())
    if block3:
        blocks.append(block3.group(1).strip())
    return "<br>".join(blocks)

@app.route('/wod_history')
def wod_history():
    if "user_id" not in session:
        flash("Please select a user first.")
        return redirect('/')
    workouts = get_all_workouts()
    wod_workouts = [w for w in workouts if w["workout_type"] == "wod" and w["user_id"] == session.get("user_id")]
    return render_template('wod_history.html', workouts=wod_workouts)

@app.route('/record_wod_feedback', methods=['POST'])
def record_wod_feedback():
    if "user_id" not in session:
        flash("Please select a user first.")
        return redirect('/')
    feedback = request.form.get('feedback')  # e.g., "too easy", "easy", "perfect", "too difficult"
    wod_workout = request.form.get('wod_workout')  # the full WOD suggestion text (all blocks combined)
    today = datetime.date.today().isoformat()
    if wod_workout and feedback:
        details = {
            "wod_blocks": wod_workout,      # Save the complete WOD workout here (use the same key as /record_wod)
            "wod_difficulty": feedback       # Save the feedback here
        }
        add_workout(today, session.get("user_id"), "wod", details)
        flash("WOD workout and feedback recorded successfully.")
    else:
        flash("Missing WOD workout data or feedback.")
    return redirect('/')

@app.route('/record_wod', methods=['POST'])
def record_wod():
    if "user_id" not in session:
        flash("Please select a user first.")
        return redirect('/')
    today = datetime.date.today().isoformat()
    wod_workout = request.form.get('wod_workout')
    if wod_workout:
        details = {"wod_blocks": wod_workout}
        add_workout(today, session.get("user_id"), "wod", details)
        flash("WOD workout recorded successfully.")
    else:
        flash("No WOD workout data provided.")
    return redirect('/wod_suggest')

@app.route('/delete_wod/<int:record_id>', methods=['POST'])
def delete_wod(record_id):
    try:
        delete_workout(record_id, workout_type='wod')
        flash("WOD record deleted successfully.")
    except Exception as e:
        logger.error(f"Failed to delete WOD record: {str(e)}")
        flash("Failed to delete WOD record.")
    return redirect('/wod_history')

# ------------------------------
# Docker & Beanstalk Entry Point
# ------------------------------
if __name__ == '__main__':
    host = os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_RUN_PORT", 5002))
    debug_mode = os.environ.get("FLASK_DEBUG", "False") == "True"
    app.run(host=host, port=port, debug=debug_mode, use_reloader=False)

# Expose the WSGI application for Elastic Beanstalk
application = app
