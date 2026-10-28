"""Sample data shared by the test suites: the transcript template and a small lint-clean deck."""

TRANSCRIPT = """# {pid}
- File: {file}
- Source guess: {guess}
- Orientation: upright
- Summary: {summary}
- Topics: {topics}
- Legibility: good

## Transcription
{body}

## Figures
{figs}

## Equations
none

## Key facts
- {fact}

## Flags
{flags}
"""
GOOD_HEADER = TRANSCRIPT.split("\n## Transcription")[0].format(
    pid="p001", file="a.jpg", guess="notebook", summary="notes", topics="cells"
)

NOTES_CARDS = [
    {
        "key": "nt_cell",
        "type": "basic",
        "source": "notes",
        "topic": "cells",
        "origin": "source",
        "pages": ["p001"],
        "front": "What are all living things made of?",
        "back": "Cells",
        "extra": "From your class notes.",
    },
    {
        "key": "nt_vacuole",
        "type": "cloze",
        "source": "notes",
        "topic": "cells",
        "origin": "source",
        "pages": ["p001"],
        "text": "{{c1::Vacuole}}: stores water; in plant cells one large central one supports the cell.",
    },
    *[
        {
            "key": f"nt_box_{n}",
            "type": "diagram",
            "source": "notes",
            "topic": "microscopes",
            "origin": "source",
            "pages": ["p002"],
            "prompt": f"<b>Labeled box</b><br>What goes in box <b>#{n}</b>?",
            "masked": "p002_box_masked.jpg",
            "answer": f"#{n} = {label}",
            "answer_image": "p002_box.jpg",
        }
        for n, label in ((1, "LABEL-A"), (2, "LABEL-B"))
    ],
]
PACKET_CARDS = [
    {
        "key": "pk_model",
        "type": "basic",
        "source": "packet",
        "topic": "cells",
        "origin": "model_answer",
        "pages": ["p003"],
        "front": "Why are controls used?",
        "back": "To compare against.",
    },
    {
        "key": "pk_eq",
        "type": "cloze",
        "source": "packet",
        "topic": "cells",
        "origin": "correction",
        "pages": ["p004"],
        "correction": "the packet swapped the products.",
        "text": "Photosynthesis: {{c1::{{chem:6CO2}}}} + 6H<sub>2</sub>O → {{c2::{{chem:C6H12O6}}}} + 6O<sub>2</sub>",
    },
    {
        "key": "pk_organelle",
        "type": "basic",
        "source": "packet",
        "topic": "vocab",
        "origin": "source",
        "pages": ["p005"],
        "front": "Define: <b>Organelle</b>",
        "back": "A specialized part of a cell with a specific function.",
    },
]
CATEGORIES = {
    "deck_root": "Test Deck",
    "audience": "7th grade",
    "sources": [
        {"id": "notes", "label": "Class notes", "subdeck": "1 Class Notes", "description": "notebook", "order": 1},
        {"id": "packet", "label": "Review packet", "subdeck": "2 Review Packet", "description": "guide", "order": 2},
    ],
    "topics": [
        {"slug": "cells", "label": "Cells", "order": 1},
        {"slug": "microscopes", "label": "Microscopes", "order": 2},
        {"slug": "vocab", "label": "Vocabulary", "order": 3},
    ],
    "page_sources": {"p001": "notes", "p002": "notes", "p003": "packet", "p004": "packet", "p005": "packet"},
    "page_topics": {
        "p001": ["cells"],
        "p002": ["microscopes"],
        "p003": ["cells"],
        "p004": ["cells"],
        "p005": ["vocab"],
    },
}
