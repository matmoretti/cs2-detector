# -*- coding: utf-8 -*-
r"""
Rotulagem humana de episódios — Fase D0.3
=========================================
Grava o veredito de uma revisão em primeira pessoa no dataset forense
(`dados/episodios.jsonl`). As revisões são **append-only**: uma nova revisão
nunca sobrescreve a anterior (regra do protocolo de rotulagem da
ARQUITETURA-ML — o histórico original é preservado para adjudicação).

Uso:
    python rotular.py listar [filtro]
        Lista episódios (id curto, mapa, round, tipo, atacante, rótulo atual).
        O filtro casa com mapa, tipo ou nome do atacante/vítima.

    python rotular.py <episode_id> <conclusao> [--tipo "..."] [--confianca X]
                      [--nota "..."] [--revisor nome]
        Anexa uma revisão ao episódio. `conclusao` deve ser uma de:
        legitimo_explicado · inconclusivo_dados · ambiguo_contexto ·
        evidencia_forte
"""

import os
import sys
import json
import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_EPISODIOS = os.path.join(PASTA, "dados", "episodios.jsonl")
ARQ_MAPA_JOGADORES = os.path.join(PASTA, "dados", "mapa_jogadores.json")

CONCLUSOES = ("legitimo_explicado", "inconclusivo_dados",
              "ambiguo_contexto", "evidencia_forte")


def carregar(caminho=ARQ_EPISODIOS):
    eps = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                eps.append(json.loads(linha))
    return eps


def salvar(eps, caminho=ARQ_EPISODIOS):
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for ep in eps:
            f.write(json.dumps(ep, ensure_ascii=False) + "\n")
    os.replace(tmp, caminho)


def nomes():
    try:
        with open(ARQ_MAPA_JOGADORES, encoding="utf-8") as f:
            return {k: v.get("nome", "?") for k, v in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def rotular(eps, episode_id, conclusao, tipo_evidencia=None, confianca=None,
            nota=None, revisor="autor", data=None):
    """Anexa uma revisão ao episódio (append-only). Retorna o episódio."""
    if conclusao not in CONCLUSOES:
        raise ValueError(f"conclusão inválida: {conclusao!r} "
                         f"(use uma de {', '.join(CONCLUSOES)})")
    alvo = next((e for e in eps if e["episode_id"] == episode_id), None)
    if alvo is None:
        raise KeyError(f"episódio não encontrado: {episode_id}")
    revisao = {
        "revisor": revisor,
        "data": data or datetime.date.today().isoformat(),
        "conclusao": conclusao,
        "tipo_evidencia": tipo_evidencia,
        "confianca": confianca,
        "nota": nota,
    }
    if not isinstance(alvo.get("rotulo_humano"), dict):
        alvo["rotulo_humano"] = {"revisoes": [], "adjudicacao": None}
    alvo["rotulo_humano"]["revisoes"].append(revisao)
    return alvo


def _resumo(ep, nm):
    ide = ep["identidade"]
    rot = ep.get("rotulo_humano")
    if isinstance(rot, dict) and rot.get("revisoes"):
        ult = rot["revisoes"][-1]
        rtxt = f"{ult['conclusao']} ({ult['revisor']})"
    else:
        rtxt = "—"
    atk = nm.get(ide.get("atacante_id"), "?")
    vit = nm.get(ide.get("vitima_id"), "?")
    return (f"{ep['episode_id']}  {ide['mapa']:<11} R{ide['round']:>2} "
            f"t{ide['tick']:<7} {ide['candidate_source']:<13} "
            f"{atk[:14]:<14} vs {vit[:14]:<14} peso={ep['saida_regra']['peso']} "
            f"rótulo: {rtxt}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    eps = carregar()

    if sys.argv[1] == "listar":
        filtro = sys.argv[2].lower() if len(sys.argv) > 2 else ""
        nm = nomes()
        for ep in eps:
            linha = _resumo(ep, nm)
            if filtro in linha.lower():
                print(linha)
        return

    episode_id = sys.argv[1]
    if len(sys.argv) < 3:
        print("Faltou a conclusão. Use: python rotular.py <id> <conclusao> ...")
        sys.exit(1)
    conclusao = sys.argv[2]
    kw = {"tipo_evidencia": None, "confianca": None, "nota": None,
          "revisor": "autor"}
    args = sys.argv[3:]
    i = 0
    while i < len(args):
        chave = args[i].lstrip("-").replace("tipo", "tipo_evidencia") \
            if args[i] in ("--tipo",) else args[i].lstrip("-")
        if chave in kw and i + 1 < len(args):
            kw[chave] = args[i + 1]
            i += 2
        else:
            print(f"argumento desconhecido: {args[i]}")
            sys.exit(1)

    ep = rotular(eps, episode_id, conclusao, **kw)
    salvar(eps)
    print("Revisão gravada:")
    print(json.dumps(ep["rotulo_humano"]["revisoes"][-1],
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
