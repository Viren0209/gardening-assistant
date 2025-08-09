from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import requests
import openai

# --- Flask app (templates + static folders) ---
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# --- Secrets from environment (Render/Local) ---
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
PLANTNET_API_KEY   = os.getenv("PLANTNET_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# Configure OpenAI client (older SDK style to stay compatible with your setup)
openai.api_key = OPENAI_API_KEY

# ---------- Helpers ----------

def get_weather_data(lat, lon):
    """Return a short weather string or a fallback message."""
    if not lat or not lon:
        return "Weather data not available (location not provided)."
    try:
        url = (
            "https://api.openweathermap.org/data/2.5/weather"
            f"?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
        )
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        temp = data["main"]["temp"]
        desc = data["weather"][0]["description"]
        hum  = data["main"]["humidity"]
        return f"Current weather: {temp}°C, {desc}, humidity {hum}%."
    except Exception as e:
        print("Weather error:", e)
        return "Weather service unavailable."

def ask_openai(system_msg, user_msg):
    """Call OpenAI Chat Completions and return text, or raise."""
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.5,
    )
    return resp.choices[0].message.content

# ---------- Routes ----------

@app.route("/", methods=["GET"])
def home():
    """Serve the UI. This MUST use render_template so the browser renders HTML (not raw text)."""
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    """Free-form gardening Q&A (optionally weather-aware)."""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    lat   = data.get("lat")
    lon   = data.get("lon")

    if not query:
        return jsonify({"error": "No query provided."}), 400

    try:
        weather = get_weather_data(lat, lon)
        prompt = f"{weather}\n\nUser question: {query}"
        system = (
            "You are a friendly, practical gardening expert. "
            "Give concise, step-by-step, India-friendly advice. "
            "Include varieties, timing, and simple actions."
        )
        answer = ask_openai(system, prompt)
        return jsonify({"answer": answer})
    except Exception as e:
        print("OpenAI /ask error:", e)
        return jsonify({"error": "AI response failed."}), 500


@app.route("/identify", methods=["POST"])
def identify():
    """Identify a plant from an uploaded image using PlantNet."""
    if "image" not in request.files:
        return jsonify({"error": "No image file uploaded."}), 400

    image = request.files["image"]
    if image.filename == "":
        return jsonify({"error": "Empty filename."}), 400

    try:
        api_url = f"https://my-api.plantnet.org/v2/identify/all?api-key={PLANTNET_API_KEY}"
        # PlantNet expects field name 'images'
        files = {"images": (image.filename, image.stream, image.mimetype)}
        resp = requests.post(api_url, files=files, timeout=60)
        resp.raise_for_status()
        result = resp.json()

        if not result.get("results"):
            return jsonify({"error": "No plant identified. Try a clearer photo."}), 404

        top = result["results"][0]
        sci = top["species"].get("scientificNameWithoutAuthor") or top["species"].get("scientificName")
        common = top["species"].get("commonNames", [])
        score = top.get("score", 0)

        return jsonify({
            "scientific_name": sci,
            "common_names": common,
            "confidence": round(float(score) * 100, 2)
        })
    except requests.HTTPError as e:
        print("PlantNet HTTP error:", e, getattr(e.response, "text", ""))
        return jsonify({"error": "PlantNet API error."}), 502
    except Exception as e:
        print("PlantNet general error:", e)
        return jsonify({"error": "Plant identification failed."}), 500


@app.route("/diagnose", methods=["POST"])
def diagnose():
    """Describe symptoms to get likely disease + actions (weather-aware)."""
    data = request.get_json(silent=True) or {}
    desc = data.get("query", "").strip()
    lat  = data.get("lat")
    lon  = data.get("lon")

    if not desc:
        return jsonify({"error": "No description provided."}), 400

    try:
        weather = get_weather_data(lat, lon)
        prompt = (
            f"{weather}\n\nUser observation: {desc}\n\n"
            "Return a short diagnosis with:\n"
            "- Likely cause/disease\n- Key symptoms\n- Immediate actions\n"
            "- Organic & chemical options (with common actives)\n- Prevention tips"
        )
        system = "You are a plant pathology expert for home gardeners. Keep it simple and safe."
        answer = ask_openai(system, prompt)
        return jsonify({"answer": answer})
    except Exception as e:
        print("OpenAI /diagnose error:", e)
        return jsonify({"error": "Diagnosis failed."}), 500


# Local debug (Render uses gunicorn, so this block is ignored there)
if __name__ == "__main__":
    # Bind to 0.0.0.0 so it’s reachable in containers; default port 5000.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)