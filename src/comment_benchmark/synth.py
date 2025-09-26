"""Dataset synthesis utilities for Comment Sense v2 benchmarking."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import logging
import os
import random
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import google.generativeai as genai

DEFAULT_MODEL_NAME = "models/gemini-2.5-flash"
SEED = 7
MAX_RETRIES = 4
SYSTEM_INSTRUCTION = (
    "Du lager datasettposter for interne sykehusnotater. Returner kun gyldig JSON som matcher schemaet. "
    "Ingen forklaringstekst. comment_text skal være kort (maks 2 linjer) og bruke apostrof i stedet for doble anførselstegn."
)
RETRY_SUFFIXES: List[str] = [
    "",
    "\n\nVIKTIG: Returner KUN gyldig JSON. Ingen ekstra ord. Bruk apostrof i comment_text og hold teksten kort.",
    "\n\nNB: JSON må være gyldig og kort. Husk at availability_periods enten er null eller liste i tråd med instruks.",
    "\n\nKRITISK: Svar nøyaktig med JSON-objektet etter schemaet. Hvis du er usikker, gjenta med kortere tekst.",
]

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STYLE_PATH = _PROJECT_ROOT / "sample.md"
_ENV_PATH = _PROJECT_ROOT / ".env"
_OUTPUT_PATH = _PROJECT_ROOT / "data" / "ground_truth.csv"
_CACHE_DIR = _PROJECT_ROOT / "data" / "gemini_cache"

_model_instance: Optional[genai.GenerativeModel] = None


@dataclass(frozen=True)
class LabelSpec:
    patient_prioritized: Optional[bool]
    patient_ready: Optional[bool]
    patient_short_notice: Optional[bool]
    availability_mode: str  # "list" or "null"
    scenario_hint: str
    style_hint: str = ""


_SCENARIO_HINTS: List[str] = [
    "Pas venter på utsvar fra kardiolog. Noter lab 05.03.25 og referer til gul lapp.",
    "Oppgi at MR knær booket uke 18 og pas ønsker å vente til etter konfirmasjon.",
    "Bruk litt slang, og nevn at pas trenger fysio 2 ganger før opr.",
    "Noter at pas tar kontakt selv når fastlegen har sendt epikrise.",
    "Fokuser på at det haster etter reinnleggelse 14.02.25.",
    "Nevn at planlegger ABC har ringt uten svar, bruk litt stavefeil.",
    "Ta med ferieperiode 15.07-04.08.25 og referer til stue 11.",
    "Oppgi behov for ny blodprøve innen 03.05.25, bruk forkortelser.",
    "Beskriv at pas ønsker op tidlig okt på grunn av jobbturnus.",
    "Bruk uke 42 som mulig kontroll, litt hakkete setning.",
    "Nevn at LIS kan ta opr om Anestesi sier ok, litt typos.",
    "Oppdater om at pas avlyste pga infeksjon, ny vurdering juni.",
    "Pas trenger mer tid for å avslutte medikasjon, nevne isotret.",
    "Ta med beskjed om å ringe på kort varsel hvis hull i plan.",
    "Referer til gul lapp datert 19.03.25 og anestesi ASA II.",
    "Nevn graviditet og at pas venter til jan 26, kortfattet.",
    "Fokuser på replanlegging etter sykemelding ut uke 35.",
    "Pas ønsker AA-lege, men ok med LIS som assistent, litt roddete.",
    "Bruk blanding av norsk/eng forkortelser, noter CT 28/04.",
    "Oppgi at pas må informere oss når han er ferdig med antibiotika 12.06.",
]

_STYLE_VARIATIONS: List[str] = [
    "Legg inn en kort dialektfrase (f.eks. 'ikkje', 'ska').",
    "Bruk litt telegraf-stil med mange punktum.",
    "Skriv i litt stresset planlegger-tone, men hold det kort.",
    "Tilføy et lite notat om at pas følger opp selv.",
    "Legg inn en forkortelse som 'kfr' eller 'prs'.",
    "Nevn et kort telefonnotat med tidspunkt.",
    "Bruk ett lite punktlistepreg med semikolon.",
    "Inkluder en liten stavefeil med bokstavbytte.",
    "Få inn en blanding av norsk/engelsk, f.eks. 'ok for call'.",
    "Nevn at planlegger noterte i gul lapp, men hold vag.",
    "Bruk referanse til 'stue' eller 'team' der det passer.",
    "Tilføy kort påminnelse om lab/rtg status.",
    "Bruk et lite utropstegn midt i notatet.",
    "Nevn at pas ønsker ringetid etter kl 15.",
    "Legg inn en kort TODO-kommentar i parentes.",
    "Oppgi en uke-notasjon (uke 34) selv om dato finnes.",
    "Bruk litt SMS-språk ('mld', 'plz').",
    "Nevn at anestesi må oppdatere ASA hvis relevant.",
    "Få inn en referanse til tidligere avlysning.",
    "Referer til LIS-navn (fiktivt) som må varsles.",
    "Nevn behov for tolketjeneste kort.",
    "Legg inn et kort 'ok av overlege XYZ'.",
    "Bruk 'kort varsl' eller lignende bevisst feil.",
    "Avslutt med kort call-to-action (ringer fredag).",
]

_BASE_SPECS: List[LabelSpec] = [
    LabelSpec(True, True, False, "list", _SCENARIO_HINTS[0]),
    LabelSpec(True, False, True, "list", _SCENARIO_HINTS[1]),
    LabelSpec(False, True, False, "null", _SCENARIO_HINTS[2]),
    LabelSpec(False, False, False, "null", _SCENARIO_HINTS[3]),
    LabelSpec(None, True, None, "list", _SCENARIO_HINTS[4]),
    LabelSpec(True, None, True, "list", _SCENARIO_HINTS[5]),
    LabelSpec(False, None, True, "null", _SCENARIO_HINTS[6]),
    LabelSpec(None, False, False, "list", _SCENARIO_HINTS[7]),
    LabelSpec(True, True, True, "list", _SCENARIO_HINTS[8]),
    LabelSpec(False, True, True, "null", _SCENARIO_HINTS[9]),
    LabelSpec(None, None, None, "null", _SCENARIO_HINTS[10]),
    LabelSpec(True, False, None, "list", _SCENARIO_HINTS[11]),
]


_AVAILABILITY_ITEM_SCHEMA = {
    'type': 'object',
    'properties': {
        'type': {'type': 'string'},
        'start_date': {'type': 'string'},
        'end_date': {'type': 'string'},
    },
    'required': ['type', 'start_date', 'end_date'],
}

_RESPONSE_SCHEMA = {
    'type': 'object',
    'properties': {
        'comment_text': {'type': 'string'},
        'patient_prioritized': {'type': 'boolean', 'nullable': True},
        'patient_ready': {'type': 'boolean', 'nullable': True},
        'patient_short_notice': {'type': 'boolean', 'nullable': True},
        'availability_periods': {
            'type': 'array',
            'nullable': True,
            'items': _AVAILABILITY_ITEM_SCHEMA,
        },
    },
    'required': [
        'comment_text',
        'patient_prioritized',
        'patient_ready',
        'patient_short_notice',
        'availability_periods',
    ],
}

def _project_root() -> Path:
    return _PROJECT_ROOT


def _load_style_seed() -> str:
    if not _STYLE_PATH.exists():
        logging.error("Style seed file %s not found", _STYLE_PATH)
        raise FileNotFoundError(_STYLE_PATH)
    return _STYLE_PATH.read_text(encoding="utf-8")


def _load_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if key:
        return key.strip()
    if not _ENV_PATH.exists():
        logging.error("Missing .env file at %s", _ENV_PATH)
        raise SystemExit(1)
    for raw_line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "GEMINI_API_KEY":
            key = value.strip().strip("'").strip('\"')
            os.environ["GEMINI_API_KEY"] = key
            return key
    logging.error("GEMINI_API_KEY not present in .env")
    raise SystemExit(1)


def _cache_key(prompt: str) -> str:
    digest = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    return digest


def _cache_path(key: str) -> Path:
    return _CACHE_DIR / f"{key}.json"


def _read_cache(key: str, expected_kind: Optional[str] = None) -> Optional[Any]:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        logging.warning('Ugyldig cachefil %s - ignorerer', path)
        return None
    except Exception as err:  # noqa: BLE001
        logging.warning('Kunne ikke lese cache %s: %s', path, err)
        return None
    kind = payload.get('kind')
    if expected_kind and kind not in {expected_kind}:
        logging.debug('Cache %s har feil type %s (forventet %s)', path, kind, expected_kind)
        return None
    if 'data' in payload:
        return payload['data']
    raw_text = payload.get('raw_text')
    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text
    return None


def _write_cache(key: str, *, prompt: str, kind: str, data: Any, raw_text: Optional[str] = None) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _cache_path(key)
        payload = {'prompt': prompt, 'kind': kind, 'data': data}
        if raw_text is not None:
            payload['raw_text'] = raw_text
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as err:  # noqa: BLE001
        logging.warning('Kunne ikke lagre cache %s: %s', key, err)


def _bool_instruction(value: Optional[bool], descriptor: str) -> str:
    if value is True:
        return f"Teksten må tydelig vise at pas er {descriptor}."
    if value is False:
        return f"Teksten må vise at pas IKKE er {descriptor}."
    return f"Ikke si noe direkte om hvorvidt pas er {descriptor}."


def _availability_instruction(mode: str) -> str:
    if mode == "list":
        return (
            "availability_periods skal være en liste med 1-2 objekter, hver med type, start_date og end_date."
            " Datoer i ISO (YYYY-MM-DD). Teksten må omtale samme perioder."
        )
    return "availability_periods skal være null og teksten må ikke gi eksplisitte datoperioder."


def _strip_code_fence(payload: str) -> str:
    text = payload.strip()
    if text.startswith("```") and "```" in text[3:]:
        parts = text.split("```")
        if len(parts) >= 3:
            return parts[1].strip()
    return text


def _parse_payload(raw_text: str) -> Dict[str, Any]:
    cleaned = _strip_code_fence(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as err:
        logging.error("Gemini response is not valid JSON: %s", err)
        digest = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()[:16]
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            fail_path = _CACHE_DIR / f'failed_{digest}.json'
            fail_path.write_text(cleaned, encoding='utf-8')
            logging.error('Rårespons lagret til %s for inspeksjon.', fail_path)
        except Exception as file_err:  # noqa: BLE001
            logging.warning('Kunne ikke lagre rårespons: %s', file_err)
        logging.debug("Raw payload: %s", raw_text)
        raise
    expected = {"comment_text", "patient_prioritized", "patient_ready", "patient_short_notice", "availability_periods"}
    missing = expected - data.keys()
    if missing:
        logging.error("Response missing keys: %s", ", ".join(sorted(missing)))
        raise KeyError(f"Missing keys: {missing}")
    return data


def _extract_response_text(response: Any) -> str:
    candidates = getattr(response, "candidates", None)
    if not candidates:
        logging.error('Gemini response contained no candidates: %s', response)
        raise RuntimeError('Gemini response contained no candidates')
    finish_reasons: List[str] = []
    for candidate in candidates:
        finish = getattr(candidate, 'finish_reason', None)
        finish_reasons.append(str(finish))
        content = getattr(candidate, 'content', None)
        parts = getattr(content, 'parts', None) if content else None
        if not parts:
            continue
        fragments: List[str] = []
        for part in parts:
            text = getattr(part, 'text', None)
            if text:
                fragments.append(text)
        if fragments:
            if finish and str(finish).upper() not in {'FINISH_REASON_STOP', 'STOP', '1'}:
                logging.debug('Non-stop finish reason: %s', finish)
            return ''.join(fragments).strip()
    logging.error('Gemini response missing text parts. Finish reasons: %s', finish_reasons)
    raise RuntimeError('Gemini response missing text parts')


def _ensure_types(record: Dict[str, Any], spec: LabelSpec) -> Dict[str, Any]:
    comment = str(record["comment_text"]).strip()
    comment = " ".join(comment.split())
    record["comment_text"] = comment

    for field in ("patient_prioritized", "patient_ready", "patient_short_notice"):
        value = record[field]
        if value not in (True, False, None):
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "yes"}:
                    record[field] = True
                elif lowered in {"false", "no"}:
                    record[field] = False
                elif lowered in {"", "null", "none"}:
                    record[field] = None
                else:
                    raise ValueError(f"Unexpected value for {field}: {value}")
            else:
                raise ValueError(f"Unexpected value for {field}: {value}")

    availability = record["availability_periods"]
    if spec.availability_mode == "list":
        if availability in (None, "null"):
            raise ValueError("Expected availability list, got null")
        if not isinstance(availability, list):
            raise ValueError("availability_periods must be a list")
        normalized_periods: List[Dict[str, str]] = []
        for item in availability:
            if not isinstance(item, dict):
                raise ValueError("Each availability period must be an object")
            period = {
                "type": str(item.get("type", "")).strip(),
                "start_date": str(item.get("start_date", "")).strip(),
                "end_date": str(item.get("end_date", "")).strip(),
            }
            if not all(period.values()):
                raise ValueError("Availability period fields cannot be empty")
            normalized_periods.append(period)
        record["availability_periods"] = normalized_periods
    else:
        if availability not in (None, "null"):
            if isinstance(availability, list) and len(availability) == 0:
                record["availability_periods"] = None
            else:
                raise ValueError("Expected availability null value")
        else:
            record["availability_periods"] = None

    return record


def _build_prompt(spec: LabelSpec, style_seed: str) -> str:
    instructions = [
        _bool_instruction(spec.patient_prioritized, "prioritert"),
        _bool_instruction(spec.patient_ready, "klar/ready for opr"),
        _bool_instruction(spec.patient_short_notice, "tilgjengelig på kort varsel"),
        _availability_instruction(spec.availability_mode),
    ]
    if spec.patient_short_notice is True:
        instructions.append("Nevn konkret at pas kan møte på kort varsel.")
    elif spec.patient_short_notice is False:
        instructions.append("Nevn nødvendig varslingstid eller at pas trenger lengre varsel.")

    guidelines = "\n- ".join([""] + instructions)

    availability_hint = (
        "Lag tydelige perioder med type som 'ferie', 'ledig', 'sykefravær' osv." if spec.availability_mode == "list" else "Hent inspirasjon fra stil uten å oppgi datoperiode direkte."
    )

    prompt = f"""
Du er planlegger ved norsk sykehus. Bruk stilen fra disse notatene:
---
{style_seed}
---
Generer ett realistisk kommentarfelt til interne planleggingssystemer. Bruk samme tone, forkortelser og blanding av språk. Tillat små skrivefeil, uke-nummer og datoer.

Scenario: {spec.scenario_hint}
{availability_hint}
{f'Stilvariasjon: {spec.style_hint}' if spec.style_hint else ''}

Krav:{guidelines}
- Teksten skal bli 1-3 korte linjer.
- Variere ordvalg, legg gjerne inn små avbrytelser (",", ";", "-").
- Unngå doble anførselstegn i teksten (bruk apostrof) eller escape dem med \".
- Verdiene i JSON må samsvare med teksten.

Returner ett JSON-objekt med nøkler "comment_text", "patient_prioritized", "patient_ready", "patient_short_notice", "availability_periods". Ingen ekstra felt, ingen Markdown, ingen forklaring.
"""
    return prompt.strip()


def _make_model() -> genai.GenerativeModel:
    key = _load_api_key()
    model_name = os.getenv("GEMINI_MODEL_NAME", DEFAULT_MODEL_NAME)
    logging.info("Bruker Gemini-modell %s", model_name)
    genai.configure(api_key=key)
    generation_config = genai.types.GenerationConfig(
        temperature=0.0,
        top_p=0.8,
        top_k=32,
        max_output_tokens=2048,
        candidate_count=1,
        response_mime_type="application/json",
        response_schema=_RESPONSE_SCHEMA,
    )
    return genai.GenerativeModel(
        model_name=model_name,
        generation_config=generation_config,
        system_instruction=SYSTEM_INSTRUCTION,
    )


def _get_model() -> genai.GenerativeModel:
    global _model_instance
    if _model_instance is None:
        _model_instance = _make_model()
    return _model_instance


def ping_gemini() -> str:
    """Send a simple hello request to Gemini and return the text response."""
    prompt = "Svar kun med ordet 'hello'."
    cache_key = _cache_key(prompt)
    cached_text = _read_cache(cache_key, expected_kind="ping")
    if isinstance(cached_text, str):
        logging.info('Gjenbruker cache for ping.')
        text = cached_text
    else:
        key = _load_api_key()
        genai.configure(api_key=key)
        model_name = os.getenv("GEMINI_MODEL_NAME", DEFAULT_MODEL_NAME)
        ping_config = genai.types.GenerationConfig(
            temperature=0.0,
            top_p=0.8,
            top_k=32,
            max_output_tokens=64,
            candidate_count=1,
        )
        ping_model = genai.GenerativeModel(model_name=model_name, generation_config=ping_config)
        logging.info("Tester forbindelse mot Gemini...")
        try:
            response = ping_model.generate_content(prompt, request_options={"timeout": 30})
        except Exception as err:  # noqa: BLE001
            logging.error("Gemini ping feilet: %s", err)
            raise
        text = _extract_response_text(response)
        _write_cache(cache_key, prompt=prompt, kind="ping", data=text)
    text = text.strip()
    if text.startswith('\"') and text.endswith('\"') and len(text) >= 2:
        text = text[1:-1]
    if not text:
        raise RuntimeError("Tomt svar fra Gemini under ping.")
    logging.info("Ping vellykket: %s", text)
    return text




def _expand_specs(n: int) -> List[LabelSpec]:
    if n <= 0:
        raise ValueError("n must be positive")
    specs: List[LabelSpec] = []
    scenario_pool = list(_SCENARIO_HINTS)
    random.shuffle(scenario_pool)
    hint_cycle = iter(scenario_pool)
    variation_pool = list(_STYLE_VARIATIONS)
    random.shuffle(variation_pool)
    variation_cycle = iter(variation_pool)
    while len(specs) < n:
        for base in _BASE_SPECS:
            if len(specs) >= n:
                break
            try:
                scenario = next(hint_cycle)
            except StopIteration:
                scenario_pool = list(_SCENARIO_HINTS)
                random.shuffle(scenario_pool)
                hint_cycle = iter(scenario_pool)
                scenario = next(hint_cycle)
            try:
                style_hint = next(variation_cycle)
            except StopIteration:
                variation_pool = list(_STYLE_VARIATIONS)
                random.shuffle(variation_pool)
                variation_cycle = iter(variation_pool)
                style_hint = next(variation_cycle)
            specs.append(LabelSpec(base.patient_prioritized, base.patient_ready, base.patient_short_notice, base.availability_mode, scenario, style_hint))
    random.shuffle(specs)
    return specs[:n]


def _format_bool_for_csv(value: Optional[bool]) -> str:
    if value is None:
        return "null"
    return "true" if value else "false"


def _write_csv(rows: List[Dict[str, Any]]) -> Path:
    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "comment_text",
        "patient_prioritized",
        "patient_ready",
        "patient_short_notice",
        "availability_periods",
    ]
    with _OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            csv_row = {
                "id": row["id"],
                "comment_text": row["comment_text"],
                "patient_prioritized": _format_bool_for_csv(row["patient_prioritized"]),
                "patient_ready": _format_bool_for_csv(row["patient_ready"]),
                "patient_short_notice": _format_bool_for_csv(row["patient_short_notice"]),
                "availability_periods": json.dumps(row["availability_periods"], ensure_ascii=False),
            }
            writer.writerow(csv_row)
    return _OUTPUT_PATH


def _synthesize_single(model: genai.GenerativeModel, spec: LabelSpec, style_seed: str, index: int) -> Dict[str, Any]:
    prompt = _build_prompt(spec, style_seed)
    cache_key = _cache_key(prompt)
    cached_entry = _read_cache(cache_key, expected_kind="dataset_record")
    normalized_record: Optional[Dict[str, Any]] = None
    raw_text: Optional[str] = None

    if isinstance(cached_entry, dict):
        logging.info("Gjenbruker cache for eksempel %s", index)
        normalized_record = cached_entry
    elif isinstance(cached_entry, str):
        logging.info("Validerer eksisterende cache for eksempel %s", index)
        try:
            parsed = _parse_payload(cached_entry)
            normalized_record = _ensure_types(parsed, spec)
            raw_text = cached_entry
        except Exception as err:  # noqa: BLE001
            logging.warning("Cache-innhold ugyldig for eksempel %s: %s. Genererer på nytt.", index, err)
            normalized_record = None

    if normalized_record is None:
        last_error: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            suffix = RETRY_SUFFIXES[min(attempt - 1, len(RETRY_SUFFIXES) - 1)]
            prompt_to_use = prompt + suffix if suffix else prompt
            logging.info("Genererer eksempel %s (forsøk %s/%s)", index, attempt, MAX_RETRIES)
            try:
                response = model.generate_content(prompt_to_use, request_options={"timeout": 600})
                raw_text = _extract_response_text(response)
                if not raw_text:
                    raise RuntimeError(f"Tom respons fra Gemini for eksempel {index}")
                parsed = _parse_payload(raw_text)
                normalized_record = _ensure_types(parsed, spec)
            except Exception as err:  # noqa: BLE001
                last_error = err
                logging.warning("Forsøk %s på eksempel %s feilet: %s", attempt, index, err)
                normalized_record = None
                raw_text = None
                if attempt == MAX_RETRIES:
                    logging.error("Oppga etter %s forsøk på eksempel %s.", MAX_RETRIES, index)
                    raise err
                continue
            else:
                cache_payload = copy.deepcopy(normalized_record)
                _write_cache(
                    cache_key,
                    prompt=prompt,
                    kind="dataset_record",
                    data=cache_payload,
                    raw_text=raw_text,
                )
                break

    normalized = copy.deepcopy(normalized_record)
    normalized["id"] = str(uuid.uuid4())
    return normalized


def generate_dataset(n: int = 100) -> Path:
    """Generate a dataset with n examples and write it to CSV."""
    random.seed(SEED)
    style_seed = _load_style_seed()
    specs = _expand_specs(n)
    model = _get_model()
    logging.info("Starter generering av %s eksempler", n)
    rows: List[Dict[str, Any]] = []
    for idx, spec in enumerate(specs, start=1):
        record = _synthesize_single(model, spec, style_seed, idx)
        rows.append(record)
    output_path = _write_csv(rows)
    logging.info("Skrev %s rader til %s", len(rows), output_path)
    return output_path


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Comment Sense v2 dataset synthesizer")
    parser.add_argument("--ping", action="store_true", help="Test Gemini connectivity")
    parser.add_argument("--generate", nargs="?", type=int, const=100, help="Generate dataset with optional row count")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = _parse_args(argv)
    executed = False
    if args.ping:
        ping_gemini()
        executed = True
    if args.generate is not None:
        generate_dataset(args.generate)
        executed = True
    if not executed:
        logging.info("Ingen kommando oppgitt. Bruk --ping og/eller --generate.")


if __name__ == "__main__":
    main()
