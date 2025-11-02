import os
import streamlit as st
import groq
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
import json
import re


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

# Helper function to calculate BMI and other health metrics
def calculate_health_metrics(weight, height, age, gender):
    """Calculate BMI, BMR, and daily calorie needs"""
    height_m = height / 100  # convert cm to meters
    bmi = weight / (height_m ** 2)
    
    # Calculate BMR using Mifflin-St Jeor Equation
    if gender.lower() == "male":
        bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    else:
        bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161
    
    # Calculate daily calorie needs (assuming moderate activity)
    calories_maintenance = bmr * 1.55
    
    # BMI category
    if bmi < 18.5:
        bmi_category = "Underweight"
        color = "blue"
    elif 18.5 <= bmi < 25:
        bmi_category = "Normal"
        color = "green"
    elif 25 <= bmi < 30:
        bmi_category = "Overweight"
        color = "orange"
    else:
        bmi_category = "Obese"
        color = "red"
    
    return {
        "bmi": round(bmi, 1),
        "bmi_category": bmi_category,
        "bmi_color": color,
        "bmr": round(bmr, 0),
        "calories_maintenance": round(calories_maintenance, 0)
    }

def parse_workout_to_table(workout_text):
    """Parse workout plan text into a structured table format"""
    days = []
    current_day = None
    current_content = []
    
    lines = workout_text.split('\n')
    
    for line in lines:
        # Check if line starts with "Day" followed by a number
        if re.match(r'^Day\s*\d+', line, re.IGNORECASE):
            # Save previous day if exists
            if current_day:
                days.append({
                    'Day': current_day,
                    'Workout Details': '\n'.join(current_content)
                })
            
            # Start new day
            current_day = line.strip()
            current_content = []
        elif line.strip() and current_day:
            current_content.append(line.strip())
    
    # Add last day
    if current_day and current_content:
        days.append({
            'Day': current_day,
            'Workout Details': '\n'.join(current_content)
        })
    
    return pd.DataFrame(days) if days else None

def parse_meal_to_table(meal_text):
    """Parse meal plan text into a structured table format"""
    days = []
    current_day = None
    meals = {'Breakfast': '', 'Lunch': '', 'Dinner': '', 'Snacks': ''}
    
    lines = meal_text.split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Check if line starts with "Day" followed by a number
        if re.match(r'^Day\s*\d+', line, re.IGNORECASE):
            # Save previous day if exists
            if current_day:
                days.append({
                    'Day': current_day,
                    'Breakfast': meals.get('Breakfast', ''),
                    'Lunch': meals.get('Lunch', ''),
                    'Dinner': meals.get('Dinner', ''),
                    'Snacks': meals.get('Snacks', '')
                })
            
            # Start new day
            current_day = line
            meals = {'Breakfast': '', 'Lunch': '', 'Dinner': '', 'Snacks': ''}
        
        # Check for meal types
        elif any(meal_type in line.lower() for meal_type in ['breakfast', 'lunch', 'dinner', 'snack']):
            for meal_type in ['Breakfast', 'Lunch', 'Dinner', 'Snacks']:
                if meal_type.lower() in line.lower():
                    # Extract meal content after the meal type
                    meal_content = re.sub(r'.*?'+meal_type+r'\s*:?\s*', '', line, flags=re.IGNORECASE)
                    meals[meal_type] = meal_content
                    break
        elif current_day and line:
            # Add to the last meal type
            for meal_type in reversed(['Breakfast', 'Lunch', 'Dinner', 'Snacks']):
                if meals[meal_type]:
                    meals[meal_type] += ' ' + line
                    break
    
    # Add last day
    if current_day:
        days.append({
            'Day': current_day,
            'Breakfast': meals.get('Breakfast', ''),
            'Lunch': meals.get('Lunch', ''),
            'Dinner': meals.get('Dinner', ''),
            'Snacks': meals.get('Snacks', '')
        })
    
    return pd.DataFrame(days) if days else None

# Function to generate a personalized fitness and meal plan using Groq API
def generate_plans_with_groq(api_key, age, weight, height, gender, diet_pref, fitness_goal, exercise_time, health_metrics):
    try:
        client = _get_groq_client(api_key)
    except Exception as e:
        # propagate a concise error to the caller (Streamlit will show it)
        raise RuntimeError(str(e))

    # Enhanced prompts with Pakistani context
    workout_prompt = f"""
    Generate a detailed week-long workout plan for a {age}-year-old {gender} from Pakistan who wants to achieve: {fitness_goal}.
    
    User Profile:
    - Weight: {weight} kg
    - Height: {height} cm
    - BMI: {health_metrics['bmi']} ({health_metrics['bmi_category']})
    - Available time: {exercise_time} minutes daily
    - Fitness Goal: {fitness_goal}
    
    IMPORTANT: Format your response EXACTLY as follows for each day:
    
    Day 1: [Day Name, e.g., Monday - Chest & Triceps]
    Warm-up: [5-10 min warm-up exercises]
    Main Workout:
    - Exercise 1: Sets x Reps (Rest time)
    - Exercise 2: Sets x Reps (Rest time)
    - Exercise 3: Sets x Reps (Rest time)
    Cool-down: [Stretching exercises]
    Calories Burned: ~XXX kcal
    
    Day 2: [Day Name]
    [Same format]
    
    Continue for all 7 days.
    
    Create a comprehensive workout plan considering:
    1. Limited access to gym equipment (provide home workout alternatives)
    2. Hot weather conditions in Pakistan (suggest indoor/early morning workouts)
    3. Progressive difficulty throughout the week
    4. Proper warm-up and cool-down exercises
    5. Rest days for recovery
    
    Make it practical, achievable, and culturally appropriate for Pakistan.
    """

    meal_prompt = f"""
    Generate a detailed week-long meal plan for a {age}-year-old {gender} from Pakistan following a {diet_pref} diet.
    
    User Profile:
    - Weight: {weight} kg, Height: {height} cm
    - BMI: {health_metrics['bmi']} ({health_metrics['bmi_category']})
    - Daily calorie target: ~{health_metrics['calories_maintenance']} kcal (for maintenance)
    - Fitness Goal: {fitness_goal}
    - Diet Preference: {diet_pref}
    
    IMPORTANT: Format your response EXACTLY as follows for each day:
    
    Day 1:
    Breakfast: [Complete breakfast with portions and calories]
    Lunch: [Complete lunch with portions and calories]
    Dinner: [Complete dinner with portions and calories]
    Snacks: [Snacks/beverages throughout the day]
    
    Day 2:
    Breakfast: [meal details]
    Lunch: [meal details]
    Dinner: [meal details]
    Snacks: [snack details]
    
    Continue for all 7 days.
    
    Create authentic Pakistani meal plans with:
    
    1. TRADITIONAL PAKISTANI FOODS:
    - Breakfast: Paratha, eggs, daal, halwa puri, nihari, channay, lassi, doodh patti chai
    - Lunch: Roti/naan with saalan (chicken karahi, mutton korma, daal, biryani, pulao)
    - Dinner: Similar to lunch but lighter portions
    - Snacks: Fruit chaat, samosas, pakoras, nuts, dates, roasted chana
    
    2. NUTRITIONAL BALANCE:
    - Include protein sources (chicken, mutton, fish, daal, eggs, dairy)
    - Complex carbs (brown rice, whole wheat roti, oats)
    - Healthy fats (desi ghee in moderation, nuts, olive oil)
    - Fresh vegetables and seasonal Pakistani fruits
    
    3. CULTURAL CONSIDERATIONS:
    - All foods must be Halal
    - Use common Pakistani spices and cooking methods
    - Suggest locally available ingredients
    - Consider meal timing (breakfast, lunch, evening chai, dinner)
    
    4. PORTION CONTROL:
    - Specify serving sizes (rotis, cups, grams)
    - Calorie estimates for each meal
    
    Adjust portions and recipes based on the fitness goal: {fitness_goal}
    Make it delicious, practical, and aligned with Pakistani eating habits!
    """

    # Call the chat completion API and handle common errors
    AuthErr = getattr(groq, "AuthenticationError", Exception)
    try:
        workout_plan = client.chat.completions.create(
            messages=[{"role": "user", "content": workout_prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
        )

        meal_plan = client.chat.completions.create(
            messages=[{"role": "user", "content": meal_prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
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


def chatbot_response(api_key: str, user_input: str, chat_history: list = None, user_context: dict = None) -> str:
    """Enhanced chatbot with conversation history and context awareness."""
    if not user_input:
        return "Please enter a message."
    try:
        client = _get_groq_client(api_key)
    except Exception as e:
        return f"Chat unavailable: {e}"

    # Build context-aware system prompt
    system_prompt = """You are a knowledgeable fitness and nutrition coach specializing in Pakistani culture and lifestyle. 
You provide practical, culturally appropriate advice about:
- Traditional Pakistani foods and their nutritional value
- Exercises suitable for Pakistani climate and available equipment
- Halal dietary requirements
- Local ingredients and cooking methods
- Fitness tips for South Asian body types

Be friendly, encouraging, and provide specific, actionable advice."""

    if user_context:
        system_prompt += f"""

User Profile:
- Age: {user_context.get('age', 'N/A')} years
- Weight: {user_context.get('weight', 'N/A')} kg, Height: {user_context.get('height', 'N/A')} cm
- Gender: {user_context.get('gender', 'N/A')}
- BMI: {user_context.get('bmi', 'N/A')}
- Fitness Goal: {user_context.get('fitness_goal', 'N/A')}
- Diet Preference: {user_context.get('diet_pref', 'N/A')}
- Exercise Time: {user_context.get('exercise_time', 'N/A')} min/day
"""

    # Build messages array with chat history
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add chat history if available
    if chat_history:
        messages.extend(chat_history)
    
    # Add current user message
    messages.append({"role": "user", "content": user_input})

    AuthErr = getattr(groq, "AuthenticationError", Exception)
    try:
        resp = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.8,
            max_tokens=1000,
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
    st.set_page_config(
        page_title="AI Fitness & Nutrition Coach",
        page_icon="💪",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.markdown(
        """
        <style>
        .main-title {
            font-size: 3em;
            color: #FF6347;
            text-align: center;
            margin-bottom: 0.5em;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        }
        .description {
            font-size: 1.2em;
            color: #2E8B57;
            text-align: center;
            margin-bottom: 2em;
        }
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            border-radius: 10px;
            color: white;
            text-align: center;
            margin: 10px 0;
        }
        .stDownloadButton button {
            background-color: #2E8B57;
            color: white;
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
        <div class="main-title">🇵🇰 AI-Powered Fitness & Nutrition Coach</div>
        <div class="description">
           Your personalized Pakistani fitness and nutrition guide. Get customized workout plans and authentic desi meal recommendations tailored to your goals! 🏋️‍♂️🥘
        </div>
        """, unsafe_allow_html=True
    )

    st.sidebar.header("📋 Enter Your Details")
    
    # User inputs
    age = st.sidebar.number_input("Age", min_value=15, max_value=100, value=25, help="Your current age")
    weight = st.sidebar.number_input("Weight (kg)", min_value=30, max_value=200, value=70, help="Your current weight in kilograms")
    height = st.sidebar.number_input("Height (cm)", min_value=120, max_value=250, value=170, help="Your height in centimeters")
    gender = st.sidebar.selectbox("Gender", ["Male", "Female", "Other"])
    
    # Calculate health metrics
    health_metrics = calculate_health_metrics(weight, height, age, gender)
    
    # Display health metrics in sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Your Health Metrics")
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.metric("BMI", f"{health_metrics['bmi']}")
        st.caption(f"Status: {health_metrics['bmi_category']}")
    with col2:
        st.metric("BMR", f"{int(health_metrics['bmr'])}")
        st.caption("Base Metabolic Rate")
    
    st.sidebar.metric("Daily Calories", f"{int(health_metrics['calories_maintenance'])}", help="For maintenance")
    
    st.sidebar.markdown("---")
    
    # Diet and fitness preferences
    diet_pref = st.sidebar.selectbox(
        "🍽️ Diet Preferences", 
        ["Omnivore (Non-Veg)", "Vegetarian", "Vegan", "Keto", "High Protein", "Balanced"],
        help="Choose your dietary preference"
    )
    
    fitness_goal = st.sidebar.selectbox(
        "🎯 Fitness Goal", 
        ["Weight Loss", "Muscle Gain", "Increase Upper Body Width", "General Fitness", "Endurance", "Flexibility & Mobility", "Maintenance"],
        help="What do you want to achieve?"
    )
    
    exercise_time = st.sidebar.slider(
        "⏱️ Daily Exercise Time (minutes)", 
        min_value=15, 
        max_value=180, 
        value=45, 
        step=15,
        help="How much time can you dedicate daily?"
    )
    
    # Store user context for chatbot
    user_context = {
        'age': age,
        'weight': weight,
        'height': height,
        'gender': gender,
        'bmi': health_metrics['bmi'],
        'fitness_goal': fitness_goal,
        'diet_pref': diet_pref,
        'exercise_time': exercise_time
    }

    
    st.sidebar.markdown("---")
    generate_button = st.sidebar.button("🚀 Generate My Plan", type="primary", use_container_width=True)

    if generate_button:
        if api_key:
            with st.spinner('🔮 Generating your personalized fitness and meal plan...'):
                try:
                    workout_plan, meal_plan = generate_plans_with_groq(
                        api_key, age, weight, height, gender, diet_pref, 
                        fitness_goal, exercise_time, health_metrics
                    )
                    
                    # Store in session state
                    st.session_state['workout_plan'] = workout_plan
                    st.session_state['meal_plan'] = meal_plan
                    st.session_state['user_context'] = user_context
                    st.session_state['generation_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    st.success("✅ Your personalized plans are ready!")
                    
                except Exception as e:
                    st.error(f"❌ Error generating plans: {str(e)}")
        else:
            st.error("⚠️ API key not found. Please configure your Groq API key.")
    
    # Display generated plans if they exist
    if 'workout_plan' in st.session_state and 'meal_plan' in st.session_state:
        
        st.markdown("---")
        
        # Create tabs for better organization
        tab1, tab2, tab3 = st.tabs(["💪 Workout Plan", "🥘 Meal Plan", "📊 Summary"])
        
        with tab1:
            st.subheader("Your Personalized Workout Plan")
            
            # Try to parse and display as table
            workout_df = parse_workout_to_table(st.session_state['workout_plan'])
            
            if workout_df is not None and not workout_df.empty:
                st.dataframe(
                    workout_df,
                    use_container_width=True,
                    height=400
                )
            else:
                # Fallback to markdown if parsing fails
                st.markdown(st.session_state['workout_plan'])
            
            # Download button for workout plan
            st.download_button(
                label="📥 Download Workout Plan",
                data=st.session_state['workout_plan'],
                file_name=f"workout_plan_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain"
            )
        
        with tab2:
            st.subheader("Your Personalized Meal Plan")
            
            # Try to parse and display as table
            meal_df = parse_meal_to_table(st.session_state['meal_plan'])
            
            if meal_df is not None and not meal_df.empty:
                st.dataframe(
                    meal_df,
                    use_container_width=True,
                    height=400
                )
            else:
                # Fallback to markdown if parsing fails
                st.markdown(st.session_state['meal_plan'])
            
            # Download button for meal plan
            st.download_button(
                label="📥 Download Meal Plan",
                data=st.session_state['meal_plan'],
                file_name=f"meal_plan_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain"
            )
        
        with tab3:
            st.subheader("📊 Your Profile Summary")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f"""
                **Personal Info**
                - Age: {age} years
                - Weight: {weight} kg
                - Height: {height} cm
                - Gender: {gender}
                """)
            
            with col2:
                st.markdown(f"""
                **Health Metrics**
                - BMI: {health_metrics['bmi']} ({health_metrics['bmi_category']})
                - BMR: {int(health_metrics['bmr'])} kcal/day
                - Daily Calories: {int(health_metrics['calories_maintenance'])} kcal
                """)
            
            with col3:
                st.markdown(f"""
                **Goals & Preferences**
                - Goal: {fitness_goal}
                - Diet: {diet_pref}
                - Exercise Time: {exercise_time} min/day
                """)
            
            st.info(f"📅 Plans generated on: {st.session_state.get('generation_time', 'N/A')}")
            
            # Download combined plan
            combined_plan = f"""
AI-POWERED FITNESS & NUTRITION COACH - PERSONALIZED PLAN
Generated: {st.session_state.get('generation_time', 'N/A')}

{'='*70}
PROFILE SUMMARY
{'='*70}
Age: {age} years | Weight: {weight} kg | Height: {height} cm | Gender: {gender}
BMI: {health_metrics['bmi']} ({health_metrics['bmi_category']})
BMR: {int(health_metrics['bmr'])} kcal/day | Daily Calories: {int(health_metrics['calories_maintenance'])} kcal
Fitness Goal: {fitness_goal}
Diet Preference: {diet_pref}
Exercise Time: {exercise_time} minutes/day

{'='*70}
WORKOUT PLAN
{'='*70}
{st.session_state['workout_plan']}

{'='*70}
MEAL PLAN
{'='*70}
{st.session_state['meal_plan']}
"""
            
            st.download_button(
                label="📥 Download Complete Plan (Workout + Meal)",
                data=combined_plan,
                file_name=f"complete_fitness_plan_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain",
                use_container_width=True
            )

    # Chatbot section with conversation history
    st.markdown("---")
    st.subheader("💬 Chat with AI Coach")
    st.markdown("Have a conversation about fitness, nutrition, exercises, or Pakistani foods!")
    
    # Initialize chat history in session state
    if 'chat_history' not in st.session_state:
        st.session_state['chat_history'] = []
    
    # Display chat history
    if st.session_state['chat_history']:
        st.markdown("### Conversation History")
        chat_container = st.container()
        with chat_container:
            for i, message in enumerate(st.session_state['chat_history']):
                if message['role'] == 'user':
                    st.markdown(f"**👤 You:** {message['content']}")
                elif message['role'] == 'assistant':
                    st.markdown(f"**🤖 AI Coach:** {message['content']}")
                    
            st.markdown("---")
    
    # Chat input
    user_input = st.text_area(
        "Your message:",
        placeholder="E.g., 'Can I replace chicken with fish?', 'What exercises for back pain?', 'How to make daal more protein-rich?'",
        height=100,
        key="chat_input"
    )
    
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        send_button = st.button("Send 📤", use_container_width=True)
    with col2:
        clear_button = st.button("Clear Chat 🗑️", use_container_width=True)
    
    if clear_button:
        st.session_state['chat_history'] = []
        st.rerun()
    
    if send_button:
        if user_input and user_input.strip():
            with st.spinner("🤔 Thinking..."):
                # Get response with chat history
                response = chatbot_response(
                    api_key, 
                    user_input,
                    st.session_state['chat_history'],
                    st.session_state.get('user_context', user_context)
                )
                
                # Add user message and assistant response to history
                st.session_state['chat_history'].append({
                    'role': 'user',
                    'content': user_input
                })
                st.session_state['chat_history'].append({
                    'role': 'assistant',
                    'content': response
                })
                
                # Rerun to display updated conversation
                st.rerun()
        else:
            st.warning("⚠️ Please enter a message to send to the AI Coach.")

if __name__ == "__main__":
    main()
