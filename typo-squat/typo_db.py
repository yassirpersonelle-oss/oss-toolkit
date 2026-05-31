KNOWN_TYPOS = {
    "requests": ["requestz", "requets", "reqests"],
    "numpy": ["numpyy", "numpi", "nummpy"],
    "pandas": ["pandasz", "panda"],
    "flask": ["flasky", "flaskk", "flasck"],
    "django": ["djangoo", "djanggo"],
    "scikit-learn": ["scikit-learrn", "sklearrn"],
    "pillow": ["pillowy", "pilow"],
    "beautifulsoup4": ["beautifulsoup", "beautifullsoup"],
    "matplotlib": ["matplotlip", "matplotlib"],
    "tensorflow": ["tensorlow", "tensorflo"],
    "torch": ["torc", "torrrch"],
    "pip": ["ppip", "pipp"],
    "selenium": ["seleniumm", "seleniium"],
    "pytest": ["pytests", "pyttest"],
    "click": ["clck", "clic"],
    "urllib3": ["urlllib3", "urllib"],
    "pyyaml": ["pyyamll", "pyyml"],
    "jinja2": ["jinjaa", "jinja22"],
    "boto3": ["botoo3", "boto33"],
    "fastapi": ["fastapii", "fasttapi"],
    "uvicorn": ["uvicron", "uvicornn"],
    "gunicorn": ["gunicron", "gunicornn"],
    "lodash": ["lodashh", "lowdash"],
    "express": ["expres", "exprss"],
    "axios": ["axioz", "axois"],
    "moment": ["momemt", "momnet"],
    "chalk": ["chak", "chalck"],
    "commander": ["commanderr", "comander"],
    "winston": ["winstonn", "winstn"],
    "async": ["asyncc", "aync"],
    "request": ["requist", "reqest"],
}

POPULAR_PACKAGES = list(KNOWN_TYPOS.keys())

ALL_TYPOS = set()
for legit, typos in KNOWN_TYPOS.items():
    for t in typos:
        ALL_TYPOS.add(t.lower())

POPULAR_LOWER = set(p.lower() for p in POPULAR_PACKAGES)
