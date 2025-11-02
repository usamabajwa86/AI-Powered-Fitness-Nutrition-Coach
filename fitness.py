import os
import streamlit as st
import groq
import pandas as pd
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()

# Prefer Streamlit secrets, then environment variables (.env or environment). Do not hardcode secrets in source.
api_key = None
try:
    # Streamlit stores secrets in st.secrets when deployed to Streamlit Cloud or when using a secrets.toml
    api_key = st.secrets.get("GROQ_API_KEY") if hasattr(st, "secrets") else None
except Exception:
    api_key = None

if not api_key:
    api_key = os.getenv("fitness") or os.getenv("FITNESS") or os.getenv("GROQ_API_KEY")


def _get_groq_client(key: str):
    """Return a groq client instance or raise a RuntimeError on failure."""
    if not key:
        raise RuntimeError("Groq API key not provided")

    # Prefer the modern Client API if available
    client = None
    try:
        client = groq.Client(api_key=key)
        return client
    except Exception:
        # Fallback: some older/newer SDKs may expose a different constructor
        try:
            # try attribute style if present (keeps compatibility with different SDKs)
            GroqClass = getattr(groq, "Groq", None)
            if GroqClass:
                return GroqClass(api_key=key)
        except Exception:
            pass

    raise RuntimeError("Unable to initialize Groq client. Check installed groq SDK and API key.")

# Function to generate a personalized fitness and meal plan using Groq API
def generate_plans_with_groq(api_key, age, weight, height, gender, diet_pref, fitness_goal, exercise_time):
    try:
        client = _get_groq_client(api_key)
    except Exception as e:
        # propagate a concise error to the caller (Streamlit will show it)
        raise RuntimeError(str(e))

    workout_prompt = f"""
    Generate a detailed week-long workout plan for a {age}-year-old {gender} who wants to increase upper body width by {fitness_goal} and has {exercise_time} minutes daily for exercise. Focus on exercises that build shoulders, chest, and back muscles.
    Please format the plan as follows:
    Day 1: Workout Description
    Day 2: Workout Description
    Day 3: Workout Description
    Day 4: Workout Description
    Day 5: Workout Description
    Day 6: Workout Description
    Day 7: Workout Description
    """

    meal_prompt = f"""
    Generate a detailed week-long meal plan for a {diet_pref} diet to help a {age}-year-old {gender} increase upper body width with a focus on muscle gain.
    Please format the plan as follows:
    Day 1: Breakfast, Lunch, Dinner, Snacks
    Day 2: Breakfast, Lunch, Dinner, Snacks
    Day 3: Breakfast, Lunch, Dinner, Snacks
    Day 4: Breakfast, Lunch, Dinner, Snacks
    Day 5: Breakfast, Lunch, Dinner, Snacks
    Day 6: Breakfast, Lunch, Dinner, Snacks
    Day 7: Breakfast, Lunch, Dinner, Snacks
    """

    # Call the chat completion API and handle common errors
    AuthErr = getattr(groq, "AuthenticationError", Exception)
    try:
        workout_plan = client.chat.completions.create(
            messages=[{"role": "user", "content": workout_prompt}],
            model="llama-3.1-8b-instant",
        )

        meal_plan = client.chat.completions.create(
            messages=[{"role": "user", "content": meal_prompt}],
            model="llama-3.1-8b-instant",
        )
    except AuthErr:
        raise RuntimeError("Authentication failed: invalid or expired Groq API key. Rotate the key and update your environment.")
    except AttributeError:
        raise RuntimeError("Groq client does not expose the expected chat API. Confirm SDK version.")
    except Exception as e:
        # surface a short message and let logs contain details
        raise RuntimeError(f"Groq API call failed: {e}")

    # Extract text safely
    try:
        w = workout_plan.choices[0].message.content
    except Exception:
        w = str(workout_plan)
    try:
        m = meal_plan.choices[0].message.content
    except Exception:
        m = str(meal_plan)

    return w, m


def chatbot_response(api_key: str, user_input: str) -> str:
    """Simple chatbot fallback using the same Groq chat completions endpoint."""
    if not user_input:
        return "Please enter a message."
    try:
        client = _get_groq_client(api_key)
    except Exception as e:
        return f"Chat unavailable: {e}"

    AuthErr = getattr(groq, "AuthenticationError", Exception)
    try:
        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": user_input}],
            model="llama-3.1-8b-instant",
        )
        try:
            return resp.choices[0].message.content
        except Exception:
            return str(resp)
    except AuthErr:
        return "Authentication failed for chat: invalid or expired API key."
    except Exception as e:
        return f"Chat error: {e}"

# Streamlit app
def main():
    st.markdown(
        """
        <style>
        .main-title {
            font-size: 3em;
            color: #FF6347;
            text-align: center;
            margin-bottom: 0.5em;
        }
        .description {
            font-size: 1.2em;
            color: #2E8B57;
            text-align: center;
            margin-bottom: 2em;
        }
        .css-1d391kg {
            background-color: #2E8B57 !important;
        }
        .css-1cpxqw2 {
            color: #FFFFFF !important;
        }
        .css-1n76uvr, .css-7jyd01, .css-vfskoc, .css-1ktcvv5 { 
            color: #2E8B57 !important;
        }
        </style>
        """, unsafe_allow_html=True
    )

    # Add the title image
    st.image("titlepage.jpeg", use_column_width=True)

    # Show a clear message if the API key is not available
    if not api_key:
        st.error(
            "Groq API key not found. Set it in your environment (.env) using one of: 'fitness', 'FITNESS', or 'GROQ_API_KEY',\n"
            "or add 'GROQ_API_KEY' to Streamlit secrets. The app cannot call the Groq API without this key."
        )

    st.markdown(
        """
        <div class="main-title">AI-Powered Fitness & Nutrition Coach</div>
        <div class="description">
           Welcome to the AI-Powered Fitness & Nutrition Coach, your personalized guide to achieving your fitness goals. This innovative application leverages advanced AI technology to deliver customized workout and meal plans tailored to your unique needs.
        </div>
        """, unsafe_allow_html=True
    )

    st.sidebar.header("Enter Your Details")
    
    age = st.sidebar.number_input("Age", min_value=1, max_value=100, value=25)
    weight = st.sidebar.number_input("Weight (kg)", min_value=20, max_value=200, value=70)
    height = st.sidebar.number_input("Height (cm)", min_value=100, max_value=250, value=170)
    gender = st.sidebar.selectbox("Gender", ["Male", "Female", "Other"])
    diet_pref = st.sidebar.selectbox("Diet Preferences", ["Omnivore", "Vegetarian", "Vegan", "Keto", "Paleo"])
    fitness_goal = st.sidebar.selectbox("Fitness Goal", ["Increase Upper Body Width", "Weight Loss", "Muscle Gain", "Maintenance", "Endurance", "Flexibility"])
    exercise_time = st.sidebar.slider("Exercise Time (minutes per day)", min_value=10, max_value=120, value=60)

    if st.sidebar.button("Generate Plan"):
        if api_key:
            with st.spinner('Generating your personalized fitness and meal plan...'):
                workout_plan, meal_plan = generate_plans_with_groq(api_key, age, weight, height, gender, diet_pref, fitness_goal, exercise_time)
                
                # Display the raw outputs
                st.subheader("Generated Workout Plan:")
                st.text(workout_plan)

                st.subheader("Generated Meal Plan:")
                st.text(meal_plan)

    # Chatbot section
    st.subheader("Chat with the AI Coach")
    user_input = st.text_area("If you have any questions or need further customization, ask here:")
    if st.button("Send"):
        if user_input:
            response = chatbot_response(api_key, user_input)
            st.markdown(f"*AI Coach:* {response}")
        else:
            st.error("Please enter a message to send to the AI Coach.")

if __name__ == "__main__":
    main()
