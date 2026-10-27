# My agent: GlowAesthetics Clinic Concierge
One-liner: A conversational agent that helps clients analyze skin concerns, discover cosmetic treatments, and plan consultations with a catalog of aesthetic treatments and skincare regimens.

Tool coverage:
- Memory: Remembers client skin profile (skin type: oily/dry/sensitive, Fitzpatrick type), primary concerns (hyperpigmentation, fine lines, acne scarring), treatment history, allergies, and aesthetic goals.
- Tools: Look up treatment details and downtime (`get_treatment_info`), check specialist availability (`check_practitioner_schedule`), book a consultation (`book_consultation`), and retrieve post-procedure aftercare instructions (`get_aftercare_guide`).
- Catalog/UI: Catalog of aesthetic services (HydraFacial, Microneedling, Chemical Peels, Laser Resurfacing, Dermal Fillers) rendered as rich A2UI cards displaying duration, downtime, price, and target concerns.
- Image gen: Generates visual personalized aftercare protocol cards and illustrative skincare regimen previews using `gemini-3.1-flash-lite-image`.
- Sandbox: Calculates treatment plan timelines (e.g. spacing 3 sessions across 12 weeks) and estimates total investment packages.

Recommended for every project: memory, storage, tools, image generation, A2UI
Agent-specific / stretch (pick what fits): Code sandbox for treatment scheduling & package pricing calculations, Cloud Trace for observability.
