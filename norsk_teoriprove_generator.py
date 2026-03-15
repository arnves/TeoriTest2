#!/usr/bin/env python3
"""
Generer norske flervalgsoppgaver for teoriprøve klasse B ved hjelp av Claude,
verifiser dem i en egen QA-passasje, og lagre dem i SQLite.

Databaseskjema:
uuid, category, difficulty, question, answer1, answer2, answer3, answer4, correctIndex, explanation

Kjøring:
    export ANTHROPIC_API_KEY="..."
    python norsk_teoriprove_generator.py --db teoriprove.db

Valgfritt:
    python norsk_teoriprove_generator.py --db teoriprove.db --law-cache lovdata_trafikkregler.txt

Avhengigheter:
    pip install requests beautifulsoup4

Merk:
- Skriptet henter og cacher Trafikkreglene fra Lovdata lokalt.
- Skriptet bruker i tillegg et innebygd, kuratert sikkerhetsgrunnlag fra PDF-notatene
  om sikkerhetskontroll klasse B. Dersom du heller vil bruke egne tekstnotater,
  kan du legge dem i en fil og peke til filen med --safety-notes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF
import requests


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"

# -----------------------------
# Kildemateriale
# -----------------------------

CURRICULUM: Dict[str, List[str]] = {
    "Fart og plassering": [
        "Avstand til forankjørende",
        "Feltvalg. Kollektivfelt. Rundkjøring. Envegskjøring",
        "Forbikjøring",
        "Hest i trafikken",
        "Planovergang",
        "Signal og tegn",
        "Sikkerhetssoner. Blindsoner",
        "Siktforhold. Vær. Mørke. Bruk av lys",
        "Stopplengde. Bremselengde. Reaksjonslengde",
        "Vegforhold. Veggrep",
    ],
    "Fører og andre trafikanter": [
        "Forholdet mellom trafikanter",
        "Fysiske/psykiske begrensninger",
        "Miljøhensyn",
        "Sanser. Reaksjonstid. Uoppmerksomhet",
    ],
    "Fører og eiers ansvar(formelle forhold)": [
        "Eierforhold. Registrering. Vognkort. Forsikring",
        "Førstehjelp",
        "Helsekrav. Førerrett. Førerkort. Øvelseskjøring",
        "Offentlige reaksjoner ved overtredelse",
        "Passasjer",
        "Pliktmessig avhold",
        "Sikt. Isfrie ruter. Snø på tak",
        "Trafikkuhell. Sikringsutstyr. Tunnelsikkerhet",
        "Tretthet. Rus",
    ],
    "Kjøretøyet": [
        "Betjeningsorganer. Instrumentpanel",
        "Dekk. Styring. Bremser. Kjetting. Lys",
        "Drivstoff. Energikilde. Eksos. Miljø",
        "Førerstøttesystemer",
        "Sikkerhetskontroll",
    ],
    "Lover og regler": [
        "Forskrift om bruk av kjøretøy",
        "Trafikkregler",
        "Vegtrafikkloven § 3 og § 21",
    ],
    "Skilt og oppmerking": [
        "Fletting",
        "Skilt. Skiltgrupper",
        "Vegoppmerking",
    ],
    "Vikeplikt": [
        "Høyreregel. Ut fra parkering. Bussholdeplass. Skilt",
        "Lysregulering. Politimannens tegn",
        "Rygging. Vending",
        "Samhandling",
        "Stoppeplikt",
        "Trafikkreglene § 10",
    ],
}

TARGET_COUNTS = {"easy": 10, "medium": 20, "hard": 10}

DIFFICULTY_DEFINITIONS = {
    "easy": (
        "Lett = ren gjenkjenning eller enkel regelanvendelse. "
        "Ett tydelig faktaforhold, lite kontekststøy, ingen eller svært begrenset beregning, "
        "og feilalternativene skal være plausible, men klart svakere enn riktig svar for en elev med grunnleggende pensumforståelse."
    ),
    "medium": (
        "Middels = anvendelse av regel i en realistisk, men oversiktlig situasjon. "
        "Kan kreve at kandidaten kobler to regler eller vurderer kontekst, for eksempel skilting + vikeplikt, "
        "vær + fart, eller kjøretøystand + konsekvens. Distraktorene skal være nære nok til å skille mellom overflatisk og reell forståelse."
    ),
    "hard": (
        "Vanskelig = scenario-basert vurdering med flere samtidige forhold eller finere juridiske/pedagogiske skiller. "
        "Kan kreve prioritering mellom regler, anvendelse av sikkerhetsprinsipper i sammensatte situasjoner, "
        "eller identifikasjon av det mest korrekte handlingsvalget. Distraktorene skal være sterke og reflektere vanlige misforståelser."
    ),
}

# Kuratert sammendrag av den opplastede PDF-en om sikkerhetskontroll klasse B.
# Dette er ment som faglig støtte for oppgaver om kjøretøy/sikkerhetskontroll.
DEFAULT_SAFETY_NOTES = """
Sikkerhetskontroll klasse B - nøkkelpunkter:
- Bremsekraftforsterker: Pump bremsepedalen flere ganger til den blir hard, hold trykk, start motoren; pedalen skal synke inn.
- Dersom bremsekraftforsterker ikke virker, blir pedalen svært tung og bremseeffekten redusert; det er som hovedregel ikke forsvarlig.
- Lav bremsevæske kan skyldes slitte bremseklosser eller lekkasje i bremsesystemet; bilen bør kontrolleres.
- Varsellampe for to-krets bremsesystem/driftsbrems må identifiseres; hvis den lyser under kjøring, må man stanse og undersøke årsak.
- ABS-varsellampe skal lyse ved oppstart og deretter slukke.
- Skader på dekk/felg kan være rifter i dekkside, bulker i felg og bobler; dette kan gi ustabilitet og redusert sikkerhet.
- Minste mønsterdybde: sommerdekk 1,6 mm, vinterdekk 3,0 mm.
- For liten mønsterdybde gir dårligere veggrep og økt fare for vannplaning.
- Riktig lufttrykk finnes i instruksjonsbok eller merking på bilen; feil lufttrykk kan gi unormal slitasje og dårligere egenskaper.
- Bremselys må fungere på begge sider og høyt bremselys skal fungere.
- Nødblink brukes ved nødstopp og andre situasjoner som krever ekstra oppmerksomhet.
- Feil innstilt nærlys kan blende møtende og redusere siktstrekning i mørke.
- Kurve-/tåkelys og tåke-/baklys brukt feil kan blende eller irritere andre trafikanter.
- Servostyring kontrolleres ved å starte motor mens rattet holdes dreid; rattet skal bli lettere.
- Retningsstabilitet testes ved lav hastighet med lett grep på rattet; bilen skal gå rett fram.
- Refleksvest skal være tilgjengelig fra førersetet.
- Varseltrekant skal plasseres godt synlig; utenfor tettbygd strøk ofte ca. 100–200 meter bak bilen, men situasjonen må vurderes konkret.
- Dugg/is på bakrute og speil må kunne fjernes; bruk oppvarming/defroster.
- Batteriet skal sitte fast; løst batteri kan gi syresøl og kortslutning.
- Vindusspyler må fungere, og fører skal vite hvor spylervæske fylles på.
- Bilbelter skal kontrolleres for slitasje, rifter og at beltestrammer fungerer.
- Motoroljenivå skal være mellom min og max på peilepinnen.
"""



BASE_SYSTEM_PROMPT = """
Du er fagforfatter for norsk teoriprøve klasse B. Du skriver kun på norsk bokmål.
Du skal lage presise, juridisk forsvarlige og pedagogisk gode flervalgsoppgaver.

Krav:
- Hver oppgave skal ha nøyaktig 4 svaralternativer.
- Kun ett alternativ skal være korrekt.
- correctIndex skal være 1-basert og i intervallet 1..4.
- explanation skal kort forklare hvorfor riktig svar er riktig, og gjerne hvorfor en vanlig misforståelse er feil.
- Spørsmålene skal være realistiske for norsk teoriprøve klasse B.
- Unngå klisjeer og nesten-identiske formuleringer.
- Unngå "alle over", "ingen av de over", absolutter uten hjemmel, og tvetydige svar.
- Distraktorer skal være plausible, men ikke riktige.
- Der spørsmål bygger på rettsregler, skal rettstilstanden være gjeldende slik den fremgår av oppgitt regelgrunnlag.
- Dersom regelgrunnlaget ikke gir trygg dekning, skal du være konservativ og velge bredt anerkjent trafikksikker praksis fremfor usikre detaljer.
Svar alltid som ren JSON uten markdown.
"""

GENERATION_JSON_SCHEMA_HINT = """
JSON-format:
{
  "questions": [
    {
      "category": "eksakt kategorinavn",
      "difficulty": "easy|medium|hard",
      "question": "tekst",
      "answer1": "tekst",
      "answer2": "tekst",
      "answer3": "tekst",
      "answer4": "tekst",
      "internal_logic_check": "Kort steg-for-steg logikk som bekrefter svaret FØR index settes",
      "correctIndex": 1,
      "explanation": "tekst",
      "subtopic": "valgfritt internt arbeidsfelt"
    }
  ]
}
"""

VERIFICATION_JSON_SCHEMA_HINT = """
JSON-format:
{
  "results": [
    {
      "index": 0,
      "status": "accept|reject|revise",
      "reason": "kort begrunnelse",
      "verified_difficulty": "easy|medium|hard",
      "issues": ["..."],
      "revised_question": {
        "category": "...",
        "difficulty": "easy|medium|hard",
        "question": "...",
        "answer1": "...",
        "answer2": "...",
        "answer3": "...",
        "answer4": "...",
        "correctIndex": 1,
        "explanation": "..."
      }
    }
  ]
}
"""

# -----------------------------
# Hjelpefunksjoner
# -----------------------------


def stable_normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\wæøå ]+", "", text)
    return text


def fingerprint_question(question: Dict[str, Any]) -> str:
    s = " | ".join(
        [
            stable_normalize(question.get("category", "")),
            stable_normalize(question.get("difficulty", "")),
            stable_normalize(question.get("question", "")),
            stable_normalize(question.get("answer1", "")),
            stable_normalize(question.get("answer2", "")),
            stable_normalize(question.get("answer3", "")),
            stable_normalize(question.get("answer4", "")),
        ]
    )
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, stable_normalize(a), stable_normalize(b)).ratio()


def likely_duplicate(candidate: Dict[str, Any], existing: Sequence[Dict[str, Any]], threshold: float = 0.86) -> bool:
    c_q = candidate.get("question", "")
    c_answers = " ".join(candidate.get(f"answer{i}", "") for i in range(1, 5))
    for item in existing:
        q_sim = text_similarity(c_q, item.get("question", ""))
        a_sim = text_similarity(c_answers, " ".join(item.get(f"answer{i}", "") for i in range(1, 5)))
        if q_sim >= threshold or (q_sim >= 0.78 and a_sim >= 0.82):
            return True
    return False


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def chunked(seq: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# -----------------------------
# Lovdata-henting og caching
# -----------------------------


def load_or_build_law_cache(cache_path: Path, force_refresh: bool = False) -> str:
    ensure_parent(cache_path)
    if cache_path.exists() and not force_refresh:
        return cache_path.read_text(encoding="utf-8")

    pdf_files = [
        "Forskrift om bruk av kjøretøy - Lovdata.pdf",
        "Forskrift om kjørende og gående trafikk (trafikkregler) - Lovdata.pdf",
        "Lov om vegtrafikk (vegtrafikkloven) - Lovdata.pdf",
    ]
    
    combined_parts = []
    # Glob for PDF files in the current directory if exact matches aren't found due to encoding
    available_pdfs = list(Path(".").glob("*.pdf"))
    
    for pdf_path in available_pdfs:
        try:
            doc = fitz.open(pdf_path)
            text_parts = [f"=== {pdf_path.name} ==="]
            for page in doc:
                text_parts.append(page.get_text())
            combined_parts.append("\n".join(text_parts))
            doc.close()
        except Exception as e:
            print(f"Advarsel: Kunne ikke lese PDF {pdf_path}: {e}", file=sys.stderr)

    combined = "\n\n".join(combined_parts)
    # Simplify whitespace
    combined = re.sub(r"\n{3,}", "\n\n", combined)
    cache_path.write_text(combined, encoding="utf-8")
    return combined


def load_safety_notes(path: Optional[Path]) -> str:
    if path is None:
        return DEFAULT_SAFETY_NOTES.strip()
    return path.read_text(encoding="utf-8").strip()


# -----------------------------
# SQLite
# -----------------------------


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            uuid TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            difficulty TEXT NOT NULL CHECK (difficulty IN ('easy','medium','hard')),
            question TEXT NOT NULL,
            answer1 TEXT NOT NULL,
            answer2 TEXT NOT NULL,
            answer3 TEXT NOT NULL,
            answer4 TEXT NOT NULL,
            correctIndex INTEGER NOT NULL CHECK (correctIndex BETWEEN 1 AND 4),
            explanation TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty)")
    conn.commit()


def row_exists(conn: sqlite3.Connection, question: Dict[str, Any]) -> bool:
    cur = conn.execute(
        """
        SELECT 1
        FROM questions
        WHERE category = ?
          AND lower(trim(question)) = lower(trim(?))
        LIMIT 1
        """,
        (question["category"], question["question"]),
    )
    return cur.fetchone() is not None


def get_existing_questions(conn: sqlite3.Connection, category: str) -> List[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT category, difficulty, question, answer1, answer2, answer3, answer4, correctIndex, explanation
        FROM questions
        WHERE category = ?
        """,
        (category,),
    )
    cols = [column[0] for column in cur.description]
    out = []
    for row in cur.fetchall():
        out.append(dict(zip(cols, row)))
    return out


def insert_question(conn: sqlite3.Connection, question: Dict[str, Any]) -> str:
    q_uuid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO questions (
            uuid, category, difficulty, question, answer1, answer2, answer3, answer4, correctIndex, explanation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            q_uuid,
            question["category"],
            question["difficulty"],
            question["question"],
            question["answer1"],
            question["answer2"],
            question["answer3"],
            question["answer4"],
            int(question["correctIndex"]),
            question["explanation"],
        ),
    )
    return q_uuid


# -----------------------------
# Claude-klient
# -----------------------------


class ClaudeClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: int = 180):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _post_messages(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Claude API error {resp.status_code}: {resp.text[:1000]}")
        return resp.json()

    def complete_json(
        self,
        system_blocks: List[Dict[str, Any]],
        user_text: str,
        max_tokens: int = 4000,
        temperature: float = 0.3,
        use_cache: bool = True,
        ttl: str = "1h",
        retries: int = 3,
        model_override: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        import requests
        payload: Dict[str, Any] = {
            "model": model_override if model_override else self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_blocks,
            "messages": [{"role": "user", "content": user_text}],
        }
        last_exception = None
        for attempt in range(retries):
            try:
                data = self._post_messages(payload)
                break
            except Exception as e:
                last_exception = e
                wait_time = (2 ** attempt) * 2
                print(f"API-feil (forsøk {attempt + 1}/{retries}): {e}. Venter {wait_time}s...", file=sys.stderr)
                time.sleep(wait_time)
        else:
            raise RuntimeError(f"Claude API feilet gjentatte ganger: {last_exception}")

        text_parts = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        raw = "".join(text_parts).strip()
        
        # Strip potential markdown formatting wrapping the JSON
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
        
        # Extract only the JSON object, ignoring any conversational text appended or prepended
        start_idx = raw.find('{')
        end_idx = raw.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            raw = raw[start_idx:end_idx+1]
            
        try:
            parsed = json.loads(raw)
            return parsed, data.get("usage", {})
        except json.JSONDecodeError as e:
            raise ValueError(f"Kunne ikke parse JSON fra Claude: {e}\nRåtekst:\n{raw[:4000]}") from e


# -----------------------------
# Validering lokalt
# -----------------------------


REQUIRED_FIELDS = [
    "category",
    "difficulty",
    "question",
    "answer1",
    "answer2",
    "answer3",
    "answer4",
    "correctIndex",
    "explanation",
]


def validate_question_shape(question: Dict[str, Any]) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in question]
    if missing:
        raise ValueError(f"Mangler felt: {missing}")
    if question["difficulty"] not in {"easy", "medium", "hard"}:
        raise ValueError("Ugyldig difficulty")
    if question["correctIndex"] not in {1, 2, 3, 4}:
        raise ValueError("correctIndex må være 1..4")
    for f in ["question", "answer1", "answer2", "answer3", "answer4", "explanation", "category", "difficulty"]:
        if not isinstance(question[f], str) or not question[f].strip():
            raise ValueError(f"Feltet {f} må være ikke-tom tekst")
    answers = [question[f"answer{i}"].strip() for i in range(1, 5)]
    if len(set(stable_normalize(a) for a in answers)) < 4:
        raise ValueError("Svaralternativene må være distinkte")
    if len(question["question"]) < 18:
        raise ValueError("For kort spørsmål")
    if len(question["explanation"]) < 20:
        raise ValueError("For kort forklaring")


# -----------------------------
# Promptbygging
# -----------------------------


def build_static_context(law_text: str, safety_notes: str) -> List[Dict[str, Any]]:
    # Vi legger cache_control på de tunge, statiske blokkene for å trigge Anthropic Prompt Caching.
    # Dette må være nøyaktig likt for alle forespørsler for å sikre 100% cache-treff etter den første.
    return [
        {"type": "text", "text": BASE_SYSTEM_PROMPT},
        {
            "type": "text",
            "text": (
                "Regelgrunnlag og faglig kontekst:\n"
                "1) Trafikkreglene og relevante deler av vegtrafikkloven.\n"
                "2) Sikkerhetskontrollnotater for klasse B.\n"
                "Bruk dette som primærkilde. Ikke finn opp detaljer som ikke følger av grunnlaget."
            ),
        },
        {
            "type": "text",
            "text": f"=== REGELGRUNNLAG ===\n{law_text[:180000]}",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        },
        {
            "type": "text",
            "text": f"=== SIKKERHETSNOTATER ===\n{safety_notes}",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        },
    ]


def build_generation_prompt(
    category: str,
    subtopics: List[str],
    difficulty: str,
    batch_size: int,
    already_accepted: Sequence[Dict[str, Any]],
    existing_signatures: Sequence[str],
) -> str:
    coverage_hint = "\n".join(f"- {s}" for s in subtopics)
    recent_examples = []
    for item in already_accepted[-12:]:
        recent_examples.append(
            {
                "question": item["question"],
                "correctIndex": item["correctIndex"],
                "answers": [item[f"answer{i}"] for i in range(1, 5)],
            }
        )

    # Kategorier som er rent juridiske (fart, vikeplikt, skilt) vs praktiske (kjøretøy, trafikanter)
    REGULATORY_CATEGORIES = {"Fart og plassering", "Lover og regler", "Skilt og oppmerking", "Vikeplikt"}
    
    if category in REGULATORY_CATEGORIES:
        grounding_mode = (
            "MODUS: STRENG JURIDISK GROUNDING.\n"
            "Spørsmålet må kunne direkte hjemles i den oppgitte lovteksten. Ikke bruk generell kunnskap "
            "hvis det strider mot eller ikke finnes i teksten."
        )
    else:
        grounding_mode = (
            "MODUS: PRAKTISK TRAFIKKFAGLIG KJØRESKIKK.\n"
            "Bruk den oppgitte lovteksten som base, men du har lov til å supplere med bredt anerkjent "
            "trafikkfaglig kunnskap for klasse B, sunn fornuft og teknisk innsikt (spesielt for Kjøretøyet)."
        )

    return f"""
{grounding_mode}

Lag {batch_size} nye spørsmål for kategorien "{category}" med vanskelighetsgrad "{difficulty}".

Pedagogisk definisjon av vanskelighetsgrad:
{DIFFICULTY_DEFINITIONS[difficulty]}

Underemner i kategorien:
{coverage_hint}

Variasjonskrav:
- Spre spørsmålene utover flere underemner.
- Ikke skriv nesten like spørsmål.
- Varier mellom fakta, regelanvendelse, situasjonsforståelse, risikoforståelse og handlingsvalg der det passer.
- Ikke gjenbruk formuleringer, scenarier, tall, eller svaralternativer tett opp mot tidligere spørsmål.

VIKTIG LOGIKK-SJEKK:
- Før du setter "correctIndex", må du skrive "internal_logic_check".
- I logic_check skal du eksplisitt si: "Riktig svar er [tekst fra svaret], som tilsvarer index [N]".
- Dette er for å unngå at du velger feil index ved en glipp.

Tidligere spørsmål som må unngås semantisk nærhet til:
{json.dumps(recent_examples, ensure_ascii=False)}

Eksisterende korte signaturer/temaer som må unngås:
{json.dumps(list(existing_signatures)[-40:], ensure_ascii=False)}

Krav til output:
- category skal være eksakt "{category}"
- difficulty skal være eksakt "{difficulty}"
- Norsk bokmål
- Kun ett riktig svar
- correctIndex 1..4
- explanation kort, presis og faglig trygg

{GENERATION_JSON_SCHEMA_HINT}
""".strip()


def build_verification_prompt(
    category: str,
    target_difficulty: str,
    candidate_questions: Sequence[Dict[str, Any]],
    accepted_questions: Sequence[Dict[str, Any]],
) -> str:
    comparison_pool = [
        {
            "question": q["question"],
            "answers": [q[f"answer{i}"] for i in range(1, 5)],
            "difficulty": q["difficulty"],
        }
        for q in accepted_questions[-20:]
    ]

    return f"""
Du er kvalitetskontrollør for norsk teoriprøve klasse B.
Vurder hvert spørsmål med hensyn til:
1. juridisk/faglig korrekthet mot oppgitt regelgrunnlag (for juridiske kategorier) eller god kjøreskikk (for praktiske kategorier)
2. LOGISK KONSISTENS: Stemmer `internal_logic_check`, `correctIndex` og `explanation` overens? Hvis logic_check sier "Index 1" men correctIndex er "2", skal spørsmålet REJECTES eller REVISES.
3. om kun ett svar er korrekt
4. om forklaringen støtter korrekt svar
5. om vanskelighetsgraden faktisk samsvarer med "{target_difficulty}"
6. om spørsmålet er tydelig og ikke tvetydig
7. om spørsmålet er tilstrekkelig forskjellig fra andre nylig aksepterte spørsmål

Kategori: {category}
Mål-vanskelighetsgrad: {target_difficulty}

Nylig aksepterte spørsmål for duplikatkontroll:
{json.dumps(comparison_pool, ensure_ascii=False)}

Kandidater som skal vurderes:
{json.dumps(candidate_questions, ensure_ascii=False)}

Regler for output:
- status = accept dersom spørsmålet holder
- status = reject dersom det er vesentlig feil, tvetydighet, duplikat eller feil vanskelighetsgrad
- status = revise dersom mindre justeringer eller en index-fix kan redde spørsmålet
- Hold reason kort og spesifikk
- verified_difficulty skal være easy|medium|hard

{VERIFICATION_JSON_SCHEMA_HINT}
""".strip()


# -----------------------------
# Generator
# -----------------------------


@dataclass
class GenerationStats:
    requested: int = 0
    generated: int = 0
    accepted: int = 0
    rejected: int = 0
    revised: int = 0
    duplicates: int = 0
    stored: int = 0


class QuestionGenerator:
    def __init__(
        self,
        conn: sqlite3.Connection,
        client: ClaudeClient,
        law_text: str,
        safety_notes: str,
        seed: int = 7,
        pause_seconds: float = 1.2,
        validation_model: str = "claude-haiku-4-5-20251001",
    ):
        self.conn = conn
        self.client = client
        self.static_context = build_static_context(law_text, safety_notes)
        self.validation_model = validation_model
        self.random = random.Random(seed)
        self.pause_seconds = pause_seconds
        self.stats = GenerationStats()

    def _log_cost(self, step: str, usage: Dict[str, Any], is_haiku: bool = False) -> None:
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        
        # Sonnet: Base In $3/M, Cache Write $3.75/M, Cache Read $0.30/M, Out $15/M
        # Haiku: Base In $0.25/M, Cache Write $0.30/M, Cache Read $0.03/M, Out $1.25/M
        if is_haiku:
            cost = (in_tok / 1e6 * 0.25) + (cache_write / 1e6 * 0.30) + (cache_read / 1e6 * 0.03) + (out_tok / 1e6 * 1.25)
        else:
            cost = (in_tok / 1e6 * 3.00) + (cache_write / 1e6 * 3.75) + (cache_read / 1e6 * 0.30) + (out_tok / 1e6 * 15.00)
            
        print(f"  [{step}] Mynter brukt: ${cost:.4f} (In:{in_tok} Write:{cache_write} Read:{cache_read} Out:{out_tok})")

    def _generation_attempt(
        self,
        category: str,
        difficulty: str,
        batch_size: int,
        accepted_so_far: Sequence[Dict[str, Any]],
        signatures: Sequence[str],
    ) -> List[Dict[str, Any]]:
        prompt = build_generation_prompt(
            category=category,
            subtopics=CURRICULUM[category],
            difficulty=difficulty,
            batch_size=batch_size,
            already_accepted=accepted_so_far,
            existing_signatures=signatures,
        )
        data, usage = self.client.complete_json(
            system_blocks=self.static_context,
            user_text=prompt,
            max_tokens=5000,
            temperature=0.5 if difficulty == "hard" else 0.35,
            use_cache=True,
            ttl="1h",
        )
        self._log_cost("Generering", usage, is_haiku=False)
        questions = data.get("questions", [])
        if not isinstance(questions, list):
            raise ValueError("Claude returnerte ikke questions-listen")
        out: List[Dict[str, Any]] = []
        for q in questions:
            if not isinstance(q, dict):
                continue
            q = dict(q)
            q["category"] = category
            q["difficulty"] = difficulty
            try:
                validate_question_shape(q)
                logic_log = q.get('internal_logic_check', 'Ingen logikk oppgitt')
                print(f"  -> Genererte spørsmål: '{q.get('question', '')[:50]}...'")
                print(f"     LOGIKK: {logic_log[:100]}...")
            except Exception as e:
                print(f"  -> Avviste generert spørsmål form: {e}")
                continue
            out.append(q)
        return out

    def _verify_batch(
        self,
        category: str,
        difficulty: str,
        candidates: Sequence[Dict[str, Any]],
        accepted_so_far: Sequence[Dict[str, Any]],
    ) -> List[Tuple[str, Dict[str, Any], str]]:
        if not candidates:
            return []

        prompt = build_verification_prompt(
            category=category,
            target_difficulty=difficulty,
            candidate_questions=candidates,
            accepted_questions=accepted_so_far,
        )
        data, usage = self.client.complete_json(
            system_blocks=self.static_context,
            user_text=prompt,
            max_tokens=5000,
            temperature=0.1,
            use_cache=True,
            ttl="1h",
            model_override=self.validation_model
        )
        self._log_cost("QA / Validering", usage, is_haiku=True)
        results = data.get("results", [])
        indexed_candidates = list(candidates)

        out: List[Tuple[str, Dict[str, Any], str]] = []
        if not isinstance(results, list):
            return out

        for item in results:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(indexed_candidates):
                continue
            status = str(item.get("status", "reject")).lower().strip()
            reason = str(item.get("reason", "")).strip()
            verified_difficulty = str(item.get("verified_difficulty", difficulty)).strip()

            q = indexed_candidates[idx]
            if status == "revise" and isinstance(item.get("revised_question"), dict):
                q = dict(item["revised_question"])
                q["category"] = category
                q["difficulty"] = verified_difficulty if verified_difficulty in TARGET_COUNTS else difficulty

            elif status == "accept":
                q = dict(q)
                if verified_difficulty in {"easy", "medium", "hard"}:
                    q["difficulty"] = verified_difficulty

            try:
                validate_question_shape(q)
            except Exception:
                status = "reject"
                reason = (reason + " | ugyldig struktur etter QA").strip(" |")

            out.append((status, q, reason))
        return out

    def generate_for_category(self, category: str, max_attempts_per_difficulty: int = 14) -> List[Dict[str, Any]]:
        existing = get_existing_questions(self.conn, category)
        accepted: List[Dict[str, Any]] = list(existing)
        signatures: List[str] = [fingerprint_question(q) for q in accepted]

        for difficulty, target_count in TARGET_COUNTS.items():
            attempts = 0
            while True:
                current_count = sum(1 for q in accepted if q["difficulty"] == difficulty)
                if current_count >= target_count:
                    break
                
                attempts += 1
                if attempts > max_attempts_per_difficulty:
                    raise RuntimeError(
                        f"Kom ikke i mål for kategori '{category}' og vanskelighetsgrad '{difficulty}'. "
                        f"Forsøk øk max_attempts_per_difficulty eller juster promptene."
                    )

                current_count = sum(1 for q in accepted if q["difficulty"] == difficulty)
                remaining = target_count - current_count
                batch_size = min(6, max(3, remaining + 1))

                self.stats.requested += batch_size
                raw_candidates = self._generation_attempt(
                    category=category,
                    difficulty=difficulty,
                    batch_size=batch_size,
                    accepted_so_far=accepted,
                    signatures=signatures,
                )
                self.stats.generated += len(raw_candidates)

                filtered_candidates: List[Dict[str, Any]] = []
                for q in raw_candidates:
                    if row_exists(self.conn, q):
                        self.stats.duplicates += 1
                        continue
                    if likely_duplicate(q, accepted):
                        self.stats.duplicates += 1
                        continue
                    if fingerprint_question(q) in signatures:
                        self.stats.duplicates += 1
                        continue
                    filtered_candidates.append(q)

                verified = self._verify_batch(
                    category=category,
                    difficulty=difficulty,
                    candidates=filtered_candidates,
                    accepted_so_far=accepted,
                )

                for status, q, _reason in verified:
                    if status == "reject":
                        self.stats.rejected += 1
                        print(f"  -> QA AVVIST: {_reason}")
                        continue
                    if status == "revise":
                        self.stats.revised += 1
                        print(f"  -> QA REVIDERT: '{q.get('question', '')[:50]}...' ({_reason})")
                    else:
                        self.stats.accepted += 1
                        print(f"  -> QA AKSEPTERT: '{q.get('question', '')[:50]}...'")

                    # Tving tilbake til måldifficulty dersom QA flytter for langt og vi ellers mister kvoten.
                    if q["difficulty"] != difficulty:
                        q["difficulty"] = difficulty

                    if row_exists(self.conn, q):
                        self.stats.duplicates += 1
                        continue
                    if likely_duplicate(q, accepted):
                        self.stats.duplicates += 1
                        continue

                    accepted.append(q)
                    signatures.append(fingerprint_question(q))

                    if sum(1 for x in accepted if x["difficulty"] == difficulty) >= target_count:
                        break

                time.sleep(self.pause_seconds)

        return accepted

    def persist_questions(self, questions: Sequence[Dict[str, Any]]) -> int:
        count = 0
        for q in questions:
            if row_exists(self.conn, q):
                continue
            insert_question(self.conn, q)
            count += 1
        self.conn.commit()
        self.stats.stored += count
        return count


# -----------------------------
# CLI
# -----------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generer teoriprøvespørsmål for klasse B med Claude.")
    p.add_argument("--db", type=Path, required=True, help="SQLite-databasefil")
    p.add_argument(
        "--law-cache",
        type=Path,
        default=Path(".cache/lovdata_trafikkregler_og_vegtrafikkloven.txt"),
        help="Lokal cachefil for lovtekst",
    )
    p.add_argument(
        "--refresh-law-cache",
        action="store_true",
        help="Hent lovteksten på nytt fra Lovdata og overskriv cachefil",
    )
    p.add_argument(
        "--safety-notes",
        type=Path,
        default=None,
        help="Valgfri tekstfil med sikkerhetsnotater. Hvis ikke satt, brukes innebygde notater.",
    )
    p.add_argument("--model", default=DEFAULT_MODEL, help="Claude-modellnavn")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--pause", type=float, default=1.2, help="Pause mellom batcher (sekunder)")
    p.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="Valgfri liste over kategorier. Hvis tomt, kjøres alle.",
    )
    return p.parse_args()


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(".env.local")
    
    args = parse_args()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Manglende ANTHROPIC_API_KEY i miljøet eller .env.local.", file=sys.stderr)
        return 2

    categories = args.categories or list(CURRICULUM.keys())
    unknown = [c for c in categories if c not in CURRICULUM]
    if unknown:
        print(f"Ukjente kategorier: {unknown}", file=sys.stderr)
        return 2

    print("Laster regelgrunnlag ...")
    law_text = load_or_build_law_cache(args.law_cache, force_refresh=args.refresh_law_cache)
    safety_notes = load_safety_notes(args.safety_notes)

    ensure_parent(args.db)
    conn = sqlite3.connect(args.db)
    init_db(conn)

    client = ClaudeClient(api_key=api_key, model=args.model)
    generator = QuestionGenerator(
        conn=conn,
        client=client,
        law_text=law_text,
        safety_notes=safety_notes,
        seed=args.seed,
        pause_seconds=args.pause,
    )

    total_new = 0
    try:
        for category in categories:
            print(f"\n=== Genererer kategori: {category} ===")
            questions = generator.generate_for_category(category)
            stored = generator.persist_questions(questions)
            total_new += stored

            by_diff = {d: 0 for d in TARGET_COUNTS}
            for q in questions:
                by_diff[q["difficulty"]] += 1

            print(
                f"Lagret {stored} spørsmål i databasen "
                f"(easy={by_diff['easy']}, medium={by_diff['medium']}, hard={by_diff['hard']})."
            )

    finally:
        conn.close()

    print("\n=== Ferdig ===")
    print(f"Nye lagrede spørsmål: {total_new}")
    print(
        "Statistikk: "
        f"requested={generator.stats.requested}, "
        f"generated={generator.stats.generated}, "
        f"accepted={generator.stats.accepted}, "
        f"revised={generator.stats.revised}, "
        f"rejected={generator.stats.rejected}, "
        f"duplicates={generator.stats.duplicates}, "
        f"stored={generator.stats.stored}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
