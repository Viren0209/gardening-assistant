from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import openai
import requests
import os

# THIS IS THE FIX: Explicitly tell Flask where the templates folder is.
app = Flask(__name__, template_folder='templates')

CORS(app)

# This part will read the secret keys we add later
openai.api_key = os.getenv("OPENAI_API_KEY")
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# ---------- Helper Function for Weather ----------
# A small reusable function to get weather data
def get_weather_data(lat, lon):
    if not lat or not lon:
        return "Weather data not available (location not provided)."

    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        temp = data['main']['temp']
        weather = data['weather'][0]['description']
        return f"Current weather: {temp}°C, {weather}."
    except requests.exceptions.RequestException as e:
        print(f"Weather API error: {e}")
        return "Could not fetch weather data."

# ---------- Main Route to Serve the Webpage ----------
# When a user visits our website, this function sends them the index.html file
@app.route('/')
def home():
    return render_template('index.html')

# ---------- API Route for General Questions ----------
@app.route('/ask', methods=['POST'])
def ask_gpt():
    data = request.get_json()
    user_query = data.get('query')

    if not user_query:
        return jsonify({'error': 'No query provided'}), 400

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a friendly and practical gardening expert."},
                {"role": "user", "content": user_query}
            ]
        )
        answer = response.choices[0].message.content
        return jsonify({'answer': answer})
    except Exception as e:
        return jsonify({'error': f'OpenAI API call failed: {e}'}), 500

# ---------- API Route for Plant Identification ----------
@app.route('/identify', methods=['POST'])
def identify_plant():
    if 'image' not in request.files:
        return jsonify({'error': 'No image file uploaded'}), 400

    image = request.files['image']
    url = f"https://my-api.plantnet.org/v2/identify/all?api-key={PLANTNET_API_KEY}"

    try:
        files = {'images': (image.filename, image.read(), image.content_type)}
        response = requests.post(url, files=files)
        response.raise_for_status()
        result = response.json()

        if not result.get('results'):
            return jsonify({'error': 'Plant could not be identified. Try a clearer image.'})

        top_result = result['results'][0]
        plant_name = top_result['species']['scientificNameWithoutAuthor']
        common_names = ", ".join(top_result['species'].get('commonNames', ['N/A']))
        score = top_result['score']

        return jsonify({
            'message': f"Identified: {plant_name}\nCommon Names: {common_names}\nConfidence: {score:.2%}"
        })
    except Exception as e:
        return jsonify({'error': f'PlantNet API call failed: {e}'}), 500

# ---------- API Route for Disease Diagnosis ----------
@app.route('/diagnose', methods=['POST'])
def diagnose_disease():
    data = request.get_json()
    user_query = data.get('query')
    lat = data.get('lon')
    lon = data.get('lon')

    if not user_query:
        return jsonify({'error': 'No description provided'}), 400

    weather_info = get_weather_data(lat, lon)
    full_prompt = f"User's location context: {weather_info}\n\nUser's observation: '{user_query}'"

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are a plant disease expert. Based on the user's description and local weather, "
                    "diagnose the issue. Provide a clear, beginner-friendly answer including:\n"
                    "- Possible Cause\n- Recommended Actions (organic and chemical options)"
                )},
                {"role": "user", "content": full_prompt}
            ]
        )
        diagnosis = response.choices[0].message.content
        return jsonify({'answer': diagnosis})
    except Exception as e:
        return jsonify({'error': f'Diagnosis failed: {e}'}), 500