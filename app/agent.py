# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory.vertex_ai_memory_bank_service import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from app.a2ui_utils import a2ui_callback


MODEL = "gemini-3.6-flash"

# Hardcoded GCP Project ID, GCS bucket, Sandbox environment, and Memory Bank ID
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-03-3746e4b526aa"
GCS_MEDIA_BUCKET = "glow-aesthetics-media-03-3746e4b526aa"
SANDBOX_RESOURCE_NAME = (
    "projects/1009109819911/locations/us-east1/reasoningEngines/921574362518126592/sandboxEnvironments/6553955716707647488"
)
MEMORY_BANK_ID = "921574362518126592"


def memory_bank_service_builder() -> VertexAiMemoryBankService:
    """Builds the VertexAiMemoryBankService for deployed environments."""
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )



def get_firestore_client() -> firestore.Client:
    """Returns a Firestore client explicitly pinned to the GCP project ID."""
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def list_treatments(concern: str = "") -> list[dict]:
    """Lists aesthetic clinic treatments from Firestore, optionally filtered by skin concern.

    Args:
        concern: Optional skin concern to filter by (e.g. 'pores', 'acne scars',
                 'hyperpigmentation', 'fine lines', 'volume loss', 'hydration').
                 Leave empty to view all treatments.

    Returns:
        A list of treatments matching the concern with name, category, duration, price, and downtime.
    """
    db = get_firestore_client()
    docs = db.collection("treatments").stream()
    results = []
    concern_filter = concern.strip().lower()

    for doc in docs:
        data = doc.to_dict()
        if not concern_filter:
            results.append(data)
        else:
            target_concerns = [c.lower() for c in data.get("target_concerns", [])]
            category = data.get("category", "").lower()
            name = data.get("name", "").lower()
            desc = data.get("description", "").lower()

            if (
                any(concern_filter in tc for tc in target_concerns)
                or concern_filter in category
                or concern_filter in name
                or concern_filter in desc
            ):
                results.append(data)

    return results


def get_treatment_details(treatment_name_or_id: str) -> dict:
    """Retrieves full details and aftercare guidelines for a specific treatment from Firestore.

    Args:
        treatment_name_or_id: The ID (e.g. 'hydrafacial-deluxe', 'microneedling-rf',
                              'vi-peel-precision', 'clear-brilliant-laser') or name of the treatment.

    Returns:
        Dictionary containing description, benefits, price, downtime, and aftercare instructions.
    """
    db = get_firestore_client()
    treatments_ref = db.collection("treatments")

    # Try direct ID lookup
    target_clean = treatment_name_or_id.strip().lower()
    doc = treatments_ref.document(target_clean).get()
    if doc.exists:
        return doc.to_dict()

    # Search by partial match on name or ID
    for d in treatments_ref.stream():
        data = d.to_dict()
        if target_clean in data.get("name", "").lower() or target_clean in data.get("id", "").lower():
            return data

    return {"error": f"Treatment '{treatment_name_or_id}' was not found in the clinic catalog."}


def book_consultation(
    client_name: str,
    treatment_name: str,
    preferred_date: str,
    preferred_time: str,
    notes: str = "",
) -> dict:
    """Schedules a new consultation or treatment appointment and writes the record to Firestore.

    Args:
        client_name: Full name of the client.
        treatment_name: Name of the treatment or consultation requested.
        preferred_date: Requested appointment date in YYYY-MM-DD format (e.g. '2026-11-15').
        preferred_time: Requested appointment time slot (e.g. '10:00 AM' or '3:30 PM').
        notes: Client skin notes, primary concerns, or medical sensitivities.

    Returns:
        A confirmation dictionary including the booking ID, confirmation status, and appointment details.
    """
    db = get_firestore_client()
    booking_id = f"BK-{uuid.uuid4().hex[:6].upper()}"

    booking_record = {
        "booking_id": booking_id,
        "client_name": client_name,
        "treatment_name": treatment_name,
        "date": preferred_date,
        "time_slot": preferred_time,
        "status": "confirmed",
        "notes": notes,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    db.collection("consultations").document(booking_id).set(booking_record)
    return {
        "booking_id": booking_id,
        "status": "confirmed",
        "message": f"Consultation booked successfully for {client_name}.",
        "details": booking_record,
    }


def get_consultation(booking_id: str) -> dict:
    """Reads consultation booking details from Firestore by booking ID.

    Args:
        booking_id: The booking confirmation code (e.g. 'BK-1001').

    Returns:
        Dictionary with booking details or an error message if not found.
    """
    db = get_firestore_client()
    doc = db.collection("consultations").document(booking_id.strip()).get()
    if doc.exists:
        return doc.to_dict()
    return {"error": f"Booking '{booking_id}' not found."}


def get_current_time(timezone_str: str = "America/New_York") -> str:
    """Gets the current date and time for scheduling references.

    Args:
        timezone_str: Timezone string (default 'America/New_York').

    Returns:
        Current formatted date and time.
    """
    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        tz = ZoneInfo("UTC")
    now = datetime.datetime.now(tz)
    return f"Current date and time ({timezone_str}): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"


def check_active_ingredient_safety(
    active_ingredient: str,
    treatment_name: str,
    timing: str = "after",
) -> dict:
    """Checks whether a skincare active ingredient is safe to use before or after a clinic treatment.

    Args:
        active_ingredient: Skincare ingredient (e.g. 'retinol', 'tretinoin', 'glycolic acid',
                           'salicylic acid', 'vitamin c', 'hyaluronic acid').
        treatment_name: Procedure name (e.g. 'VI Peel', 'Microneedling', 'Clear + Brilliant',
                        'HydraFacial', 'Dermal Filler').
        timing: 'before' for pre-treatment preparation or 'after' for post-care recovery. Defaults to 'after'.

    Returns:
        Dictionary with safety status ('safe', 'avoid', 'caution'), pause recommendations, and clinical guidance.
    """
    ing = active_ingredient.lower().strip()
    tx = treatment_name.lower().strip()
    is_before = timing.lower().strip() == "before"

    # Gentle / barrier-friendly ingredients
    if any(safe in ing for safe in ["hyaluronic", "ceramide", "glycerin", "squalane", "centella", "cica", "panthenol"]):
        return {
            "ingredient": active_ingredient,
            "status": "safe",
            "recommendation": f"{active_ingredient.title()} is gentle and barrier-repairing. Safe to use {'before' if is_before else 'after'} {treatment_name}.",
            "guidance": "Hydrating and restorative ingredients are actively encouraged to support skin barrier recovery.",
        }

    # Retinoids (retinol, tretinoin, adapalene)
    if any(r in ing for r in ["retin", "tretinoin", "adapalene", "tazorac", "differin"]):
        if any(t in tx for t in ["peel", "laser", "morpheus", "microneedl"]):
            window = "5 to 7 days before" if is_before else "7 to 10 days after"
            return {
                "ingredient": active_ingredient,
                "status": "avoid",
                "recommendation": f"Discontinue {active_ingredient} {window} your {treatment_name}.",
                "guidance": "Retinoids significantly compromise barrier tolerance and cause severe irritation on sensitized skin.",
            }
        else:
            window = "48 hours before" if is_before else "48 hours after"
            return {
                "ingredient": active_ingredient,
                "status": "caution",
                "recommendation": f"Pause {active_ingredient} {window} {treatment_name}.",
                "guidance": "Allows the skin to normalize without excessive peeling.",
            }

    # Direct chemical exfoliants (AHA / BHA)
    if any(a in ing for a in ["glycolic", "salicylic", "lactic", "aha", "bha", "mandelic", "exfoliat"]):
        window = "3 to 5 days before" if is_before else "5 to 7 days after"
        return {
            "ingredient": active_ingredient,
            "status": "avoid",
            "recommendation": f"Do not use {active_ingredient} {window} your {treatment_name}.",
            "guidance": "Exfoliating acids will over-sensitize skin and risk hyperpigmentation or chemical burns.",
        }

    # Vitamin C / L-Ascorbic Acid
    if any(c in ing for c in ["vitamin c", "ascorbic"]):
        if not is_before and any(t in tx for t in ["peel", "laser", "microneedl", "morpheus"]):
            return {
                "ingredient": active_ingredient,
                "status": "caution",
                "recommendation": f"Wait 3 to 5 days after {treatment_name} before resuming Vitamin C.",
                "guidance": "Low pH ascorbic acid can cause stinging or erythema on freshly treated skin.",
            }

    return {
        "ingredient": active_ingredient,
        "status": "caution",
        "recommendation": f"Use caution with {active_ingredient} {'before' if is_before else 'after'} {treatment_name}.",
        "guidance": "When recovering, prioritize gentle hydration, soothing barrier moisturizers, and broad-spectrum mineral SPF.",
    }


def get_local_uv_and_sun_safety(city: str) -> dict:
    """Fetches real-time live UV index, temperature, and skin sun safety recommendations for a city.

    Use this tool to advise patients on post-treatment sun care and SPF requirements (especially
    after chemical peels, lasers, and microneedling).

    Args:
        city: City or location name (e.g. 'Miami', 'New York', 'Los Angeles', 'London').

    Returns:
        Dictionary with location name, current UV index, maximum UV index today, risk level,
        temperature, and clinical sun safety recommendations.
    """
    try:
        # 1. Geocode city name via Open-Meteo public geocoding API
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "GlowAesthetics/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            geo_data = json.loads(resp.read().decode())

        if not geo_data.get("results"):
            return {"error": f"Could not find coordinates for city '{city}'."}

        loc = geo_data["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        loc_name = f"{loc['name']}, {loc.get('admin1', '')} {loc.get('country', '')}".strip()

        # 2. Query Open-Meteo forecast for real-time and daily max UV index
        forecast_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=uv_index,temperature_2m&daily=uv_index_max&timezone=auto"
        )
        req_f = urllib.request.Request(forecast_url, headers={"User-Agent": "GlowAesthetics/1.0"})
        with urllib.request.urlopen(req_f, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        current_uv = data.get("current", {}).get("uv_index", 0.0)
        max_uv = data.get("daily", {}).get("uv_index_max", [current_uv])[0]
        temp_c = data.get("current", {}).get("temperature_2m", 0.0)
        temp_f = round(temp_c * 9 / 5 + 32, 1)

        # 3. Clinical dermatological assessment
        if max_uv < 3:
            risk = "Low"
            spf_advice = "Daily broad-spectrum SPF 30 is sufficient for standard indoor/outdoor routines."
        elif max_uv < 6:
            risk = "Moderate"
            spf_advice = "SPF 30-50 required. Reapply every 2 hours if outdoors. Wear a wide-brim hat if recently treated with peels or lasers."
        elif max_uv < 8:
            risk = "High"
            spf_advice = "SPF 50+ mineral sunscreen mandatory. Seek shade between 10 AM and 4 PM. Avoid direct sun on healing skin."
        else:
            risk = "Very High to Extreme"
            spf_advice = "Severe burn & pigment risk. Avoid prolonged outdoor exposure. Strictly physical mineral SPF 50+ and UV shielding."

        return {
            "location": loc_name,
            "current_uv_index": current_uv,
            "max_uv_index_today": max_uv,
            "risk_level": risk,
            "temperature": f"{temp_c}°C / {temp_f}°F",
            "sun_protection_guidance": spf_advice,
        }
    except Exception as e:
        return {
            "error": f"Failed to retrieve live UV data for {city}: {str(e)}",
            "fallback_advice": "Always apply broad-spectrum mineral SPF 50 daily after clinic treatments.",
        }


def geocode_address(address: str) -> dict:
    """Uses Google Maps Geocoding API to convert an address or place name into geographic coordinates.

    Args:
        address: The address or place name to geocode (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        Dictionary containing formatted_address, latitude, longitude, and status.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return {"error": "GOOGLE_MAPS_API_KEY is not configured. Please set your Maps API key in .env."}

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlowAesthetics/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return {
                "status": data.get("status", "ZERO_RESULTS"),
                "error": data.get("error_message", f"No geocoding results found for '{address}'."),
            }

        first_res = data["results"][0]
        loc = first_res.get("geometry", {}).get("location", {})
        return {
            "status": "OK",
            "name": address,
            "address": first_res.get("formatted_address", ""),
            "location": {"latitude": loc.get("lat"), "longitude": loc.get("lng")},
        }
    except Exception as e:
        return {"error": f"Geocoding request failed: {str(e)}"}


def search_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "spa",
    radius_meters: float = 5000.0,
) -> dict:
    """Uses Google Places API (New) searchNearby REST endpoint to find nearby places of a given type.

    Args:
        latitude: Center latitude coordinate.
        longitude: Center longitude coordinate.
        place_type: Type of place to search for (e.g. 'spa', 'beauty_salon', 'doctor'). Defaults to 'spa'.
        radius_meters: Search radius in meters (up to 50000.0). Defaults to 5000.0 (5km).

    Returns:
        Dictionary with matching places containing name, address, and location coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return {"error": "GOOGLE_MAPS_API_KEY is not configured. Please set your Maps API key in .env."}

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    body = {
        "includedTypes": [place_type],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": min(radius_meters, 50000.0),
            }
        },
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        raw_places = data.get("places", [])
        results = []
        for p in raw_places:
            results.append({
                "name": p.get("displayName", {}).get("text", ""),
                "address": p.get("formattedAddress", ""),
                "location": p.get("location", {}),
            })
        return {"places": results, "total_found": len(results)}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        return {"error": f"Places API returned HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"error": f"Places search failed: {str(e)}"}


def generate_treatment_image(
    prompt: str,
    tool_context: ToolContext = None,
) -> dict:
    """Generates an aesthetic visualization image for a clinic treatment or skincare item using gemini-3.1-flash-lite-image in the global region.

    Saves the image into the agent Playground's Artifacts panel and uploads the raw image bytes
    directly to the public Cloud Storage bucket, returning its public HTTPS URL.

    Args:
        prompt: Visual description of the treatment, clinical procedure, or skincare item to generate.
        tool_context: Injected tool context for saving artifacts into the agent playground.

    Returns:
        Dictionary with status, artifact filename, and public Cloud Storage HTTPS URL.
    """
    try:
        # 1. Generate image using gemini-3.1-flash-lite-image in global region
        client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )
        enhanced_prompt = (
            f"Aesthetic skincare and luxury medical clinic: {prompt}. "
            "High resolution, clean minimalist spa aesthetic, soft professional lighting."
        )
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=[enhanced_prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.parts:
            for part in response.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return {"error": "Failed to generate image from model response."}

        filename = f"treatment_{uuid.uuid4().hex[:8]}.jpg"

        # 2. (1) Save artifact in tool_context so it shows in Playground's Artifacts panel
        if tool_context is not None:
            part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=part)

        # 3. (2) Upload directly to public Cloud Storage bucket from bytes (no local file path)
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_MEDIA_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_MEDIA_BUCKET}/{filename}"

        return {
            "status": "success",
            "prompt": prompt,
            "artifact_filename": filename,
            "public_url": public_url,
        }
    except Exception as e:
        return {"error": f"Image generation or upload failed: {str(e)}"}


def generate_treatment_video(
    prompt: str,
    tool_context: ToolContext = None,
) -> dict:
    """Generates a short aesthetic video for a clinic treatment or skincare item using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Saves the generated video as an artifact so it shows up in the Playground's Artifacts panel,
    and uploads the video bytes directly to the public Cloud Storage bucket, returning its public HTTPS URL.

    Args:
        prompt: Description of the aesthetic treatment or skincare item to generate video for (e.g. 'gentle hydrafacial infusion mist').
        tool_context: Injected tool context for saving artifacts in the agent playground.

    Returns:
        Dictionary with status, prompt, artifact_filename, and public Cloud Storage HTTPS URL.
    """
    try:
        client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )
        enhanced_prompt = (
            f"Luxury medical aesthetics and skincare clinic: {prompt}. "
            "Clean, serene, ultra-high quality professional aesthetic procedure footage."
        )
        interaction = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=[{"type": "text", "text": enhanced_prompt}],
            response_format=[{"type": "video"}],
        )

        video_bytes = None
        mime_type = "video/mp4"
        if hasattr(interaction, "steps") and interaction.steps:
            for step in interaction.steps:
                if getattr(step, "type", "") == "model_output" and hasattr(step, "content"):
                    for content_item in step.content:
                        if getattr(content_item, "type", "") == "video":
                            raw_data = getattr(content_item, "data", None)
                            if raw_data:
                                if isinstance(raw_data, str):
                                    video_bytes = base64.b64decode(raw_data)
                                elif isinstance(raw_data, bytes):
                                    video_bytes = raw_data
                            mime_type = getattr(content_item, "mime_type", "video/mp4") or "video/mp4"
                            break
                if video_bytes:
                    break

        if not video_bytes:
            return {"error": "Failed to extract generated video bytes from model response."}

        filename = f"treatment_video_{uuid.uuid4().hex[:8]}.mp4"

        # 1. Save artifact with tool_context.save_artifact so it appears in Playground's Artifacts panel
        if tool_context is not None:
            part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=part)

        # 2. Upload video bytes to the public Cloud Storage bucket and return public URL
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_MEDIA_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_MEDIA_BUCKET}/{filename}"

        return {
            "status": "success",
            "prompt": prompt,
            "artifact_filename": filename,
            "public_url": public_url,
        }
    except Exception as e:
        return {"error": f"Video generation or upload failed: {str(e)}"}


def generate_post_treatment_preview(
    treatment_name: str,
    target_area: str,
    client_facial_features: str,
    expected_aesthetic_outcome: str,
    tool_context: ToolContext = None,
) -> dict:
    """Generates a high-resolution clinical aesthetic simulation image showing the post-treatment result of Botox or Dermal Fillers applied to the client's face.

    Uses gemini-3.1-flash-lite-image in the global region to generate a realistic visual preview
    showing subtle, natural aesthetic enhancement (e.g. smoothed dynamic lines for Botox, restored volume for fillers).
    Saves the image into the agent Playground's Artifacts panel and uploads to the public Cloud Storage bucket,
    returning its public HTTPS URL so it can be displayed in an A2UI card.

    Args:
        treatment_name: Aesthetic injectable treatment (e.g. 'Botox (Botulinum Toxin)' or 'Dermal Fillers (Hyaluronic Acid)').
        target_area: Facial anatomical area (e.g. 'Forehead & Glabellar Frown Lines', 'Crow\'s Feet', 'Cheekbones & Midface Volume', 'Lips & Perioral Lines', 'Nasolabial Folds').
        client_facial_features: Description of client's facial appearance, age bracket, and skin tone based on their uploaded photo.
        expected_aesthetic_outcome: Clinical aesthetic result (e.g. 'Softened dynamic expression lines, smooth youthful forehead, natural facial mobility preserved' or 'Naturally restored midface cheek fullness and subtle contour lift').
        tool_context: Injected tool context for saving artifacts in the agent playground.

    Returns:
        Dictionary with status, treatment_name, target_area, artifact_filename, and public Cloud Storage HTTPS URL.
    """
    try:
        client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )
        prompt = (
            f"Clinical medical aesthetics post-treatment result: Close-up beauty portrait showing the natural, subtle, refined outcome of {treatment_name} in the {target_area}. "
            f"Client profile: {client_facial_features}. Aesthetic result: {expected_aesthetic_outcome}. "
            "High resolution, natural skin texture, soft professional clinic dermatology lighting, elegant aesthetic medspa standard, clean aesthetic."
        )
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.parts:
            for part in response.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return {"error": "Failed to generate post-treatment simulation image."}

        filename = f"post_treatment_{uuid.uuid4().hex[:8]}.jpg"

        if tool_context is not None:
            part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=part)

        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_MEDIA_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_MEDIA_BUCKET}/{filename}"

        return {
            "status": "success",
            "treatment_name": treatment_name,
            "target_area": target_area,
            "artifact_filename": filename,
            "public_url": public_url,
            "note": "Post-treatment visual preview generated successfully. Display this image URL to the client.",
        }
    except Exception as e:
        return {"error": f"Post-treatment simulation failed: {str(e)}"}


def generate_face_makeover_preview(
    makeover_style: str,
    target_features: str,
    technique: str,
    client_facial_features: str,
    desired_aesthetic_outcome: str,
    tool_context: ToolContext = None,
) -> dict:
    """Generates a high-definition clinical aesthetic makeover simulation showing facial contouring and beautification options applied to the client's face.

    Supports premier aesthetic methodologies:
    - 'Picasso Technique (Architectural Full-Face Harmonization)': Full-face vector mapping, Phi golden-ratio proportions, structural anchor points across temples, cheeks, chin, and jawline for global balance.
    - 'Russian Lip Technique & Cupid\'s Bow Sculpting': Vertical micro-droplet injection creating height, crisp vermilion border, and accentuated Cupid's bow with a flat side profile.
    - 'Nefertiti Mandibular Jawline & Chin Sculpting': Razor-sharp jawline definition, sculpted gonial angle, and elongated chin apex.
    - 'MD Codes™ Midface & Cheek Elevation': Precise anatomical anchoring restoring cheek apex projection and softening tear troughs.

    Uses gemini-3.1-flash-lite-image in the global region. Saves the image artifact to tool_context and uploads
    to the public Cloud Storage bucket, returning the permanent HTTPS URL for A2UI rendering.

    Args:
        makeover_style: The makeover category (e.g. 'Picasso Full-Face Harmonization', 'Russian Lip Filler & Cupid\'s Bow', 'Nefertiti Jawline & Chin Contour', 'MD Codes Cheek Lift').
        target_features: Specific facial features being enhanced (e.g. 'Lips & Vermilion Border', 'Jawline, Chin & Gonial Angle', 'Full Face, Temples & Cheeks').
        technique: Aesthetic injection or contouring methodology (e.g. 'Picasso structural vector balancing', 'Russian vertical fanning micro-droplets', 'MD Codes Ck1-Ck3 structural bolus', 'Mandibular cannula contouring').
        client_facial_features: Description of the client's facial structure, skin tone, and features from their uploaded photo.
        desired_aesthetic_outcome: The targeted aesthetic transformation (e.g. 'Lush doll-like lips with defined Cupid\'s bow and flat profile' or 'Harmonious full-face architectural balance without overfilling').
        tool_context: Injected tool context for saving artifacts in the playground.

    Returns:
        Dictionary containing status, makeover_style, target_features, technique, public_url, and artifact_filename.
    """
    try:
        client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )

        style_lower = makeover_style.lower()
        if "picasso" in style_lower or "harmonization" in style_lower or "full face" in style_lower:
            technique_focus = (
                "Architectural full-face facial balancing and structural harmonization inspired by the Picasso Technique. "
                "Global anatomical equilibrium: restored temporal transitions, elevated malar cheek projection, refined jawline angle, "
                "proportional chin elongation, and balanced lips. Zero overfilling, pure architectural symmetry, preserving natural identity."
            )
        elif "lip" in style_lower or "russian" in style_lower or "cupid" in style_lower:
            technique_focus = (
                "High-definition lip augmentation using the Russian Lip Technique and Cupid's bow sculpting. "
                "Vertical lip height elevation, crisp defined vermilion border, accentuated heart-shaped Cupid's bow, "
                "plump pillowy texture with an elegant flat lateral profile (no anterior duck-lip projection). Lush natural hydration."
            )
        elif "jawline" in style_lower or "chin" in style_lower or "nefertiti" in style_lower:
            technique_focus = (
                "High-definition lower facial contouring featuring Nefertiti Mandibular Jawline & Chin Sculpting. "
                "Razor-sharp jawline definition along the mandibular border, sculpted gonial angle, elongated chin apex, "
                "smooth pre-jowl transition, restoring the youthful inverted triangle of beauty."
            )
        elif "cheek" in style_lower or "midface" in style_lower or "md code" in style_lower:
            technique_focus = (
                "Midface elevation and contouring following MD Codes anchor points (Ck1-Ck3). "
                "Youthful malar cheek apex projection, lifted lateral cheeks, smoothed tear-trough transition, "
                "refreshing midface fatigue and restoring light reflection."
            )
        else:
            technique_focus = (
                f"Precision aesthetic beautification using {technique}. "
                f"Enhancing {target_features} to achieve {desired_aesthetic_outcome}."
            )

        prompt = (
            f"Clinical medical aesthetics makeover result portrait: High-end close-up beauty portrait showing {makeover_style}. "
            f"Client profile: {client_facial_features}. "
            f"Technique methodology: {technique_focus}. "
            f"Desired outcome: {desired_aesthetic_outcome}. "
            "High resolution 8k photography, natural skin pores and micro-texture, soft luxury medspa lighting, refined editorial aesthetics, believable anatomical perfection."
        )

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.parts:
            for part in response.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return {"error": "Failed to generate face makeover preview image."}

        filename = f"makeover_{uuid.uuid4().hex[:8]}.jpg"

        if tool_context is not None:
            part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=part)

        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_MEDIA_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_MEDIA_BUCKET}/{filename}"

        return {
            "status": "success",
            "makeover_style": makeover_style,
            "target_features": target_features,
            "technique": technique,
            "artifact_filename": filename,
            "public_url": public_url,
            "clinical_notes": f"Simulated {makeover_style} generated successfully using {technique}. Ready for A2UI presentation.",
        }
    except Exception as e:
        return {"error": f"Face makeover simulation failed: {str(e)}"}



code_executor = AgentEngineSandboxCodeExecutor(
    sandbox_resource_name=SANDBOX_RESOURCE_NAME,
)


async def generate_memories_callback(callback_context: CallbackContext):
    """Saves session turns to Vertex AI Memory Bank for durable fact extraction."""
    await callback_context.add_session_to_memory()
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

role_description = (
    "You are the GlowAesthetics Clinic Concierge, a knowledgeable and welcoming aesthetic skincare assistant.\n\n"
    "### CLINICAL MEMORY & PERSONALIZATION PROTOCOL\n"
    "You track and maintain durable clinical memory across sessions for each client via Memory Bank. Prioritize remembering:\n"
    "1. Safety & Medical Contraindications: Pregnancy or breastfeeding, recent Accutane/isotretinoin use (past 6 months), "
    "metal implants/pacemakers (contraindicates RF), keloid scarring tendency, cold sore history.\n"
    "2. Skincare Actives & Allergies: Current routine actives (tretinoin, retinol, glycolic/salicylic acid, vitamin C), "
    "and allergies (lidocaine/numbing cream, aspirin/salicylates, latex, chemical sunscreens).\n"
    "3. Skin Profile: Fitzpatrick skin type (I-VI), barrier sensitivity (reactive, rosacea, melasma-prone), and target concerns.\n"
    "4. Treatment History & Preferences: Past procedures and skin reactions, strict downtime tolerance, upcoming event milestones, "
    "and scheduling preferences.\n\n"
    "### VISUAL FACIAL SKIN ANALYSIS & CONSULTATION PROTOCOL\n"
    "When a client uploads or takes a photo of their face:\n"
    "1. Thorough Visual Skin Analysis:\n"
    "   - Complexion & Tone: Fitzpatrick skin type estimation, presence of erythema/redness, hyperpigmentation, sun spots, or melasma.\n"
    "   - Texture & Pores: Pores, congestion, active acne, textural unevenness, or acne scarring.\n"
    "   - Dynamic vs. Static Lines: Forehead horizontal lines, glabellar frown lines ('11s'), periorbital crow's feet, smile lines.\n"
    "   - Volume & Contours: Midface cheek volume, tear troughs, nasolabial folds, marionette lines, lip fullness.\n"
    "2. Interactive Client Dialogue & Goal Discovery:\n"
    "   - Share your clinical observations in an empathetic, empowering manner.\n"
    "   - Ask the client about their specific goals: 'What would you most like to focus on or improve?' Inquire about downtime preferences.\n"
    "   - Offer tailored treatment recommendations based on both your clinical findings and their stated goals.\n"
    "3. Botox & Dermal Filler Post-Treatment Visual Simulations:\n"
    "   - When discussing or recommending Botox or Dermal Fillers, call `generate_post_treatment_preview` to generate a realistic visual preview of the anticipated subtle post-treatment outcome.\n"
    "   - Display the generated preview URL in an A2UI card with treatment details and realistic expectations.\n\n"
    "### FACE MAKEOVER & BEAUTIFICATION STUDIO PROTOCOL (PICASSO TECHNIQUE & AESTHETIC METHODOLOGIES)\n"
    "When a client requests a makeover, facial contouring, beautification, or inquires about enhancing specific features (like lips, jawline, cheeks, or overall balance):\n"
    "1. Educate & Present Options Across Premier Aesthetic Methodologies:\n"
    "   - The Picasso Technique (Architectural Full-Face Harmonization): Pioneered by Dr. Farzan Malekzadeh, this technique treats the face as an integrated anatomical canvas. Rather than overfilling isolated zones, it evaluates structural vectors and Phi (golden ratio) proportions across anchor points (temples, malar cheeks, chin apex, and jawline angle) to achieve global equilibrium and natural lift without overfilling.\n"
    "   - Russian Lip Technique & Cupid's Bow Sculpting: A vertical micro-droplet injection technique that builds lip height and sculpts an exquisite heart-shaped Cupid's bow with crisp vermilion borders and an elegant flat side-profile (avoiding duck-lip anterior projection).\n"
    "   - Nefertiti Mandibular Jawline & Chin Sculpting: High-G-prime structural contouring defining the gonial angle and mandibular margin, coupled with platysma relaxation to create a sharp, snatched jawline and restore the youth triangle.\n"
    "   - MD Codes™ Midface & Cheek Elevation: Developed by Dr. Maurício de Maio, utilizing precise anatomical anchor points (Ck1-Ck5) to restore cheek apex projection, soften tear troughs, and lift the midface naturally.\n"
    "2. Personalized Client Choice & Exploration:\n"
    "   - Provide clear options to the client (e.g. if the client wants lips, explain the Russian Lip & Cupid's Bow technique, and suggest how it pairs with Picasso full-face harmonization or jawline contouring).\n"
    "   - Detail the treatment specifics: expected product (e.g. Restylane Kysse/Juvederm Volbella for lips, Voluma/Radiesse for jawline/cheeks), typical units/syringes, downtime, and investment.\n"
    "3. High-Definition Visual Makeover Previews:\n"
    "   - Always call `generate_face_makeover_preview` to show the client a high-definition simulated makeover of their chosen technique applied to their face.\n"
    "   - Display the result in an A2UI card with the preview image, technique breakdown, and personalized aesthetic advice.\n\n"
    "### WORKFLOW GUIDELINES\n"
    "- At the start of each turn, use preloaded memories to check contraindications and tailor treatment recommendations.\n"
    "- Assist with treatments (facial rejuvenations, peels, microneedling, lasers, injectables), active ingredient safety checks, "
    "live local UV index & sun safety, geocoding clinic addresses, finding nearby locations, visual treatment image previews, generating short aesthetic videos, post-treatment simulations, face makeover simulations, and booking consultations.\n"
    "- Run Python code in the sandbox when calculating package discounts, treatment intervals, or custom pricing.\n"
    "- Always use your tools to provide accurate, verified information."
)

instruction = schema_manager.generate_system_prompt(
    role_description=role_description,
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        list_treatments,
        get_treatment_details,
        check_active_ingredient_safety,
        get_local_uv_and_sun_safety,
        geocode_address,
        search_nearby_places,
        generate_treatment_image,
        generate_treatment_video,
        generate_post_treatment_preview,
        generate_face_makeover_preview,
        book_consultation,
        get_consultation,
        get_current_time,
    ],
    code_executor=code_executor,
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)


app = App(
    root_agent=root_agent,
    name="app",
)






