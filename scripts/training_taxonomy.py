"""Spend categories for notices coded only to UNSPSC segment 86, *Education and Training Services*.

The AusTender codeset has no families under segment 86 (only two commodity codes), so agencies
can't code training any finer than "education and training". This taxonomy is written for
the questions a category manager would ask of that spend: is it staff development the agency
could buy through a shared arrangement, operational training tied to equipment, a program
delivered to the public, or not training at all?

One source of truth: the labelling guide, the keyword baseline and the Claude prompt all read
these definitions, and the categories are listed in the order they are decided (first match wins).
"""
from __future__ import annotations

# (key, short name, definition). Order = decision order.
CATEGORIES: list[tuple[str, str, str]] = [
    ("public_program", "Program delivered to the public",
     "An education, employment, scholarship or placement program that the agency funds for "
     "citizens, students, job seekers or overseas partners (for example the Skills for Education "
     "and Employment program, scholarships, clinical placement programs, aid-funded education "
     "programs, teacher resources). Not training for the agency's own staff."),
    ("not_training", "Not education or training",
     "The notice is for something other than training staff or delivering a program: catering, "
     "printing, quality assurance, care services, recruitment, general consulting, venues, books "
     "and subscriptions, or school fees."),
    ("military_operational", "Military and operational training",
     "Training for defence or operational roles: training systems and simulators, training on "
     "specific aircraft, vessels, vehicles or weapons, flying training, military courses, or "
     "a supplier whose business is defence training or simulation."),
    ("leadership_coaching", "Leadership, management and coaching",
     "Leadership or management development, executive or SES programs, coaching, mentoring, "
     "team development."),
    ("language", "Language training",
     "Learning a language, including interpreting and translation courses."),
    ("digital_it", "IT, data and digital skills",
     "Software, IT, cyber security, data, analytics, GIS or other digital-tool training."),
    ("safety_compliance", "Safety, first aid and compliance",
     "Work health and safety, first aid, mental health first aid, fire, water or laser safety, "
     "security awareness, fraud, ethics, legal or regulatory compliance training."),
    ("professional_technical", "Other professional and technical skills",
     "A named topic not covered above: finance, procurement, project management, writing, "
     "policy, trades, vocational or technical skills, clinical skills, and similar."),
    ("elearning", "E-learning content and platforms",
     "Online course libraries, virtual or e-learning content, learning management systems."),
    ("events_memberships", "Conferences, memberships and networks",
     "Conference attendance, annual memberships, learning networks or executive forums."),
    ("tertiary", "University or TAFE, topic not stated",
     "The supplier is a university, TAFE or other tertiary institution and the notice doesn't "
     "say what the training is about."),
    ("unspecified", "Can't tell from the notice",
     "A generic description (such as 'Training services') and nothing in the supplier's name "
     "says what the training is."),
]

KEYS = [k for k, _, _ in CATEGORIES]
NAMES = {k: name for k, name, _ in CATEGORIES}
DEFINITIONS = {k: d for k, _, d in CATEGORIES}

# Groups for the business read-out.
GROUPS = {
    "public_program": "Program delivery, not staff training",
    "not_training": "Not training (miscoded)",
    "military_operational": "Military and operational",
    "leadership_coaching": "Staff development, topic known",
    "language": "Staff development, topic known",
    "digital_it": "Staff development, topic known",
    "safety_compliance": "Staff development, topic known",
    "professional_technical": "Staff development, topic known",
    "elearning": "Staff development, topic known",
    "events_memberships": "Staff development, topic known",
    "tertiary": "Topic unknown",
    "unspecified": "Topic unknown",
}

# Evidence a label rests on (recorded in the check set).
BASIS = {
    "description": "the description says it",
    "supplier_name": "the supplier's name says it (e.g. 'Learn 2 Fly')",
    "outside_knowledge": "general knowledge of what a well-known supplier or program is",
    "none": "nothing says it (unspecified)",
}

assert len(set(KEYS)) == len(KEYS)
assert set(GROUPS) == set(KEYS)
