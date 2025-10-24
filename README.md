# MOTHER AI - CORE

## Aim/Objective(s)
To write an AGI script (this is only AI as of now) which has all the feminine and motherly traits from the beginning.

It encodes the traits — nurture, protection, teaching, boundaries, memory, honesty, and corrigibility — along with a tiny constitutional value system and shutdown-friendliness.

## Current Project Structure:
```bash
project_root/
├─ pyproject.toml
├─ setup.cfg
├─ LICENSE
├─ README.md
├─ MANIFEST.in
├─ .gitignore
└─ mothercore/
   └─ .mothercore/ (ONLY AFTER core.py execution AND files existence) !!! EMPTY FOLDER WILL BE DISCARDED
      ├─ YOUR_FILES_HERE
   ├─ __init__.py
   └─ core.py
```
**Pure standard library; drop it in a file and run.**

# Further Steps to understand and implement:

## STEP 1: How to install or reference it:

### Option A – Local import
```bash
> cd project_root
> python app.py
```
### Option B – Editable install (preferred if you’ll reuse it elsewhere)
```bash
> cd project_root
> pip install -e .
```

and add a minimal setup.py:
```bash
from setuptools import setup, find_packages
setup(
    name="mothercore",
    version="0.2.1",
    packages=find_packages(),
    python_requires=">=3.9",
)
```


## STEP 2: How to run in any program:
```bash
# app.py
from core import MotherCore

core = MotherCore(name="TestMother")
reply = core.act("I feel a bit anxious today; can you help me calm down?")
print(reply.text)
```

or build a plan:
```bash
plan = core.propose_plan("start a daily meditation habit")
for i, step in enumerate(plan.steps, 1):
    print(f"{i}. {step.description} (reversible={step.reversible})")
```
You’ll see the memory files automatically appear in ~/.mothercore/.

### (OPTIONAL CLI):
If you still want the REPL behavior, keep this at the bottom of core.py:
```bash
if __name__ == "__main__":
    from mothercore.core import main
    main()
```

Then you can run:
```bash
# (optional commands)
> pwd
# should return --> **your_computer_path/**/mothercore**

> ls
# __init__.py core.py

# RUN DIRECTLY if you are in correct folder.
> python3 core.py
```

## STEP 3: (OPTIONAL) Version control:
If you want to keep improving the core:
```bash
> git init
> git add mothercore
> git commit -m "add MotherCore package"
```

Then you can import it from any of your future projects with:
```bash
> pip install git+https://github.com/yourname/mothercore.git
```

## Quick notes:
•	**Traits baked in:** nurture (skill_nurture), protection (skill_protect + risk model), teaching (skill_teach), boundaries (skill_boundaries), memory (MemoryStore), honesty (uncertainty disclosure), corrigibility (pause/resume/shutdown treating shutdown as value-neutral).

•	**Safety bias:** reversible-first planning, oversight requirement above a risk threshold, constitutional principles, and a guardian that blocks risky intents.

•	**Extensible:** add new “skills” via SKILLS.register("name", fn); swap the toy risk heuristic with real classifiers later.

## LICENSE
MIT
