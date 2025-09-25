#!/usr/bin/env python3
"""Generate a synthetic benchmark dataset for the comment analysis model."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import csv

OUTPUT_PATH = Path("datasets/comment_benchmark_ground_truth.csv")
TARGET_COUNT = 100
random.seed(20240516)


@dataclass
class Example:
    comment_text: str
    patient_ready: Optional[bool]
    patient_short_notice: Optional[bool]
    patient_prioritized: Optional[bool]
    availability_notes: str
    priority_reason: str
    notes: str

    def as_row(self, idx: int) -> dict[str, str]:
        return {
            "example_id": f"ex_{idx:03d}",
            "comment_text": self.comment_text,
            "patient_ready": bool_to_str(self.patient_ready),
            "patient_short_notice": bool_to_str(self.patient_short_notice),
            "patient_prioritized": bool_to_str(self.patient_prioritized),
            "availability_notes": self.availability_notes,
            "priority_reason": self.priority_reason,
            "notes": self.notes,
        }


def bool_to_str(value: Optional[bool]) -> str:
    if value is None:
        return "null"
    return "true" if value else "false"


MANUAL_EXAMPLES: list[Example] = [
    Example(
        comment_text=(
            "KPOL 26.05.25 EKG/LAB ASA III. Avbestilte 23.09. Ønsker oppstart fra oktober på grunn av sykepenger, "
            "jfr. gul lapp KPOL 07.07.25 (planleggerens init)."
        ),
        patient_ready=False,
        patient_short_notice=False,
        patient_prioritized=False,
        availability_notes="Disponibel fra oktober 2025",
        priority_reason="",
        notes="Avventer økonomi, tydelig nei til kort varsel",
    ),
    Example(
        comment_text=(
            "AVVENT. Sendt gul lapp til ABC om videre forløp. DEF 14.09.25, KPOL 23.03.25. Ønsker operasjon i okt/nov 2025, "
            "rtg og lab bestilles, ASA 2, BMI 30."
        ),
        patient_ready=False,
        patient_short_notice=False,
        patient_prioritized=False,
        availability_notes="Planlagt for oktober/november 2025",
        priority_reason="",
        notes="Venter på videre avklaring fra ABC",
    ),
    Example(
        comment_text=(
            "Opl. meld 27.03.25, men er gravid og skal derfor ikke opereres før jan 2026. ABC 08.10.25. Må konfereres "
            "med DEF. 100. DEF + GHI."
        ),
        patient_ready=False,
        patient_short_notice=False,
        patient_prioritized=False,
        availability_notes="Tidligst januar 2026",
        priority_reason="",
        notes="Graviditet utsetter inngrep",
    ),
    Example(
        comment_text=(
            "KPOL 03.04.25. Operasjon med ABC som assistent jfr. DEF. Lab ikke tatt - behøver ikke jfr. DEF 10.04.25. "
            "Ilm. kort varsel, ASA 2, BMI 31."
        ),
        patient_ready=True,
        patient_short_notice=True,
        patient_prioritized=False,
        availability_notes="Kan tas inn ved kort varsel",
        priority_reason="",
        notes="Team avklart, ønsker rask innkalling",
    ),
    Example(
        comment_text=(
            "ØNH: Gifter seg i sept 2023. Må ringes 2 mnd før operasjon. Lunge-anestesitilsyn? ABC følger."
        ),
        patient_ready=None,
        patient_short_notice=False,
        patient_prioritized=False,
        availability_notes="Kontakt to måneder før ønsket dato",
        priority_reason="",
        notes="Trenger koordinering rundt bryllup",
    ),
    Example(
        comment_text=(
            "Kjeveoperasjon først, usikker på når hun får denne. Skal holde oss oppdatert jfr. 13.08.25. Pasienten ønsker "
            "oppringing for tilpassing av operasjon. Stue 11."
        ),
        patient_ready=False,
        patient_short_notice=None,
        patient_prioritized=False,
        availability_notes="Avventer kjeveoppr. dato",
        priority_reason="",
        notes="Mangler klarering fra annet inngrep",
    ),
    Example(
        comment_text=(
            "Stue 11. Kort varsel. Ferie 23.06. Ønsker sent september eller tidlig oktober 2025."
        ),
        patient_ready=True,
        patient_short_notice=True,
        patient_prioritized=False,
        availability_notes="Tilgjengelig etter ferie, helst slutten av september",
        priority_reason="",
        notes="Ferie begrenser vindu",
    ),
    Example(
        comment_text=(
            "Pasient tar kontakt når han er klar for operasjon. Behandles nå for leukemi 31.10.24 ABC, svar 31/10-24. Ferie "
            "05-25.06 og 10.09-15.10.24. Stue 11. Klar til operasjon jmf. anestesi."
        ),
        patient_ready=True,
        patient_short_notice=None,
        patient_prioritized=False,
        availability_notes="Tilgjengelig utenom ferieperioder",
        priority_reason="",
        notes="Medisinsk klarering dokumentert",
    ),
    Example(
        comment_text=(
            "Pasient gir beskjed når hun har sluttet med Isotretonin 30.04.25, evt. litt før. ABC HLOS pas. Ikke DEF. Kan "
            "opereres av LIS. Stue 11."
        ),
        patient_ready=False,
        patient_short_notice=None,
        patient_prioritized=False,
        availability_notes="Tidligst mai 2025",
        priority_reason="",
        notes="Avventer medikamentpause",
    ),
]


def build_generated_example(counter: int) -> Example:
    clinics = ["KPOL", "ØNH", "GYN", "ORTO", "HUD", "KAR", "NEVRO", "GAST", "URO"]
    supervisors = ["ABC", "DEF", "GHI", "JKL", "MNO", "PRS", "TUV", "WXY"]
    rooms = ["Stue 3", "Stue 5", "Stue 7", "Stue 9", "Stue 11", "Stue 14"]
    months = [
        "januar", "februar", "mars", "april", "mai", "juni",
        "juli", "august", "september", "oktober", "november", "desember"
    ]
    ready_templates = {
        True: [
            "Klar for operasjon. Preop er fullført.",
            "Klarert av anestesi og kirurg."
        ],
        False: [
            "Avventer ytterligere avklaringer før operasjon.",
            "Ikke klarert av anestesi ennå."
        ],
        None: [
            "Klareringsstatus ikke diskutert i siste møte.",
            "Status ikke vurdert, må tas opp på neste kontroll."
        ],
    }
    short_notice_templates = {
        True: [
            "Kan kalles inn på kort varsel.",
            "Tar gjerne ledig plass innen få dager."
        ],
        False: [
            "Ønsker varsel minst fire uker i forkant.",
            "Kan ikke ta kort varsel pga jobb og familie."],
        None: [
            "Kort varsel ikke diskutert.",
            "Ingen preferanse angitt for varsel."],
    }
    priority_templates = {
        True: [
            "PRIO-sett av ansvarlig kirurg.",
            "Skal prioriteres grunnet medisinsk forverring."
        ],
        False: [
            "Ingen ekstra prioritet oppgitt.",
            "Standard prioritet i køen."
        ],
    }
    availability_templates = [
        "Foretrekker operasjon i {month} {year}",
        "Tilgjengelig etter {month} {year}",
        "Kan settes opp mellom {month} og {next_month} {year}",
    ]
    note_templates = [
        "Oppfølging avtales med {supervisor}.",
        "Kontakt {supervisor} for preop spørsmål.",
        "{supervisor} informert om plan.",
    ]

    ready_state = random.choice([True, False, None, True, False])
    short_notice_state = random.choice([True, False, None, False, True])
    priority_state = random.choice([False, False, True, False])

    clinic = random.choice(clinics)
    supervisor = random.choice(supervisors)
    room = random.choice(rooms)
    month = random.choice(months)
    next_month = random.choice(months)
    year = random.choice(["2024", "2025", "2026"])

    availability_text = random.choice(availability_templates).format(
        month=month,
        next_month=next_month,
        year=year,
    )
    readiness_text = random.choice(ready_templates[ready_state])
    short_notice_text = random.choice(short_notice_templates[short_notice_state])
    priority_text = random.choice(priority_templates[priority_state])
    note_text = random.choice(note_templates).format(supervisor=supervisor)

    comment_parts = [
        f"{clinic} kontroll {counter % 28 + 1:02d}.{(counter * 3) % 12 + 1:02d}.{2024 + counter % 3}",
        room,
        readiness_text,
        short_notice_text,
        priority_text,
        availability_text + ".",
        note_text,
    ]
    comment_text = " ".join(p.strip() for p in comment_parts if p)

    availability_notes = availability_text
    priority_reason = "Medisinsk" if priority_state else ""
    notes = "Syntetisk generert eksempel"

    return Example(
        comment_text=comment_text,
        patient_ready=ready_state,
        patient_short_notice=short_notice_state,
        patient_prioritized=priority_state,
        availability_notes=availability_notes,
        priority_reason=priority_reason,
        notes=notes,
    )


def main() -> None:
    examples: list[Example] = list(MANUAL_EXAMPLES)

    counter = 1
    while len(examples) < TARGET_COUNT:
        example = build_generated_example(counter)
        examples.append(example)
        counter += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "example_id",
                "comment_text",
                "patient_ready",
                "patient_short_notice",
                "patient_prioritized",
                "availability_notes",
                "priority_reason",
                "notes",
            ],
        )
        writer.writeheader()
        for idx, example in enumerate(examples, start=1):
            writer.writerow(example.as_row(idx))

    print(f"Wrote {len(examples)} examples to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
