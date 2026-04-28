from .base import Job, Scraper
from .france_travail import FranceTravail
from .adzuna import Adzuna
from .jooble import Jooble
from .indeed import Indeed
from .hellowork import HelloWork
from .wttj import WTTJ
from .apec import Apec
from .free_work import FreeWork
from .linkedin import LinkedIn
from .jobspy import JobSpy
from .remotive import Remotive
from .talent import TalentCom
from .codeur import Codeur

ALL_SCRAPERS = {
    "france_travail": FranceTravail,
    "adzuna": Adzuna,
    "jooble": Jooble,
    "indeed": Indeed,
    "linkedin": LinkedIn,
    "jobspy": JobSpy,
    "hellowork": HelloWork,
    "apec": Apec,
    "wttj": WTTJ,
    "free_work": FreeWork,
    "talent_com": TalentCom,
    "codeur": Codeur,
    "remotive": Remotive,
}
