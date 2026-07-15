# -*- coding: utf-8 -*-
"""
Reconsulta na Steam todos os jogadores do historico.json e avisa quem tomou
ban NOVO desde a última checagem. Rode de tempos em tempos (ex.: 1x por semana)
com dois cliques no CHECAR-BANS.bat.
"""

import sys
import os
import json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import steam_info

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_HISTORICO = os.path.join(PASTA, "historico.json")


def main():
    if not os.path.exists(ARQ_HISTORICO):
        print("historico.json ainda não existe — analise ao menos uma demo antes.")
        sys.exit(1)

    with open(ARQ_HISTORICO, encoding="utf-8") as f:
        hist = json.load(f)

    cfg = steam_info.carregar_config()
    chave = cfg.get("steam_api_key") or None
    fonte = "API oficial" if chave else "perfil público (sem chave de API)"
    sids = list(hist.keys())
    print(f"Checando {len(sids)} jogador(es) via {fonte}...\n")

    dados = steam_info.consultar_jogadores(sids, chave)

    novos_bans = []
    for sid, d in dados.items():
        antes = hist[sid].get("steam", {})
        vac_antes = bool(antes.get("vac"))
        jogo_antes = int(antes.get("bans_jogo", 0) or 0)
        vac_agora = bool(d.get("vac"))
        jogo_agora = int(d.get("bans_jogo", 0) or 0)
        if (vac_agora and not vac_antes) or (jogo_agora > jogo_antes):
            novos_bans.append(sid)
        hist[sid]["steam"] = {**antes, **d}

    with open(ARQ_HISTORICO, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)

    # resumo
    maior_score = lambda sid: max(
        (p["score"] for p in hist[sid].get("partidas", {}).values()), default=0)
    banidos = [s for s in sids if hist[s].get("steam", {}).get("vac")
               or int(hist[s].get("steam", {}).get("bans_jogo", 0) or 0) > 0]

    if novos_bans:
        print("🚨 BANS NOVOS desde a última checagem:")
        for sid in sorted(novos_bans, key=maior_score, reverse=True):
            st = hist[sid]["steam"]
            tipo = "VAC" if st.get("vac") else "ban de jogo"
            print(f"   ☠ {hist[sid]['nome']} — {tipo} "
                  f"(nosso maior score: {maior_score(sid)}/100)")
        print()

    if banidos:
        print(f"Total de banidos entre os {len(sids)} já analisados: {len(banidos)}")
        flagrados = [s for s in banidos if maior_score(s) >= 30]
        if flagrados:
            print(f"…dos quais {len(flagrados)} o detector tinha marcado como "
                  f"MÉDIO ou ALTO. 🎯")
    else:
        print("Nenhum ban entre os jogadores analisados (por enquanto).")

    erros = [s for s, d in dados.items() if d.get("erro")]
    if erros:
        print(f"\n({len(erros)} perfil(is) não puderam ser consultados agora)")


if __name__ == "__main__":
    main()
