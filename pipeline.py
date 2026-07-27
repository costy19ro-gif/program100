"""
Miliardarul Pipeline — motorul statistic
==========================================
Port Python al pipeline-ului construit in Excel:

  1. Decay exponential (half-life configurabil) pe istoricul real de meciuri
  2. Shrinkage Bayesian (James-Stein) pentru esantioane mici
  3. Reconciliere lambda/mu (o singura sursa de adevar pentru expected goals)
  4. Corectie Dixon-Coles (tau) pentru scorurile mici + renormalizare
  5. Scanner de piete: extrage orice piata (1X2, GG, Over/Under, combo) direct
     din matricea de scor, ca probabilitate reala (nu inmultire naiva de cote)

Toate functiile sunt pure (nu ating retea/fisiere) — usor de testat izolat.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from math import exp, log, factorial
from typing import Sequence


# ---------------------------------------------------------------------------
# 1. STRUCTURA DE DATE PENTRU UN MECI ISTORIC
# ---------------------------------------------------------------------------

@dataclass
class MeciIstoric:
    """Un singur meci din istoricul unei echipe."""
    data: date
    goluri_marcate: int
    goluri_primite: int
    goluri_marcate_pauza: int | None = None
    goluri_primite_pauza: int | None = None


# ---------------------------------------------------------------------------
# 2. DECAY EXPONENTIAL (Modulul B)
# ---------------------------------------------------------------------------

def pondere_decay(zile_diferenta: int, half_life_zile: float = 30.0) -> float:
    """Pondere exponentiala: la half_life_zile distanta, ponderea = 0.5."""
    return exp(-log(2) / half_life_zile * zile_diferenta)


def atac_aparare_decay(
    meciuri: Sequence[MeciIstoric],
    data_referinta: date,
    half_life_zile: float = 30.0,
) -> dict:
    """
    Calculeaza media ponderata (decay) a golurilor marcate/primite,
    plus "n efectiv" (Kish effective sample size) — cate meciuri
    "conteaza" de fapt dupa aplicarea decay-ului.

    Returneaza si echivalentul pentru prima repriza, daca datele exista.
    """
    if not meciuri:
        raise ValueError("Lista de meciuri istorice este goala.")

    ponderi, marcate, primite = [], [], []
    marcate_pauza, primite_pauza = [], []
    are_date_pauza = all(
        m.goluri_marcate_pauza is not None and m.goluri_primite_pauza is not None
        for m in meciuri
    )

    for m in meciuri:
        zile = (data_referinta - m.data).days
        w = pondere_decay(zile, half_life_zile)
        ponderi.append(w)
        marcate.append(m.goluri_marcate)
        primite.append(m.goluri_primite)
        if are_date_pauza:
            marcate_pauza.append(m.goluri_marcate_pauza)
            primite_pauza.append(m.goluri_primite_pauza)

    suma_ponderi = sum(ponderi)
    suma_patrate = sum(w ** 2 for w in ponderi)

    atac = sum(w * g for w, g in zip(ponderi, marcate)) / suma_ponderi
    aparare = sum(w * g for w, g in zip(ponderi, primite)) / suma_ponderi
    n_efectiv = (suma_ponderi ** 2) / suma_patrate if suma_patrate else 0.0

    rezultat = {
        "atac_decay": atac,
        "aparare_decay": aparare,
        "n_efectiv": n_efectiv,
    }

    if are_date_pauza:
        rezultat["atac_decay_pauza"] = sum(w * g for w, g in zip(ponderi, marcate_pauza)) / suma_ponderi
        rezultat["aparare_decay_pauza"] = sum(w * g for w, g in zip(ponderi, primite_pauza)) / suma_ponderi

    return rezultat


# ---------------------------------------------------------------------------
# 3. SHRINKAGE BAYESIAN + RECONCILIERE LAMBDA/MU (Modulul C + reconciliere)
# ---------------------------------------------------------------------------

def reconciliaza_lambda_mu(
    gazde: dict,
    oaspeti: dict,
    k_shrinkage: float = 10.0,
) -> dict:
    """
    Primeste rezultatele `atac_aparare_decay` pentru ambele echipe si
    calculeaza lambda (Gazde) / mu (Oaspeti) canonic, dupa shrinkage
    Bayesian catre o medie de referinta proprie meciului.

    Formula standard: lambda = Atac_Gazde_shrunk * Aparare_Oaspeti_shrunk / medie_referinta
    """
    medie_referinta = (
        gazde["atac_decay"] + gazde["aparare_decay"]
        + oaspeti["atac_decay"] + oaspeti["aparare_decay"]
    ) / 4.0

    w_gazde = gazde["n_efectiv"] / (gazde["n_efectiv"] + k_shrinkage)
    w_oaspeti = oaspeti["n_efectiv"] / (oaspeti["n_efectiv"] + k_shrinkage)

    atac_gazde_shrunk = w_gazde * gazde["atac_decay"] + (1 - w_gazde) * medie_referinta
    aparare_gazde_shrunk = w_gazde * gazde["aparare_decay"] + (1 - w_gazde) * medie_referinta
    atac_oaspeti_shrunk = w_oaspeti * oaspeti["atac_decay"] + (1 - w_oaspeti) * medie_referinta
    aparare_oaspeti_shrunk = w_oaspeti * oaspeti["aparare_decay"] + (1 - w_oaspeti) * medie_referinta

    lam = atac_gazde_shrunk * aparare_oaspeti_shrunk / medie_referinta
    mu = atac_oaspeti_shrunk * aparare_gazde_shrunk / medie_referinta

    rezultat = {
        "medie_referinta": medie_referinta,
        "w_gazde": w_gazde,
        "w_oaspeti": w_oaspeti,
        "atac_gazde_shrunk": atac_gazde_shrunk,
        "aparare_gazde_shrunk": aparare_gazde_shrunk,
        "atac_oaspeti_shrunk": atac_oaspeti_shrunk,
        "aparare_oaspeti_shrunk": aparare_oaspeti_shrunk,
        "lambda_gazde": lam,
        "mu_oaspeti": mu,
    }

    # Prima repriza, daca datele exista pentru ambele echipe
    if "atac_decay_pauza" in gazde and "atac_decay_pauza" in oaspeti:
        fractie_pauza = (
            (gazde["atac_decay_pauza"] + oaspeti["atac_decay_pauza"])
            / (gazde["atac_decay"] + oaspeti["atac_decay"])
        )
        rezultat["fractie_prima_repriza"] = fractie_pauza
        rezultat["lambda_total_prima_repriza"] = (lam + mu) * fractie_pauza

    return rezultat


# ---------------------------------------------------------------------------
# 4. MATRICEA POISSON + CORECTIA DIXON-COLES (Modulul A)
# ---------------------------------------------------------------------------

def _poisson(k: int, medie: float) -> float:
    return exp(-medie) * medie ** k / factorial(k)


def _tau_dixon_coles(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    if x == 1 and y == 0:
        return 1 + mu * rho
    if x == 0 and y == 1:
        return 1 + lam * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def matrice_scor(
    lam: float,
    mu: float,
    rho: float = -0.18,
    goluri_max: int = 8,
) -> list[list[float]]:
    """
    Returneaza matricea de probabilitati P[gol_gazde][gol_oaspeti],
    corectata Dixon-Coles si renormalizata la suma 1.0.
    """
    P = [[_poisson(h, lam) * _poisson(a, mu) for a in range(goluri_max)] for h in range(goluri_max)]

    for h in range(2):
        for a in range(2):
            P[h][a] *= _tau_dixon_coles(h, a, lam, mu, rho)

    total = sum(sum(row) for row in P)
    return [[v / total for v in row] for row in P]


# ---------------------------------------------------------------------------
# 5. SCANNER DE PIETE — extrage orice piata direct din matrice
# ---------------------------------------------------------------------------

def scanner_piete(matrice: list[list[float]]) -> dict:
    """Calculeaza toate pietele standard, ca probabilitate reala (nu inmultire)."""
    n = len(matrice)

    def suma_unde(conditie):
        return sum(
            matrice[h][a]
            for h in range(n)
            for a in range(n)
            if conditie(h, a)
        )

    piete = {
        "1": suma_unde(lambda h, a: h > a),
        "X": suma_unde(lambda h, a: h == a),
        "2": suma_unde(lambda h, a: h < a),
        "Gazde_marcheaza": suma_unde(lambda h, a: h > 0),
        "Oaspeti_marcheaza": suma_unde(lambda h, a: a > 0),
        "GG": suma_unde(lambda h, a: h > 0 and a > 0),
        "Peste_0.5": suma_unde(lambda h, a: (h + a) > 0.5),
        "Peste_1.5": suma_unde(lambda h, a: (h + a) > 1.5),
        "Peste_2.5": suma_unde(lambda h, a: (h + a) > 2.5),
        "Peste_3.5": suma_unde(lambda h, a: (h + a) > 3.5),
    }
    piete["1X"] = piete["1"] + piete["X"]
    piete["X2"] = piete["X"] + piete["2"]
    piete["12"] = piete["1"] + piete["2"]
    piete["NO_GOL"] = 1 - piete["GG"]
    piete["Sub_2.5"] = 1 - piete["Peste_2.5"]
    piete["Sub_1.5"] = 1 - piete["Peste_1.5"]
    return piete


def combo(matrice: list[list[float]], conditii: list) -> float:
    """
    Probabilitate REALA a intersectiei mai multor conditii (nu inmultire naiva).
    `conditii` e o lista de functii(h, a) -> bool.
    """
    n = len(matrice)
    return sum(
        matrice[h][a]
        for h in range(n)
        for a in range(n)
        if all(cond(h, a) for cond in conditii)
    )


def scor_probabil(matrice: list[list[float]], top_n: int = 5) -> list[tuple[int, int, float]]:
    """Returneaza cele mai probabile `top_n` scoruri, descrescator."""
    n = len(matrice)
    scoruri = [(h, a, matrice[h][a]) for h in range(n) for a in range(n)]
    return sorted(scoruri, key=lambda x: -x[2])[:top_n]


# ---------------------------------------------------------------------------
# 6. FUNCTIE DE NIVEL INALT — ruleaza tot pipeline-ul dintr-o data
# ---------------------------------------------------------------------------

def analizeaza_meci(
    meciuri_gazde: Sequence[MeciIstoric],
    meciuri_oaspeti: Sequence[MeciIstoric],
    data_referinta: date | None = None,
    half_life_zile: float = 30.0,
    k_shrinkage: float = 10.0,
    rho: float = -0.18,
) -> dict:
    """Punctul de intrare unic: dai istoricul brut, primesti tot rezultatul."""
    if data_referinta is None:
        data_referinta = date.today()

    gazde_stats = atac_aparare_decay(meciuri_gazde, data_referinta, half_life_zile)
    oaspeti_stats = atac_aparare_decay(meciuri_oaspeti, data_referinta, half_life_zile)
    reconciliere = reconciliaza_lambda_mu(gazde_stats, oaspeti_stats, k_shrinkage)

    matrice = matrice_scor(reconciliere["lambda_gazde"], reconciliere["mu_oaspeti"], rho)
    piete = scanner_piete(matrice)
    top_scoruri = scor_probabil(matrice)

    return {
        "gazde_stats": gazde_stats,
        "oaspeti_stats": oaspeti_stats,
        "reconciliere": reconciliere,
        "matrice": matrice,
        "piete": piete,
        "top_scoruri": top_scoruri,
    }
