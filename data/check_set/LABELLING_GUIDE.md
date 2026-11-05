# Labelling guide: training notices (Part 4 check set)

Each notice in `training_labels.csv` gets one **label**, the **basis** it rests on and an optional
**note**. The labeller sees what any user of the data sees: the description, the supplier's name, the
agency and the value. Nothing else was looked up.

The check set was labelled in full **before** the keyword rules in `scripts/categorise.py` were
written, so the rules couldn't be tuned to these rows.

## Labels (decide in this order; the first that fits wins)

| Label | Use when |
|---|---|
| `public_program` | An education, employment, scholarship or placement program that the agency funds for citizens, students, job seekers or overseas partners. Not training for the agency's own staff. |
| `not_training` | The notice is for something other than training staff or delivering a program: catering, printing, quality assurance, care services, recruitment, general consulting, venues, books and subscriptions, or school fees. |
| `military_operational` | Training for defence or operational roles: training systems and simulators, training on specific aircraft, vessels, vehicles or weapons, flying training, military courses, or a supplier whose business is defence training or simulation. |
| `leadership_coaching` | Leadership or management development, executive or SES programs, coaching, mentoring, team development. |
| `language` | Learning a language, including interpreting and translation courses. |
| `digital_it` | Software, IT, cyber security, data, analytics, GIS or other digital-tool training. |
| `safety_compliance` | Work health and safety, first aid, mental health first aid, fire, water or laser safety, security awareness, fraud, ethics, legal or regulatory compliance. |
| `professional_technical` | A named topic not covered above: finance, procurement, project management, writing, policy, trades, vocational or technical skills, clinical skills. |
| `elearning` | Online course libraries, virtual or e-learning content, learning management systems. |
| `events_memberships` | Conference attendance, annual memberships, learning networks, executive forums. |
| `tertiary` | The supplier is a university, TAFE or other tertiary institution and the notice doesn't say what the training is about. |
| `unspecified` | A generic description and nothing in the supplier's name says what the training is. |

The definitions are kept in `scripts/training_taxonomy.py`, which the keyword rules and the Claude
prompt also read.

## Basis

| Basis | Meaning |
|---|---|
| `description` | The description says it. |
| `supplier_name` | The supplier's name says it (e.g. "Learn 2 Fly", "Life Saving Victoria"). |
| `outside_knowledge` | General knowledge of what a well-known supplier or program is (e.g. a defence simulation company, or eSafety's *Be Connected* program). Used only when the supplier has one clear line of business; otherwise the label is `unspecified` or `tertiary`. |
| `none` | Nothing says it (`unspecified`). |

## Hard cases, decided once

- **Defence + generic description + a university or TAFE** → `tertiary`, not `military_operational`:
  the agency alone doesn't say what the course is.
- **Defence + generic description + an unknown supplier** → `unspecified`. Being a Defence notice isn't
  enough for `military_operational`.
- **"Learning and development" with no topic** from a consulting firm → `unspecified`.
- **Memberships of learning networks** (e.g. "Executive learning group membership") → `events_memberships`,
  even if the network is about leadership.
- **Coaching** → `leadership_coaching`, whatever the supplier.
- **Program names** that clearly serve the public (scholarships, pre-employment projects, industry
  initiatives that train people outside government) → `public_program`, even if the supplier is a
  university or TAFE.
- **Interpreting or translating services** (not courses) → `not_training`.
- **Workshop or group facilitation** with no topic → `unspecified`: it may be team development or
  plain consulting.
- **School fees** (e.g. a grammar school paid by Defence) → `not_training`: education, but an
  employee benefit, not staff training.
- **Venue hire and event management** → `not_training`; paying to *attend* a conference →
  `events_memberships`.
- **Training for people outside government** (industry, overseas partners, rangers funded through a
  program) → `public_program`.
- One annotator labelled every row, so the set is a careful reference, not perfect truth. Rows that
  took a judgement call say so in `note`.
