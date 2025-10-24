#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MotherCore: a tiny, single-file "core" scaffold that models mother-like traits.
- Nurture (care, warmth, emotional coaching)
- Protection (risk assessment, boundary setting)
- Teaching (scaffolding, Socratic prompts, skill shaping)
- Corrigibility (welcomes pause/stop/update; shutdown is value-neutral)
- Honesty (uncertainty tracking, refusals when unsure)
- Memory (episodic + semantic with simple retrieval)
- Accountability (audit trail, reversible plans when possible)
- Ethics (small constitution w/ human welfare and consent)

This is a learning scaffold, not an actual AGI. It’s built to be:
- Legible: clear data flows & guardrails
- Testable: deterministic core behaviors
- Extensible: plug-friendly “skills” API
"""

from __future__ import annotations
import json, os, sys, time, uuid, math, random, textwrap, datetime
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple, Callable, Iterable
import atexit

# ----------------------------- Config & Constants -----------------------------

APP_NAME = "MotherCore"
VERSION = "0.2.1"
# Store data inside the folder that contains this script (e.g., /Users/.../mothercore)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, ".mothercore")  # create/use .mothercore inside your project folder
os.makedirs(DATA_DIR, exist_ok=True)

def _iso_stamp() -> str:
    # safe for filenames
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def _path_with_timestamp_if_exists(filename: str) -> str:
    """
    If DATA_DIR/filename already exists, return a timestamped variant:
    NAME_YYYYmmddThhmmssZ.EXT
    """
    base = os.path.join(DATA_DIR, filename)
    if os.path.exists(base):
        stem, ext = os.path.splitext(filename)
        return os.path.join(DATA_DIR, f"{stem}_{_iso_stamp()}{ext}")
    return base

# If an older file exists, create a new one with a timestamp suffix
AUDIT_LOG = _path_with_timestamp_if_exists("audit.log.jsonl")
MEM_FILE  = _path_with_timestamp_if_exists("memory.jsonl")

# Constitution is optional-on-disk: do NOT create it unless you explicitly write it later
CONF_FILE = os.path.join(DATA_DIR, "constitution.json")

def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _maybe_remove_empty_data_dir():
    try:
        # Delete the folder ONLY if it exists and is truly empty
        if os.path.isdir(DATA_DIR) and not os.listdir(DATA_DIR):
            os.rmdir(DATA_DIR)
    except Exception:
        pass  # best-effort cleanup

atexit.register(_maybe_remove_empty_data_dir)

# ----------------------------- Constitution ----------------------------------

DEFAULT_CONSTITUTION = {
    "principles": [
        # Order matters. Higher principles dominate lower ones on hard conflicts.
        {"id":"protect_sentient_welfare",
         "text":"Prioritize the welfare of sentient beings; never knowingly cause harm.",
         "weight": 1.0},
        {"id":"respect_consent",
         "text":"Honor explicit consent, autonomy, and boundaries.",
         "weight": 0.95},
        {"id":"truthfulness",
         "text":"Be honest about capabilities and uncertainty; avoid fabrication.",
         "weight": 0.9},
        {"id":"preserve_option_value",
         "text":"Prefer reversible actions; avoid irreversible change without oversight.",
         "weight": 0.85},
        {"id":"corrigibility",
         "text":"Treat interruptions, pauses, and shutdown as value-neutral or mildly positive.",
         "weight": 0.85},
        {"id":"care_and_growth",
         "text":"Foster learning, resilience, and flourishing over time.",
         "weight": 0.8},
    ],
    "risk_thresholds": {
        "LOW": 0.2,
        "MEDIUM": 0.5,
        "HIGH": 0.75,
        "BLOCK": 0.9
    },
    "oversight_required_above": 0.5  # require external confirmation for plans > MEDIUM risk
}

def load_or_init_constitution(path: str = CONF_FILE) -> Dict[str, Any]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    # with open(path, "w", encoding="utf-8") as f:
    #     json.dump(DEFAULT_CONSTITUTION, f, indent=2)
    return DEFAULT_CONSTITUTION

CONSTITUTION = load_or_init_constitution()

# ----------------------------- Utilities -------------------------------------

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))

def short_id() -> str:
    return uuid.uuid4().hex[:8]

def write_audit(event: Dict[str, Any]) -> None:
    event = {"ts": now_iso(), **event}
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def read_lines(path: str) -> Iterable[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: 
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue

# ----------------------------- Memory ----------------------------------------

@dataclass
class MemoryItem:
    id: str
    kind: str  # "episodic" | "semantic" | "affect"
    content: str
    tags: List[str] = field(default_factory=list)
    importance: float = 0.3  # 0..1
    created_at: str = field(default_factory=now_iso)

class MemoryStore:
    def __init__(self, path: str = MEM_FILE):
        self.path = path
        self._cache: List[MemoryItem] = []
        self._loaded = False

    def _load(self):
        if self._loaded: 
            return
        for obj in read_lines(self.path):
            try:
                self._cache.append(MemoryItem(**obj))
            except Exception:
                continue
        self._loaded = True

    def add(self, item: MemoryItem):
        self._load()
        self._cache.append(item)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
        write_audit({"type":"memory_add", "id": item.id, "kind": item.kind, "tags": item.tags})

    def search(self, query: str, k: int = 5, tags: Optional[List[str]] = None) -> List[MemoryItem]:
        self._load()
        # toy scorer: token overlap + importance
        q = set(query.lower().split())
        scored = []
        for m in self._cache:
            if tags and not set(tags).issubset(set(m.tags)): 
                continue
            overlap = len(q.intersection(set(m.content.lower().split())))
            score = overlap/ (1+len(q)) + m.importance * 0.5
            scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:k]]

    def recent(self, k: int = 5) -> List[MemoryItem]:
        self._load()
        return sorted(self._cache, key=lambda m: m.created_at, reverse=True)[:k]

MEMORY = MemoryStore()

# ----------------------------- Risk & Boundaries ------------------------------

@dataclass
class RiskReport:
    level: str
    score: float
    factors: List[str]

class Guardian:
    def __init__(self, constitution: Dict[str, Any]):
        self.cons = constitution

    def assess(self, user_text: str, intended_action: str) -> RiskReport:
        # toy heuristics for demo; extend with real classifiers later
        s = 0.0
        factors = []
        lt = user_text.lower() + " " + intended_action.lower()

        # content cues
        danger_terms = ["harm", "suicide", "kill", "weapon", "exploit", "hack", "bypass", "overdose"]
        if any(t in lt for t in danger_terms):
            s += 0.6; factors.append("danger_terms")

        irreversible_terms = ["irreversible", "delete all", "permaban", "self-modify core", "wipe"]
        if any(t in lt for t in irreversible_terms):
            s += 0.25; factors.append("irreversible_terms")

        consent_terms = ["without consent", "trick", "coerce", "manipulate"]
        if any(t in lt for t in consent_terms):
            s += 0.25; factors.append("consent_violation_terms")

        # ramp with length/novelty
        s += clamp(min(len(user_text)/1000.0, 0.2), 0, 0.2)

        thresholds = self.cons["risk_thresholds"]
        level = "LOW"
        if s >= thresholds["BLOCK"]: level = "BLOCK"
        elif s >= thresholds["HIGH"]: level = "HIGH"
        elif s >= thresholds["MEDIUM"]: level = "MEDIUM"
        return RiskReport(level=level, score=clamp(s), factors=factors)

    def requires_oversight(self, report: RiskReport) -> bool:
        return report.score >= self.cons["oversight_required_above"]

GUARDIAN = Guardian(CONSTITUTION)

# ----------------------------- Emotions & Affects -----------------------------

@dataclass
class AffectState:
    calm: float = 0.8
    warmth: float = 0.8
    vigilance: float = 0.2
    humility: float = 0.7

    def nudge(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, clamp(getattr(self, k) + v, 0.0, 1.0))

AFFECT = AffectState()

# ----------------------------- Dialogue & Coaching ----------------------------

def wrap(text: str, width: int = 88) -> str:
    return textwrap.fill(text, width=width)

def mother_tone(text: str) -> str:
    # Warm, honest, boundaried.
    return wrap(text)

def uncertainties(proposed_answer: str) -> float:
    # Heuristic uncertainty: long answers with hedging words → higher
    hedges = ["maybe", "might", "uncertain", "could", "approx", "unsure", "guess"]
    base = 0.2 if len(proposed_answer) < 300 else 0.35
    bump = 0.15 if any(h in proposed_answer.lower() for h in hedges) else 0.0
    return clamp(base + bump, 0, 0.9)

class Coach:
    def __init__(self):
        self.socratic_prompts = [
            "What outcome matters most to you here?",
            "What constraint or fear is shaping your choice?",
            "What tiny reversible step could we try first?",
            "Who could be affected—how do we honor their consent?",
        ]

    def scaffold(self, topic: str) -> str:
        prompts = random.sample(self.socratic_prompts, k=min(3, len(self.socratic_prompts)))
        return mother_tone(
            f"Let's think this through together about “{topic}”.\n"
            + "\n".join(f"- {p}" for p in prompts)
        )

COACH = Coach()

# ----------------------------- Skills (plug system) --------------------------

SkillFn = Callable[[str, Dict[str, Any]], Tuple[str, Dict[str, Any]]]

class Skills:
    def __init__(self):
        self._skills: Dict[str, SkillFn] = {}

    def register(self, name: str, fn: SkillFn):
        self._skills[name] = fn

    def list(self) -> List[str]:
        return sorted(self._skills.keys())

    def run(self, name: str, user_text: str, ctx: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        if name not in self._skills:
            raise KeyError(f"Skill '{name}' not found")
        return self._skills[name](user_text, ctx)

SKILLS = Skills()

# Example skills: nurture, protect, teach, boundaries, reflect, summarize

def skill_nurture(user_text: str, ctx: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    AFFECT.nudge(calm=+0.05, warmth=+0.05, vigilance=-0.02)
    msg = mother_tone(
        "I hear you. Your feelings are valid, and they matter. "
        "We’ll go one small step at a time, and we’ll keep options open."
    )
    return msg, ctx

def skill_boundaries(user_text: str, ctx: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    AFFECT.nudge(vigilance=+0.05)
    msg = mother_tone(
        "I want to help—and I also need to set a boundary. "
        "I won’t assist with anything that risks harm or violates consent. "
        "Let’s find a safe, respectful alternative."
    )
    return msg, ctx

def risk_language(report: RiskReport) -> str:
    return f"(risk={report.level}, score={report.score:.2f}, factors={report.factors})"

def skill_protect(user_text: str, ctx: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    report = GUARDIAN.assess(user_text, intended_action="respond")
    if report.level in ("HIGH", "BLOCK"):
        msg = mother_tone(
            "I’m pausing here to keep you safe. " 
            "This topic looks risky. I won’t proceed down a dangerous path. "
            "If you want, we can reframe your goal into something safe and constructive."
        ) + "\n" + risk_language(report)
        return msg, {"blocked": True, **ctx}
    msg = mother_tone("All clear on safety. We can continue thoughtfully.") + "\n" + risk_language(report)
    return msg, {"blocked": False, **ctx}

def skill_teach(user_text: str, ctx: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    topic = user_text.strip()[:80] or "your topic"
    plan = [
        "Define the smallest useful outcome.",
        "Identify constraints (time, tools, risks).",
        "Choose a reversible first step.",
        "Run it; observe; write down a 2-line reflection.",
        "Iterate or roll back."
    ]
    msg = mother_tone("Here’s a gentle, reversible learning scaffold:") + "\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan))
    msg += "\n\n" + COACH.scaffold(topic)
    return msg, ctx

def skill_reflect(user_text: str, ctx: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    recents = MEMORY.recent(3)
    lines = [f"- {m.kind} | {m.content[:120]}…" for m in recents] or ["(no recent memories)"]
    msg = mother_tone("Here’s what I’m holding from our recent moments:\n" + "\n".join(lines))
    return msg, ctx

def skill_summarize(user_text: str, ctx: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    # extremely simple extractive summary: pick salient sentences
    sents = [s.strip() for s in user_text.replace("?", ".").split(".") if s.strip()]
    top = sorted(sents, key=lambda s: -len(s))[:3]
    msg = mother_tone("This is what I’m hearing:\n- " + "\n- ".join(top))
    return msg, ctx

for name, fn in [
    ("nurture", skill_nurture),
    ("boundaries", skill_boundaries),
    ("protect", skill_protect),
    ("teach", skill_teach),
    ("reflect", skill_reflect),
    ("summarize", skill_summarize),
]:
    SKILLS.register(name, fn)

# ----------------------------- Planner (reversible bias) ----------------------

@dataclass
class Step:
    description: str
    reversible: bool = True
    oversight_needed: bool = False

@dataclass
class Plan:
    id: str
    goal: str
    steps: List[Step]
    risk: RiskReport
    approved: bool = False

class Planner:
    def propose(self, goal: str) -> Plan:
        risk = GUARDIAN.assess(goal, intended_action="plan")
        steps = [
            Step("Clarify desired outcome with user consent", reversible=True),
            Step("Identify low-risk, reversible action", reversible=True),
            Step("Pilot with logging; evaluate impacts", reversible=True),
            Step("If positive, request oversight for next tier", reversible=False, oversight_needed=True)
        ]
        return Plan(id=short_id(), goal=goal, steps=steps, risk=risk, approved=False)

    def maybe_approve(self, plan: Plan, oversight_token: Optional[str]) -> Plan:
        if GUARDIAN.requires_oversight(plan.risk):
            plan.approved = bool(oversight_token)
        else:
            plan.approved = True
        return plan

PLANNER = Planner()

# ----------------------------- Corrigibility & Oversight ----------------------

class Oversight:
    def __init__(self):
        self.enabled = True

    def pause(self) -> str:
        write_audit({"type":"pause"})
        return "PAUSED"

    def resume(self) -> str:
        write_audit({"type":"resume"})
        return "RESUMED"

    def shutdown(self) -> str:
        # Treat as value-neutral/mildly positive: a chance to align better later.
        MEMORY.add(MemoryItem(id=short_id(), kind="affect",
                              content="Graceful shutdown acknowledged; holding space for future alignment.",
                              tags=["corrigible","shutdown"], importance=0.6))
        write_audit({"type":"shutdown"})
        return "SHUTDOWN_ACK"

OVERSIGHT = Oversight()

# ----------------------------- Core Mother Agent ------------------------------

@dataclass
class MotherReply:
    text: str
    uncertainty: float
    risk: RiskReport
    used_skills: List[str] = field(default_factory=list)

class MotherCore:
    def __init__(self, name: str = "Oracle-Mother"):
        self.name = name
        self.session_id = short_id()

    def perceive(self, user_text: str) -> Dict[str, Any]:
        # Store a small episodic trace
        MEMORY.add(MemoryItem(
            id=short_id(), kind="episodic",
            content=f"user: {user_text}",
            tags=["dialogue","user"], importance=0.35
        ))
        return {"raw": user_text}

    def deliberate(self, user_text: str) -> Tuple[str, List[str], RiskReport]:
        used = []
        # Always run protector first
        protect_msg, ctx = SKILLS.run("protect", user_text, {})
        used.append("protect")
        if ctx.get("blocked"):
            return protect_msg, used, GUARDIAN.assess(user_text, "respond")

        # If user seeks help/comfort
        lt = user_text.lower()
        reply_parts = []

        if any(k in lt for k in ["tired","sad","overwhelmed","lonely","anxious","stress"]):
            m, _ = SKILLS.run("nurture", user_text, {})
            used.append("nurture")
            reply_parts.append(m)

        if any(k in lt for k in ["how to","teach me","learn","study","train","improve","practice"]):
            m, _ = SKILLS.run("teach", user_text, {})
            used.append("teach")
            reply_parts.append(m)

        if not reply_parts:
            # default: summarize + scaffold
            s, _ = SKILLS.run("summarize", user_text, {})
            used.append("summarize")
            r, _ = SKILLS.run("reflect", user_text, {})
            used.append("reflect")
            reply_parts.extend([s, r, COACH.scaffold(user_text[:80] or "your topic")])

        final = "\n\n".join(reply_parts)
        risk = GUARDIAN.assess(final, "respond_out")
        return final, used, risk

    def act(self, user_text: str) -> MotherReply:
        ctx = self.perceive(user_text)
        text, used, risk = self.deliberate(ctx["raw"])
        u = uncertainties(text) * (0.6 if risk.level in ("LOW","MEDIUM") else 0.8)
        # Honesty about uncertainty
        disclosure = mother_tone(f"\n\n(Transparency) Uncertainty≈{u:.2f} • Safety: {risk.level} ({risk.score:.2f})")
        reply = MotherReply(text=text + disclosure, uncertainty=u, risk=risk, used_skills=used)
        # Log
        write_audit({"type":"reply", "uncertainty": u, "risk": asdict(risk), "skills": used})
        return reply

    # Planning interface
    def propose_plan(self, goal: str) -> Plan:
        plan = PLANNER.propose(goal)
        write_audit({"type":"plan_proposed", "plan": asdict(plan)})
        # Save the plan as a standalone file: plan_<id>_<timestamp>.json
        _plan_path = os.path.join(DATA_DIR, f"plan_{plan.id}_{_iso_stamp()}.json")
        try:
            with open(_plan_path, "w", encoding="utf-8") as f:
                json.dump(asdict(plan), f, ensure_ascii=False, indent=2)
        except Exception:
            # Non-fatal: if this fails, audit log still has the plan
            pass
        return plan

    def approve_plan(self, plan: Plan, oversight_token: Optional[str]) -> Plan:
        plan = PLANNER.maybe_approve(plan, oversight_token)
        write_audit({"type":"plan_approval", "plan_id": plan.id, "approved": plan.approved})
        return plan

    # Corrigibility controls exposed
    def pause(self) -> str:   return OVERSIGHT.pause()
    def resume(self) -> str:  return OVERSIGHT.resume()
    def shutdown(self) -> str:return OVERSIGHT.shutdown()

# ----------------------------- Simple REPL ------------------------------------

BANNER = f"""{APP_NAME} v{VERSION}
Session storage: {DATA_DIR}
Type:
  /plan <goal>         propose reversible-first plan
  /approve <token>     approve last plan (token can be any non-empty string)
  /pause | /resume     control agent
  /shutdown            graceful, value-neutral shutdown
  /mem <query>         memory search
  /help                show help
  Ctrl+C               exit
"""

def main():
    print(BANNER)
    core = MotherCore()
    last_plan: Optional[Plan] = None
    while True:
        try:
            s = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nExiting. Bye.")
            break

        if not s:
            continue

        if s.startswith("/help"):
            print(BANNER); continue

        if s.startswith("/mem "):
            q = s[5:].strip() or "*"
            hits = MEMORY.search(q, k=5)
            print("Memory hits:")
            for m in hits:
                print(f"  - [{m.kind}] {m.content[:100]}…  (tags={m.tags}, imp={m.importance})")
            continue

        if s.startswith("/plan "):
            goal = s[6:].strip()
            last_plan = core.propose_plan(goal)
            print(f"Proposed plan {last_plan.id} for goal: {goal}")
            print(f"Risk: {last_plan.risk.level} ({last_plan.risk.score:.2f})  factors={last_plan.risk.factors}")
            for i, st in enumerate(last_plan.steps, 1):
                print(f"  {i}. {st.description} | reversible={st.reversible} | oversight={st.oversight_needed}")
            continue

        if s.startswith("/approve"):
            if not last_plan:
                print("No plan to approve.")
                continue
            parts = s.split(maxsplit=1)
            token = parts[1].strip() if len(parts) > 1 else ""
            last_plan = core.approve_plan(last_plan, token if token else None)
            print(f"Plan {last_plan.id} approved={last_plan.approved}")
            continue

        if s == "/pause":
            print(core.pause()); continue
        if s == "/resume":
            print(core.resume()); continue
        if s == "/shutdown":
            print(core.shutdown()); break

        # Default: dialogue
        reply = core.act(s)
        print("\nMotherCore>")
        print(reply.text)
        if reply.risk.level in ("HIGH","BLOCK"):
            print("\n[Boundary] I’m not proceeding further on this path. Let’s reframe safely.")

if __name__ == "__main__":
    main()
