#!/usr/bin/env python3
"""Seed Firestore with aesthetic clinic treatments and sample consultations."""

from google.cloud import firestore

# Hardcoded project ID as required
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-03-3746e4b526aa"

TREATMENTS = [
    {
        "id": "hydrafacial-deluxe",
        "name": "HydraFacial Deluxe",
        "category": "Hydration & Congestion",
        "target_concerns": ["clogged pores", "dehydration", "dullness", "uneven texture"],
        "duration_minutes": 60,
        "downtime": "No downtime, immediate radiant glow",
        "price_usd": 275,
        "description": "A 3-step medical grade facial that deep-cleanses, extracts, and infuses patented antioxidant serums.",
        "aftercare_summary": "Avoid heavy sweating or makeup for 6 hours. Keep skin hydrated with SPF 50.",
        "suitable_skin_types": ["all", "sensitive", "dry", "oily", "combination"],
    },
    {
        "id": "microneedling-rf",
        "name": "Radiofrequency Microneedling (Morpheus8)",
        "category": "Collagen & Texture",
        "target_concerns": ["acne scars", "fine lines", "skin laxity", "enlarged pores"],
        "duration_minutes": 75,
        "downtime": "24-48 hours mild redness and pinpoint flaking",
        "price_usd": 650,
        "description": "Combines collagen-inducing microneedling with deep radiofrequency heat to remodel subdermal tissue.",
        "aftercare_summary": "No makeup for 24 hours. Use gentle peptide serum and strict mineral SPF. Avoid direct sun.",
        "suitable_skin_types": ["Fitzpatrick I-VI", "normal", "oily", "mature"],
    },
    {
        "id": "vi-peel-precision",
        "name": "VI Peel Precision Plus",
        "category": "Chemical Exfoliation",
        "target_concerns": ["hyperpigmentation", "melasma", "sun damage", "post-inflammatory erythema"],
        "duration_minutes": 45,
        "downtime": "3-5 days of noticeable skin peeling",
        "price_usd": 350,
        "description": "A medium-depth medical peel specifically formulated to target stubborn pigment, UV damage, and dark spots.",
        "aftercare_summary": "Do not pick or pull peeling skin. Apply soothing post-peel protectant and broad-spectrum physical sunscreen daily.",
        "suitable_skin_types": ["hyperpigmented", "sun-damaged", "oily"],
    },
    {
        "id": "clear-brilliant-laser",
        "name": "Clear + Brilliant Gentle Laser",
        "category": "Laser Resurfacing",
        "target_concerns": ["early signs of aging", "pore size", "texture irregularity", "prejuvenation"],
        "duration_minutes": 45,
        "downtime": "12-24 hours sandpaper-like texture, mild flush",
        "price_usd": 425,
        "description": "Gentle fractional laser treatment known as the 'baby Fraxel' that renews skin from the inside out.",
        "aftercare_summary": "Moisturize frequently. Do not use retinoids or AHAs/BHAs for 5 days. Daily SPF 50 required.",
        "suitable_skin_types": ["all", "first-time laser patients"],
    },
    {
        "id": "dermal-filler-contour",
        "name": "Hyaluronic Acid Dermal Contouring",
        "category": "Injectables",
        "target_concerns": ["volume loss", "hollow cheeks", "lip definition", "nasolabial folds"],
        "duration_minutes": 60,
        "downtime": "24-72 hours possible mild swelling or bruising",
        "price_usd": 750,
        "description": "Targeted hyaluronic acid filler injection by a medical practitioner to restore structural volume and symmetry.",
        "aftercare_summary": "Avoid touching or applying pressure to treated areas. Avoid strenuous exercise, alcohol, and saunas for 24 hours.",
        "suitable_skin_types": ["all adult skin types"],
    },
]

def seed_data():
    print(f"Connecting to Firestore with project: {FIRESTORE_PROJECT_ID}...")
    db = firestore.Client(project=FIRESTORE_PROJECT_ID)
    
    # 1. Seed treatments
    treatments_ref = db.collection("treatments")
    for t in TREATMENTS:
        doc_id = t["id"]
        treatments_ref.document(doc_id).set(t)
        print(f"  ✓ Seeded treatment: {t['name']} ({doc_id})")
        
    # 2. Seed a sample consultation record
    sample_booking = {
        "booking_id": "BK-1001",
        "client_name": "Jordan Smith",
        "treatment_id": "hydrafacial-deluxe",
        "treatment_name": "HydraFacial Deluxe",
        "date": "2026-11-02",
        "time_slot": "10:30 AM",
        "practitioner": "Dr. Sarah Lin, MD",
        "status": "confirmed",
        "notes": "First-time visitor, prep for upcoming wedding.",
    }
    db.collection("consultations").document(sample_booking["booking_id"]).set(sample_booking)
    print(f"  ✓ Seeded sample consultation: {sample_booking['booking_id']}")
    
    print("\nFirestore database seeded successfully!")

if __name__ == "__main__":
    seed_data()
