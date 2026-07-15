# -*- coding: utf-8 -*-
r"""
CS2 Detector de Suspeitos — v5
==============================
Analisa demos (.dem) do CS2 e gera um relatório de suspeita por jogador,
combinando estatísticas de eventos com análise da MIRA tick a tick:

  * Flicks sobre-humanos ..... giro de mira enorme terminando em headshot instantâneo
  * Reação inumana ........... tempo entre mira-no-alvo e a kill abaixo do limite humano
  * Tracking (pré-aim) ....... mira "grudada" num alvo em movimento antes do confronto
  * Kills por smoke / parede . atirar em quem não dá pra ver
  * Kills cego de flash ...... idem
  * Precisão real ............ % de tiros que acertam e % de acertos na cabeça
  * Histórico ................ reincidência entre partidas analisadas (historico.json)

Uso:
    python analisar.py                        (acha a demo mais recente sozinho)
    python analisar.py caminho\partida.dem    (demo específica)

IMPORTANTE: estatística sugere, NÃO prova. O relatório aponta o round e o tick
exato de cada momento suspeito justamente para você assistir antes de denunciar.
"""

import sys
import os
import glob
import json
import math
import html
import bisect
import shutil
import pathlib
import datetime
import webbrowser

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from demoparser2 import DemoParser

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_HISTORICO = os.path.join(PASTA, "historico.json")

# ---------------------------------------------------------------------------
# Parâmetros da análise (64 ticks = 1 segundo)
# ---------------------------------------------------------------------------
JANELA = 160            # ticks analisados antes de cada kill (~2,5 s)
JANELA_CARREGA = 352    # ticks carregados (~5,5 s) p/ checar "viu o alvo antes"
NO_ALVO_GRAUS = 6.0     # mira a menos disso do alvo conta como "no alvo"
FLICK_MIN_GRAUS = 35.0  # giro mínimo p/ contar como flick
FLICK_REACAO_MAX = 3    # ticks (~47 ms) entre fim do flick e a kill
REACAO_RAPIDA_MAX = 2   # ticks (~31 ms) p/ "reação inumana"
REACAO_SNAP_MIN = 20.0  # a reação rápida só conta se veio de um giro real
TRACK_MIN_TICKS = 96    # ~1,5 s de mira grudada
TRACK_MIN_MOVIMENTO = 150.0  # o alvo precisa ter se movido (senão é só segurar ângulo)
TRACK_MIN_DIST = 400.0  # ignora tracking a queima-roupa (muito ruído)
TRACK_MIN_GIRO = 12.0   # a DIREÇÃO até o alvo precisa ter mudado: mira parada
                        # segurando ângulo enquanto o alvo anda no cone NÃO é tracking

ARMAS_IGNORAR = {
    "knife", "knife_t", "bayonet", "taser",
    "hegrenade", "flashbang", "smokegrenade", "molotov",
    "incgrenade", "decoy", "c4", "planted_c4", "inferno", "world",
}


# ---------------------------------------------------------------------------
# Localização de demos (pasta local + bibliotecas Steam)
# ---------------------------------------------------------------------------

def pastas_replays_steam():
    """Descobre as pastas de replays do CS2 em todas as bibliotecas Steam."""
    pastas = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam = winreg.QueryValueEx(k, "SteamPath")[0].replace("/", "\\")
    except Exception:
        steam = r"C:\Program Files (x86)\Steam"

    libs = [steam]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        import re
        with open(vdf, encoding="utf-8", errors="replace") as f:
            for m in re.finditer(r'"path"\s+"([^"]+)"', f.read()):
                libs.append(m.group(1).replace("\\\\", "\\"))

    for lib in libs:
        rep = os.path.join(lib, "steamapps", "common",
                           "Counter-Strike Global Offensive",
                           "game", "csgo", "replays")
        if os.path.isdir(rep) and rep not in pastas:
            pastas.append(rep)
    return pastas


def encontrar_demos():
    if len(sys.argv) > 1:
        alvos = [a for a in sys.argv[1:] if a.lower().endswith(".dem")]
        for a in alvos:
            if not os.path.exists(a):
                print(f"Arquivo não encontrado: {a}")
                sys.exit(1)
        if alvos:
            return alvos

    candidatos = glob.glob(os.path.join(PASTA, "*.dem"))
    for rep in pastas_replays_steam():
        candidatos += glob.glob(os.path.join(rep, "*.dem"))
    if not candidatos:
        print("Nenhuma demo (.dem) encontrada — nem nesta pasta, nem nas pastas "
              "de replays da Steam.")
        print("Baixe a demo no CS2 (Assistir > Suas Partidas > Baixar) e rode de novo.")
        sys.exit(1)

    mais_recente = max(candidatos, key=os.path.getmtime)
    print(f"Demo escolhida (mais recente): {os.path.basename(mais_recente)}")
    return [mais_recente]


# ---------------------------------------------------------------------------
# Matemática de mira
# ---------------------------------------------------------------------------

def norm180(a):
    return (a + 180.0) % 360.0 - 180.0


def desvio_mira(ax, ay, az, yaw, pitch, vx, vy, vz):
    """Menor ângulo (graus) entre a mira do atacante e o corpo da vítima.
    Testa cabeça/peito/quadril para tolerar agachamento."""
    melhor = None
    dist = 0.0
    for alvo_z in (64.0, 46.0, 18.0):
        dx, dy = vx - ax, vy - ay
        dz = (vz + alvo_z) - (az + 64.0)
        dxy = math.hypot(dx, dy)
        if dxy < 1.0:
            continue
        quer_yaw = math.degrees(math.atan2(dy, dx))
        quer_pitch = -math.degrees(math.atan2(dz, dxy))
        dyaw = norm180(quer_yaw - yaw) * math.cos(math.radians(pitch))
        dpitch = quer_pitch - pitch
        desvio = math.hypot(dyaw, dpitch)
        if melhor is None or desvio < melhor:
            melhor = desvio
            dist = math.hypot(dx, dy, dz)
    return melhor, dist


def giro_mira(yaw1, pitch1, yaw2, pitch2):
    """Rotação angular (graus) entre duas orientações de mira."""
    return math.hypot(norm180(yaw2 - yaw1) * math.cos(math.radians(pitch2)),
                      pitch2 - pitch1)


# ---------------------------------------------------------------------------
# Extração da demo
# ---------------------------------------------------------------------------

def get(linha, col, padrao):
    try:
        v = linha[col]
        if v is None or (isinstance(v, float) and v != v):
            return padrao
        return v
    except (KeyError, IndexError):
        return padrao


def novo_jogador(nome):
    return {
        "nome": nome, "kills": 0, "mortes": 0, "hs": 0,
        "smoke": 0, "wallbang": 0, "cego": 0,
        "flicks": 0, "reacoes": 0, "tracks": 0, "tracks_parede": 0,
        "tiros": 0, "acertos": 0, "acertos_cabeca": 0,
        # L7: escalada de score exige vítimas DISTINTAS (vítima previsível
        # dispara o mesmo sinal em vários atacantes)
        "vitimas_smoke": [], "vitimas_track": [], "vitimas_parede": [],
        "momentos": [],
    }


def carregar_visibilidade(mapa):
    """Geometria do mapa (awpy) para checar se havia parede na linha de visão."""
    tri = os.path.join(os.path.expanduser("~"), ".awpy", "tris", f"{mapa}.tri")
    if not os.path.exists(tri):
        print(f"  (geometria de {mapa} não encontrada — tracking sem checagem "
              "de parede; rode 'awpy get tris' para baixar)")
        return None
    try:
        from awpy.visibility import VisibilityChecker
        print(f"  Carregando geometria de {mapa} p/ linha de visão real (~10 s)...")
        return VisibilityChecker(path=pathlib.Path(tri))
    except Exception as e:
        print(f"  (falha ao carregar geometria de {mapa}: {e})")
        return None


def dados_radar(mapa):
    """Imagem de radar + calibração de coordenadas (awpy) para o relatório."""
    base = os.path.join(os.path.expanduser("~"), ".awpy", "maps")
    arq = os.path.join(base, "map-data.json")
    if not os.path.exists(arq):
        return None
    try:
        with open(arq, encoding="utf-8") as f:
            md = json.load(f).get(mapa)
        if not md:
            return None
        destino = os.path.join(PASTA, "maps")
        os.makedirs(destino, exist_ok=True)
        radar = {"pos_x": md["pos_x"], "pos_y": md["pos_y"],
                 "scale": md["scale"],
                 "lower_max": md.get("lower_level_max_units")}
        for sufixo, chave in (("", "img"), ("_lower", "img_lower")):
            src = os.path.join(base, f"{mapa}{sufixo}.png")
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(destino, f"{mapa}{sufixo}.png"))
                radar[chave] = f"maps/{mapa}{sufixo}.png"
        return radar if "img" in radar else None
    except Exception:
        return None


def analisar_demo(caminho):
    print(f"\nLendo demo: {os.path.basename(caminho)} ...")
    parser = DemoParser(caminho)

    try:
        header = parser.parse_header()
    except Exception:
        header = {}
    mapa = header.get("map_name", "?")

    kills_df = parser.parse_event("player_death", other=["total_rounds_played"])
    try:
        total_rounds = len(parser.parse_event("round_end"))
    except Exception:
        total_rounds = 0

    # --- ticks necessários (janela antes de cada kill) ---
    ticks_necessarios = set()
    kills_validas = []
    for _, m in kills_df.iterrows():
        a_sid = get(m, "attacker_steamid", None)
        v_sid = get(m, "user_steamid", None)
        if a_sid is None or v_sid is None or str(a_sid) == str(v_sid):
            continue
        T = int(get(m, "tick", 0))
        if T <= JANELA:
            continue
        kills_validas.append(m)
        ticks_necessarios.update(range(max(1, T - JANELA_CARREGA), T + 1))

    print(f"  {len(kills_validas)} kills; carregando mira/posição de "
          f"{len(ticks_necessarios)} ticks (pode levar ~1 min)...")

    tdf = parser.parse_ticks(["X", "Y", "Z", "yaw", "pitch", "is_alive"],
                             ticks=sorted(ticks_necessarios))
    lk = {}
    for r in tdf.itertuples(index=False):
        lk[(int(r.tick), str(r.steamid))] = (
            float(r.X), float(r.Y), float(r.Z),
            float(r.yaw), float(r.pitch), bool(r.is_alive))

    # tiros por jogador, ordenados por tick (p/ separar tap preciso de spray);
    # barulho_ticks (L5) inclui granadas — jogar decoy/HE também revela posição
    fires = parser.parse_event("weapon_fire")
    tiros_ticks = {}
    barulho_ticks = {}
    for _, f in fires.iterrows():
        sid = get(f, "user_steamid", None)
        arma = str(get(f, "weapon", "")).replace("weapon_", "")
        if sid is None:
            continue
        sid = str(sid)
        if arma not in ("knife", "knife_t", "bayonet"):
            barulho_ticks.setdefault(sid, []).append(int(f["tick"]))
        if arma not in ARMAS_IGNORAR:
            tiros_ticks.setdefault(sid, []).append(int(f["tick"]))
    for d in (tiros_ticks, barulho_ticks):
        for lst in d.values():
            lst.sort()

    def tiros_ultimos_2s(sid, T):
        lst = tiros_ticks.get(sid, [])
        return bisect.bisect_right(lst, T) - bisect.bisect_left(lst, T - 128)

    jogadores = {}
    candidatos_track = []

    def jog(sid, nome):
        p = jogadores.setdefault(str(sid), novo_jogador(nome))
        p["nome"] = nome
        return p

    # --- análise kill a kill ---
    for m in kills_validas:
        a_sid, v_sid = str(m["attacker_steamid"]), str(m["user_steamid"])
        a_nome = get(m, "attacker_name", "?")
        v_nome = get(m, "user_name", "?")
        T = int(m["tick"])
        rodada = int(get(m, "total_rounds_played", 0)) + 1
        arma = str(get(m, "weapon", "?"))
        headshot = bool(get(m, "headshot", False))

        atacante = jog(a_sid, a_nome)
        vitima = jog(v_sid, v_nome)
        atacante["kills"] += 1
        vitima["mortes"] += 1
        if headshot:
            atacante["hs"] += 1

        a_kill = lk.get((T, a_sid))
        v_kill = lk.get((T, v_sid))

        def momento(tipo, desc, peso):
            d = {
                "tipo": tipo, "desc": desc, "round": rodada, "tick": T,
                "vitima": v_nome, "arma": arma, "peso": peso,
                "apos": [round(a_kill[0]), round(a_kill[1]),
                         round(a_kill[2])] if a_kill else None,
                "vpos": [round(v_kill[0]), round(v_kill[1]),
                         round(v_kill[2])] if v_kill else None,
            }
            atacante["momentos"].append(d)
            return d

        if get(m, "thrusmoke", False):
            # filtro anti-falso-positivo: smoke kill só é suspeita se foi tiro
            # preciso (não spray) e a uma distância em que não se vê nada
            dist_m = float(get(m, "distance", 0.0))
            n_tiros = tiros_ultimos_2s(a_sid, T)
            if dist_m >= 7.0 and n_tiros <= 4:
                atacante["smoke"] += 1
                atacante["vitimas_smoke"].append(v_nome)
                # timing de gatilho: acertar alvo RÁPIDO cruzando a smoke com a
                # mira parada exige disparar a ±40 ms do cruzamento — repetido,
                # sugere ESP de posição (anotação sem peso no score, em validação)
                extra, peso_s = "", 3
                v8 = lk.get((T - 8, v_sid))
                a64 = lk.get((T - 64, a_sid))
                if v_kill and v8 and a_kill and a64:
                    vel_v = math.hypot(v_kill[0] - v8[0],
                                       v_kill[1] - v8[1]) / (8 / 64.0)
                    giro = giro_mira(a64[3], a64[4], a_kill[3], a_kill[4])
                    if vel_v >= 150 and giro <= 3.0:
                        extra = (f" — GATILHO CIRÚRGICO: alvo cruzando a "
                                 f"{vel_v:.0f} u/s com a mira parada "
                                 f"(giro de {giro:.1f}° no último segundo)")
                        peso_s = 4
                momento("SMOKE", f"kill através de smoke a {dist_m:.0f} m com "
                                 f"tiro preciso ({n_tiros} tiro(s) em 2 s)"
                                 f"{extra}", peso_s)
            else:
                motivo = ("briga dentro/perto da smoke"
                          if dist_m < 7.0 else f"spray de {n_tiros} tiros")
                momento("SMOKE-COMUM", f"kill por smoke SEM pontuar "
                                       f"({motivo}, {dist_m:.0f} m)", 0)
        if int(get(m, "penetrated", 0)) > 0:
            atacante["wallbang"] += 1
            momento("PAREDE", "kill através de parede/objeto", 2)
        if get(m, "attackerblind", False):
            atacante["cego"] += 1
            momento("CEGO", "kill enquanto cego de flashbang", 3)

        # --- série de desvio da mira em relação à vítima ---
        desvios = {}
        pos_vitima = {}
        for t in range(T - JANELA, T + 1):
            a = lk.get((t, a_sid))
            v = lk.get((t, v_sid))
            if a is None or v is None:
                continue
            if not v[5] and t != T:
                continue
            d, dist = desvio_mira(a[0], a[1], a[2], a[3], a[4],
                                  v[0], v[1], v[2])
            if d is not None:
                desvios[t] = (d, dist)
                pos_vitima[t] = (v[0], v[1], v[2])

        if len(desvios) < 32:
            continue  # dados insuficientes nesta kill

        # flick: rotação líquida da mira nos últimos 8 ticks (~125 ms)
        a_fim = lk.get((T, a_sid))
        a_antes = lk.get((T - 8, a_sid))
        snap = 0.0
        if a_fim and a_antes:
            snap = giro_mira(a_antes[3], a_antes[4], a_fim[3], a_fim[4])

        # reação: há quantos ticks a mira está "no alvo" antes da kill
        reacao = None
        i = 0
        while True:
            t = T - i
            if t not in desvios:
                if i == 0:
                    i += 1
                    continue
                break
            if desvios[t][0] > NO_ALVO_GRAUS:
                break
            i += 1
            if i > JANELA:
                break
        ticks_no_alvo = max(0, i - 1)
        if 0 < ticks_no_alvo <= JANELA:
            reacao = ticks_no_alvo

        if (snap >= FLICK_MIN_GRAUS and reacao is not None
                and reacao <= FLICK_REACAO_MAX and headshot):
            atacante["flicks"] += 1
            momento("FLICK", f"giro de {snap:.0f}° terminando em headshot "
                             f"em {reacao * 15.6:.0f} ms", 5)
        elif (reacao is not None and reacao <= REACAO_RAPIDA_MAX
                and snap >= REACAO_SNAP_MIN):
            atacante["reacoes"] += 1
            momento("REAÇÃO", f"mira chegou no alvo e matou em "
                              f"{reacao * 15.6:.0f} ms (giro de {snap:.0f}°)", 3)

        # tracking: maior sequência contínua de mira no alvo ANTES do confronto
        melhor_seq, seq_ini, seq_fim = 0, None, None
        atual_ini = None
        for t in range(T - JANELA, T - 16):
            ok = t in desvios and desvios[t][0] <= NO_ALVO_GRAUS \
                and desvios[t][1] >= TRACK_MIN_DIST
            if ok:
                if atual_ini is None:
                    atual_ini = t
                if t - atual_ini + 1 > melhor_seq:
                    melhor_seq = t - atual_ini + 1
                    seq_ini, seq_fim = atual_ini, t
            else:
                atual_ini = None

        if melhor_seq >= TRACK_MIN_TICKS and seq_ini in pos_vitima \
                and seq_fim in pos_vitima:
            p1, p2 = pos_vitima[seq_ini], pos_vitima[seq_fim]
            movimento = math.hypot(p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
            if movimento >= TRACK_MIN_MOVIMENTO:
                amostras = []
                for t in range(seq_ini, seq_fim + 1, 8):
                    a = lk.get((t, a_sid))
                    v = lk.get((t, v_sid))
                    if a and v:
                        amostras.append(((a[0], a[1], a[2] + 64.0),
                                         (v[0], v[1], v[2] + 32.0)))

                # a mira precisa ter SEGUIDO o alvo: soma da mudança de direção
                # atacante→vítima ao longo da janela (mira parada não conta)
                giro_necessario = 0.0
                for i in range(1, len(amostras)):
                    a1, v1 = amostras[i - 1]
                    a2, v2 = amostras[i]
                    y1 = math.degrees(math.atan2(v1[1] - a1[1], v1[0] - a1[0]))
                    y2 = math.degrees(math.atan2(v2[1] - a2[1], v2[0] - a2[0]))
                    giro_necessario += abs(norm180(y2 - y1))

                # L4+L5: vítima que atirou OU jogou granada há <=5 s revelou
                # a posição (som/tracer/radar)
                barulho_v = barulho_ticks.get(v_sid, [])
                vitima_barulho = (bisect.bisect_right(barulho_v, seq_fim)
                                  - bisect.bisect_left(barulho_v, seq_ini - 320)) > 0

                if giro_necessario < TRACK_MIN_GIRO:
                    pass  # segurar ângulo parado — jogada normal, nem registra
                elif vitima_barulho:
                    momento("TRACK-INFO", f"mira acompanhou o alvo por "
                            f"{melhor_seq / 64.0:.1f} s, mas a vítima atirou/"
                            "jogou granada nos 5 s anteriores (posição "
                            "revelada — não pontua)", 0)
                else:
                    mom = momento("TRACK", f"mira ACOMPANHOU alvo em movimento "
                                  f"(giro de {giro_necessario:.0f}°) por "
                                  f"{melhor_seq / 64.0:.1f} s antes da kill, "
                                  "sem barulho da vítima nos 5 s anteriores", 4)
                    candidatos_track.append((atacante, mom, amostras,
                                             a_sid, v_sid, seq_ini))

    # --- classificação dos trackings: havia parede na linha de visão? ---
    checker = carregar_visibilidade(mapa) if candidatos_track else None
    for atacante, mom, amostras, a_sid, v_sid, seq_ini in candidatos_track:
        # L6: se o atacante VIU o alvo nos ~3 s antes da janela, é jogada de
        # "última posição conhecida", não wallhack
        viu_antes = False
        if checker:
            for t in range(seq_ini - 192, seq_ini, 16):
                a = lk.get((t, a_sid))
                v = lk.get((t, v_sid))
                if a and v and v[5] and checker.is_visible(
                        (a[0], a[1], a[2] + 64.0), (v[0], v[1], v[2] + 32.0)):
                    viu_antes = True
                    break
        if viu_antes:
            mom["tipo"] = "TRACK-VIU"
            mom["peso"] = 0
            mom["desc"] += (" — mas o atacante teve linha de visão para o alvo "
                            "segundos antes (última posição conhecida — não pontua)")
            continue

        atras_parede = False
        if checker and len(amostras) >= 4:
            invisiveis = sum(1 for a, v in amostras
                             if not checker.is_visible(a, v))
            frac = invisiveis / len(amostras)
            if frac >= 0.7:
                atras_parede = True
                mom["tipo"] = "TRACK-PAREDE"
                mom["peso"] = 6
                mom["desc"] += (f" — em {100 * frac:.0f}% do tempo havia PAREDE "
                                "entre eles (checado na geometria do mapa)")
        if atras_parede:
            atacante["tracks_parede"] += 1
            atacante["vitimas_parede"].append(mom["vitima"])
        else:
            atacante["tracks"] += 1
            atacante["vitimas_track"].append(mom["vitima"])

    # --- precisão do jogo inteiro ---
    for sid, lst in tiros_ticks.items():
        if sid in jogadores:
            jogadores[sid]["tiros"] = len(lst)

    hurts = parser.parse_event("player_hurt")
    for _, h in hurts.iterrows():
        sid = get(h, "attacker_steamid", None)
        arma = str(get(h, "weapon", "")).replace("weapon_", "")
        if sid is None or arma in ARMAS_IGNORAR:
            continue
        sid = str(sid)
        if sid not in jogadores:
            continue
        if str(get(h, "user_steamid", "")) == sid:
            continue
        jogadores[sid]["acertos"] += 1
        if str(get(h, "hitgroup", "")) == "head":
            jogadores[sid]["acertos_cabeca"] += 1

    return jogadores, {"mapa": mapa, "rounds": total_rounds,
                       "arquivo": os.path.basename(caminho),
                       "radar": dados_radar(mapa)}


# ---------------------------------------------------------------------------
# Pontuação (0–100)
# ---------------------------------------------------------------------------

def escada(n, degraus):
    """degraus = [(min_n, pontos), ...] em ordem crescente; retorna o maior."""
    pts = 0
    for minimo, valor in degraus:
        if n >= minimo:
            pts = valor
    return pts


def pontuar(p):
    comp = {}
    # L7: sinais situacionais escalam por VÍTIMAS DISTINTAS, não por repetição
    # na mesma vítima (vítima previsível dispara o sinal em vários atacantes)
    def vitimas(chave):
        return len(set(p.get(chave, [])))

    comp["Flicks sobre-humanos"] = escada(p["flicks"], [(1, 12), (2, 22), (3, 30)])
    comp["Reações inumanas"] = escada(p["reacoes"], [(1, 4), (2, 8), (3, 12)])
    comp["Tracking ATRAVÉS DE PAREDE"] = escada(vitimas("vitimas_parede"),
                                                [(1, 10), (2, 22), (3, 35)])
    comp["Tracking pré-confronto"] = escada(vitimas("vitimas_track"),
                                            [(1, 6), (2, 12), (3, 18), (4, 24)])
    comp["Kills por smoke"] = escada(vitimas("vitimas_smoke"),
                                     [(1, 3), (2, 8), (3, 15), (5, 24)])
    comp["Wallbangs"] = escada(p["wallbang"], [(3, 8), (5, 14)])
    comp["Kills cego"] = escada(p["cego"], [(2, 8)])

    hs_pct = 100.0 * p["hs"] / p["kills"] if p["kills"] else 0.0
    if p["kills"] >= 12 and hs_pct >= 75:
        comp["Headshot % anormal"] = 10
    elif p["kills"] >= 12 and hs_pct >= 65:
        comp["Headshot % anormal"] = 6
    else:
        comp["Headshot % anormal"] = 0

    prec = 100.0 * p["acertos"] / p["tiros"] if p["tiros"] else 0.0
    cabeca = 100.0 * p["acertos_cabeca"] / p["acertos"] if p["acertos"] else 0.0
    comp["Precisão anormal"] = 8 if (p["tiros"] >= 40 and prec >= 50) else 0
    comp["Acertos na cabeça anormais"] = 8 if (p["acertos"] >= 25 and cabeca >= 40) else 0

    comp = {k: v for k, v in comp.items() if v > 0}
    return min(100, sum(comp.values())), comp


def classificar(score):
    if score >= 55:
        return "ALTO", "alto", "🔴"
    if score >= 30:
        return "MÉDIO", "medio", "🟠"
    if score >= 12:
        return "LEVE", "leve", "🟡"
    return "normal", "normal", "🟢"


# ---------------------------------------------------------------------------
# Histórico entre partidas
# ---------------------------------------------------------------------------

def salvar_historico(hist):
    with open(ARQ_HISTORICO, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)


def atualizar_historico(jogadores, meta):
    hist = {}
    if os.path.exists(ARQ_HISTORICO):
        try:
            with open(ARQ_HISTORICO, encoding="utf-8") as f:
                hist = json.load(f)
        except Exception:
            hist = {}

    hoje = datetime.date.today().isoformat()
    for sid, p in jogadores.items():
        score, _ = pontuar(p)
        registro = hist.setdefault(sid, {"nome": p["nome"], "partidas": {}})
        registro["nome"] = p["nome"]
        registro["partidas"][meta["arquivo"]] = {"score": score, "data": hoje,
                                                 "mapa": meta["mapa"]}

    salvar_historico(hist)
    return hist


def enriquecer_com_steam(hist, sids):
    """Consulta bans/idade/nível dos jogadores desta partida na Steam.
    Falha em silêncio se estiver sem internet."""
    try:
        import steam_info
        cfg = steam_info.carregar_config()
        chave = cfg.get("steam_api_key") or None
        fonte = "API oficial" if chave else "perfis públicos (sem chave de API)"
        print(f"  Consultando Steam ({fonte})...")
        dados = steam_info.consultar_jogadores(sids, chave)
        for sid, d in dados.items():
            if sid in hist:
                hist[sid]["steam"] = {**hist[sid].get("steam", {}), **d}
        salvar_historico(hist)
    except Exception as e:
        print(f"  (consulta à Steam falhou: {e} — relatório sai sem contexto de conta)")
    return hist


# ---------------------------------------------------------------------------
# Relatório HTML
# ---------------------------------------------------------------------------

CSS = """
:root {
  color-scheme: dark;
  --pagina:#0d0d0d; --superficie:#1a1a19; --superficie2:#222221;
  --ink:#ffffff; --ink2:#c3c2b7; --mudo:#898781;
  --hairline:#2c2c2a; --borda:rgba(255,255,255,.10);
  --bom:#0ca30c; --atencao:#fab219; --serio:#ec835a; --critico:#d03b3b;
}
@media (prefers-color-scheme: light) {
  :root {
    color-scheme: light;
    --pagina:#f9f9f7; --superficie:#fcfcfb; --superficie2:#f0efec;
    --ink:#0b0b0b; --ink2:#52514e; --mudo:#898781;
    --hairline:#e1e0d9; --borda:rgba(11,11,11,.10);
  }
}
* { box-sizing:border-box; margin:0; }
body { background:var(--pagina); color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif; padding:32px 16px; }
.wrap { max-width:1020px; margin:0 auto; }
h1 { font-size:1.45rem; }
.sub { color:var(--mudo); margin:4px 0 24px; }
.aviso { background:var(--superficie); border:1px solid var(--borda);
  border-left:3px solid var(--atencao); padding:12px 16px; border-radius:8px;
  margin-bottom:24px; color:var(--ink2); }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
  gap:12px; margin-bottom:28px; }
.tile { background:var(--superficie); border:1px solid var(--borda);
  border-radius:10px; padding:14px 16px; }
.tile .rotulo { font-size:12px; color:var(--mudo); }
.tile .valor { font-size:1.7rem; font-weight:600; }
.card { background:var(--superficie); border:1px solid var(--borda);
  border-radius:10px; margin-bottom:10px; }
.card summary { display:flex; align-items:center; gap:14px; padding:14px 16px;
  cursor:pointer; list-style:none; flex-wrap:wrap; }
.card summary::-webkit-details-marker { display:none; }
.nome { font-weight:600; min-width:150px; }
.nome a { color:inherit; text-decoration:none; border-bottom:1px dotted var(--mudo); }
.badge { font-size:12px; font-weight:600; color:var(--ink2);
  display:inline-flex; align-items:center; gap:6px; min-width:86px; }
.medidor { flex:1; min-width:140px; height:8px; border-radius:99px;
  overflow:hidden; }
.medidor > div { height:100%; border-radius:99px; }
.m-alto   { background:rgba(208,59,59,.22); }   .m-alto > div   { background:var(--critico); }
.m-medio  { background:rgba(236,131,90,.22); }  .m-medio > div  { background:var(--serio); }
.m-leve   { background:rgba(250,178,25,.22); }  .m-leve > div   { background:var(--atencao); }
.m-normal { background:rgba(12,163,12,.22); }   .m-normal > div { background:var(--bom); }
.score { font-weight:600; font-variant-numeric:tabular-nums; width:64px;
  text-align:right; color:var(--ink2); }
.det { padding:4px 16px 16px; border-top:1px solid var(--hairline); }
.det h3 { font-size:13px; color:var(--mudo); text-transform:uppercase;
  letter-spacing:.05em; margin:14px 0 8px; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:8px; }
.stats div { background:var(--superficie2); border-radius:8px; padding:8px 10px;
  font-size:13px; color:var(--ink2); }
.stats b { display:block; color:var(--ink); font-size:15px; }
.tabela-scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:13.5px; }
th, td { padding:7px 10px; text-align:left; white-space:nowrap; }
th { color:var(--mudo); font-weight:600; border-bottom:1px solid var(--hairline);
  font-size:11px; text-transform:uppercase; letter-spacing:.05em; }
tr + tr td { border-top:1px solid var(--hairline); }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
code { background:var(--superficie2); padding:2px 7px; border-radius:6px;
  font-size:12.5px; }
.chips { display:flex; gap:6px; flex-wrap:wrap; margin:12px 0 2px; }
.chip { font-size:12px; padding:3px 10px; border-radius:99px;
  background:var(--superficie2); color:var(--ink2); border:1px solid var(--borda); }
.chip-ban { background:rgba(208,59,59,.18); color:var(--critico);
  border-color:transparent; font-weight:600; }
.chip-alerta { background:rgba(250,178,25,.16); color:var(--atencao);
  border-color:transparent; }
.links-jogador { color:var(--mudo); font-size:13px; margin-top:12px; }
.radar-fig { margin:8px 0 0; }
.radar { width:100%; max-width:440px; display:block; border-radius:10px;
  background:#0a0a0a; }
.radar-fig figcaption { color:var(--mudo); font-size:12.5px; margin-top:6px;
  max-width:440px; }
.secao { margin-top:36px; }
.secao h2 { font-size:1.1rem; margin-bottom:10px; }
.secao ol, .secao ul { padding-left:22px; color:var(--ink2); }
.secao li { margin-bottom:6px; }
a { color:var(--ink2); }
.desc-momento { white-space:normal; max-width:340px; }
"""

ICONES = {"FLICK": "⚡", "REAÇÃO": "⏱️", "TRACK": "🧲", "TRACK-PAREDE": "🚨",
          "TRACK-INFO": "🔊", "TRACK-VIU": "👀", "SMOKE": "💨",
          "SMOKE-COMUM": "🌫️", "PAREDE": "🧱", "CEGO": "🫣"}


def svg_radar(radar, momentos):
    """Mini-mapa com a posição de atacante→vítima em cada momento suspeito."""
    if not radar:
        return ""
    niveis = {}
    for m in momentos:
        if not m.get("apos") or not m.get("vpos"):
            continue
        baixo = (radar.get("lower_max") is not None and radar.get("img_lower")
                 and len(m["apos"]) > 2 and m["apos"][2] < radar["lower_max"])
        niveis.setdefault("baixo" if baixo else "cima", []).append(m)

    def cor(peso):
        if peso >= 6:
            return "#d03b3b"
        if peso >= 4:
            return "#ec835a"
        return "#fab219"

    def transf(p):
        return ((p[0] - radar["pos_x"]) / radar["scale"],
                (radar["pos_y"] - p[1]) / radar["scale"])

    blocos = []
    for nivel, moms in sorted(niveis.items()):
        img = radar["img_lower"] if nivel == "baixo" else radar["img"]
        marcas = []
        for m in moms[:20]:
            ax, ay = transf(m["apos"])
            vx, vy = transf(m["vpos"])
            rotulo = html.escape(f"R{m['round']} {m['tipo']} vs {m['vitima']}")
            marcas.append(f"""
      <g><title>{rotulo}</title>
        <line x1="{ax:.0f}" y1="{ay:.0f}" x2="{vx:.0f}" y2="{vy:.0f}"
          stroke="#ffffff" stroke-opacity=".55" stroke-width="3"/>
        <circle cx="{vx:.0f}" cy="{vy:.0f}" r="9" fill="#ffffff"
          fill-opacity=".9"/>
        <circle cx="{ax:.0f}" cy="{ay:.0f}" r="12" fill="{cor(m['peso'])}"
          stroke="#1a1a19" stroke-width="3"/>
      </g>""")
        titulo = " (andar de baixo)" if nivel == "baixo" else ""
        blocos.append(f"""
    <figure class="radar-fig">
      <svg class="radar" viewBox="0 0 1024 1024" role="img"
        aria-label="Radar dos momentos suspeitos{titulo}">
        <image href="{img}" width="1024" height="1024"/>
        {''.join(marcas)}
      </svg>
      <figcaption>Radar{titulo} — bolinha colorida = suspeito
        (🔴 sinal forte, 🟠 médio, 🟡 leve) · bolinha branca = vítima ·
        passe o mouse para ver o lance</figcaption>
    </figure>""")

    if not blocos:
        return ""
    return "<h3>Onde aconteceu</h3>" + "".join(blocos)


def gerar_html(jogadores, meta, hist):
    ordenados = sorted(jogadores.items(), key=lambda kv: pontuar(kv[1])[0],
                       reverse=True)
    total_kills = sum(p["kills"] for _, p in ordenados)
    total_momentos = sum(len(p["momentos"]) for _, p in ordenados)
    n_suspeitos = sum(1 for _, p in ordenados if pontuar(p)[0] >= 30)

    cards = []
    for sid, p in ordenados:
        if p["kills"] == 0 and p["mortes"] == 0:
            continue
        score, comp = pontuar(p)
        rotulo, classe, icone = classificar(score)
        hs_pct = 100.0 * p["hs"] / p["kills"] if p["kills"] else 0.0
        prec = 100.0 * p["acertos"] / p["tiros"] if p["tiros"] else 0.0
        cabeca = 100.0 * p["acertos_cabeca"] / p["acertos"] if p["acertos"] else 0.0
        perfil = f"https://steamcommunity.com/profiles/{sid}"

        n_partidas = len(hist.get(sid, {}).get("partidas", {}))
        scores_hist = [v["score"] for v in
                       hist.get(sid, {}).get("partidas", {}).values()]
        media_hist = sum(scores_hist) / len(scores_hist) if scores_hist else 0

        linhas_comp = "".join(
            f"<tr><td>{html.escape(k)}</td><td class='num'>+{v}</td></tr>"
            for k, v in sorted(comp.items(), key=lambda kv: -kv[1]))

        momentos = sorted(p["momentos"], key=lambda m: -m["peso"])[:30]
        linhas_mom = "".join(
            f"<tr><td>{ICONES.get(m['tipo'], '•')} {m['tipo']}</td>"
            f"<td class='num'>{m['round']}</td>"
            f"<td>{html.escape(str(m['vitima']))}</td>"
            f"<td>{html.escape(m['arma'])}</td>"
            f"<td class='desc-momento'>{html.escape(m['desc'])}</td>"
            f"<td><code>demo_gototick {max(0, m['tick'] - 320)}</code></td></tr>"
            for m in momentos)

        detalhe_momentos = f"""
        <h3>Momentos suspeitos ({len(p['momentos'])})</h3>
        <div class="tabela-scroll"><table>
        <tr><th>Sinal</th><th class="num">Round</th><th>Vítima</th><th>Arma</th>
            <th>O que aconteceu</th><th>Pular na demo (console)</th></tr>
        {linhas_mom}</table></div>""" if momentos else \
            "<p style='color:var(--mudo);margin-top:12px'>Nenhum momento suspeito registrado.</p>"

        detalhe_comp = f"""
        <h3>De onde vem o score</h3>
        <div class="tabela-scroll"><table>
        <tr><th>Componente</th><th class="num">Pontos</th></tr>
        {linhas_comp}</table></div>""" if comp else ""

        hist_txt = (f" · visto em {n_partidas} partida(s) analisada(s), "
                    f"score médio {media_hist:.0f}") if n_partidas > 1 else ""

        # chips de contexto de conta (Fase A)
        st = hist.get(sid, {}).get("steam", {})
        chips = []
        if st.get("vac"):
            n_vac = st.get("n_vac") or 1
            chips.append(("chip-ban", f"☠ JÁ TEM VAC BAN ({n_vac}x)"))
        if int(st.get("bans_jogo", 0) or 0) > 0:
            chips.append(("chip-ban", f"☠ ban de jogo ({st['bans_jogo']}x)"))
        if st.get("ban_troca"):
            chips.append(("chip-ban", "☠ banido de trocas"))
        idade = None
        if st.get("conta_criada"):
            try:
                criada = datetime.date.fromisoformat(st["conta_criada"])
                idade = (datetime.date.today() - criada).days / 365.25
            except ValueError:
                pass
        if idade is not None and idade < 1.0:
            chips.append(("chip-alerta", "🐣 conta com menos de 1 ano"))
        elif st.get("conta_criada"):
            chips.append(("chip", f"conta desde {st['conta_criada'][:4]}"))
        if st.get("privado"):
            chips.append(("chip-alerta", "🔒 perfil privado"))
        if st.get("conta_limitada"):
            chips.append(("chip-alerta", "conta limitada"))
        if st.get("nivel") is not None:
            chips.append(("chip", f"nível Steam {st['nivel']}"))
        if st.get("horas_cs2") is not None:
            chips.append(("chip", f"{st['horas_cs2']} h de CS2"))
        chips_html = ""
        if chips:
            chips_html = "<div class='chips'>" + "".join(
                f"<span class='chip {c}'>{html.escape(t)}</span>"
                for c, t in chips) + "</div>"

        cards.append(f"""
<details class="card"{' open' if score >= 30 else ''}>
  <summary>
    <span class="nome"><a href="{perfil}" target="_blank"
      title="Abrir perfil Steam">{html.escape(str(p['nome']))}</a></span>
    <span class="badge">{icone} {rotulo}</span>
    <span class="medidor m-{classe}"><div style="width:{score}%"></div></span>
    <span class="score">{score}/100</span>
  </summary>
  <div class="det">
    <h3>Estatísticas</h3>
    <div class="stats">
      <div><b>{p['kills']} / {p['mortes']}</b>kills / mortes</div>
      <div><b>{hs_pct:.0f}%</b>headshot (kills)</div>
      <div><b>{prec:.0f}%</b>tiros que acertam</div>
      <div><b>{cabeca:.0f}%</b>acertos na cabeça</div>
      <div><b>{p['flicks']}</b>flicks sobre-humanos</div>
      <div><b>{p['tracks_parede']}</b>trackings por parede</div>
      <div><b>{p['tracks']}</b>trackings pré-confronto</div>
      <div><b>{p['smoke']}</b>kills por smoke</div>
      <div><b>{p['wallbang']}</b>wallbangs</div>
    </div>
    {chips_html}
    {detalhe_comp}
    {detalhe_momentos}
    {svg_radar(meta.get('radar'), p['momentos'])}
    <p class="links-jogador">
      SteamID: {sid}{hist_txt} ·
      <a href="{perfil}" target="_blank">perfil Steam ↗</a> ·
      <a href="https://csstats.gg/player/{sid}" target="_blank">csstats.gg ↗</a> ·
      <a href="https://leetify.com/app/profile/{sid}" target="_blank">Leetify ↗</a></p>
  </div>
</details>""")

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório de suspeitos — CS2</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>🔍 Relatório de suspeitos — v5</h1>
<p class="sub">{html.escape(meta['arquivo'])} · mapa {html.escape(meta['mapa'])}
 · {meta['rounds']} rounds</p>

<div class="aviso"><strong>Leia antes de denunciar:</strong> nenhum detector por
demo é infalível — nem este. Os sinais abaixo são <em>fortes indícios</em>, e os
mais confiáveis são ⚡ flicks, 🧲 tracking e 💨 kills por smoke repetidos.
Um smurf muito bom pode gerar alerta LEVE ou até MÉDIO. Use o comando
<code>demo_gototick</code> no console durante o replay para assistir cada momento
com seus próprios olhos (a demo pula pra ~5 s antes do lance).</div>

<div class="tiles">
  <div class="tile"><div class="rotulo">Jogadores analisados</div>
    <div class="valor">{len(ordenados)}</div></div>
  <div class="tile"><div class="rotulo">Kills analisadas tick a tick</div>
    <div class="valor">{total_kills}</div></div>
  <div class="tile"><div class="rotulo">Momentos suspeitos</div>
    <div class="valor">{total_momentos}</div></div>
  <div class="tile"><div class="rotulo">Suspeitos (médio ou alto)</div>
    <div class="valor">{n_suspeitos}</div></div>
</div>

{''.join(cards)}

<div class="secao">
<h2>Como conferir e denunciar (Premier)</h2>
<ol>
<li><strong>Assista primeiro:</strong> CS2 → <em>Assistir → Suas Partidas</em> →
  dê play na demo. Abra o console (tecla ') e cole o comando
  <code>demo_gototick ...</code> do momento suspeito. Espectate na visão do
  suspeito e ligue o X-ray.</li>
<li><strong>Denuncie no jogo:</strong> placar (Tab) → clique no jogador →
  <em>Denunciar</em> → marque mira automática e/ou visão através de paredes.
  Esse report alimenta o VACnet.</li>
<li><strong>Denuncie na Steam:</strong> o nome de cada jogador acima linka o
  perfil → <em>Mais → Denunciar violação</em>.</li>
</ol>
</div>

<div class="secao">
<h2>Metodologia e limites</h2>
<ul>
<li><strong>⚡ Flick sobre-humano:</strong> giro de ≥{FLICK_MIN_GRAUS:.0f}° nos
  últimos 125 ms terminando em headshot com ≤{FLICK_REACAO_MAX * 15.6:.0f} ms de
  mira no alvo. Humanos até fazem flicks grandes, mas não param cirurgicamente
  na cabeça de forma repetida.</li>
<li><strong>⏱️ Reação inumana:</strong> mira chega no alvo e mata em
  ≤{REACAO_RAPIDA_MAX * 15.6:.0f} ms após um giro real. Reação humana média em
  jogo é 150–250 ms.</li>
<li><strong>🧲 Tracking:</strong> mira colada (≤{NO_ALVO_GRAUS:.0f}°) num alvo em
  movimento por ≥1,5 s antes da kill — e a mira precisa ter realmente GIRADO
  acompanhando o alvo (≥{TRACK_MIN_GIRO:.0f}°): segurar ângulo parado não conta.
  Se a vítima atirou nos 5 s anteriores (posição revelada pelo som), vira 🔊 e
  não pontua.</li>
<li><strong>🚨 Tracking através de parede:</strong> o mesmo tracking, mas checado
  contra a geometria real do mapa: em ≥70% do tempo havia parede entre o suspeito
  e o alvo. Repetido em VÍTIMAS DIFERENTES, é o sinal mais próximo de prova de
  wallhack que uma demo permite (repetição na mesma vítima não conta — vítima
  previsível dispara o sinal em vários atacantes). Uma ocorrência isolada pode
  ser rastreio legítimo pelo SOM. Não pontua se o atacante viu o alvo segundos
  antes (👀 última posição conhecida) ou se a vítima atirou/jogou granada
  (🔊 posição revelada). (Smoke não é parede — kills por smoke são o 💨.)</li>
<li><strong>💨 Kill por smoke:</strong> só pontua se foi tiro PRECISO (≤4 tiros
  em 2 s) a ≥7 m — spammar posição conhecida através da fumaça é jogada normal
  e aparece como 🌫️ sem pontuar. Filtro calibrado com feedback de jogador
  real flagrado injustamente.</li>
<li><strong>Precisão:</strong> % de tiros que acertam (típico: 15–35%) e % de
  acertos na cabeça (típico: 15–25%). Granadas e faca não contam.</li>
<li><strong>Limites:</strong> demos gravam a 64 ticks/s com interpolação — lances
  isolados podem enganar; por isso o score pesa <em>repetição</em>. Latência e
  peek advantage também distorcem lances individuais.</li>
</ul>
</div>
</div></body></html>"""


# ---------------------------------------------------------------------------

def main():
    demos = encontrar_demos()
    ultimo_relatorio = None

    for caminho in demos:
        jogadores, meta = analisar_demo(caminho)
        if not jogadores:
            print("  Não consegui extrair dados dessa demo.")
            continue

        hist = atualizar_historico(jogadores, meta)
        hist = enriquecer_com_steam(hist, list(jogadores))

        nome_rel = "relatorio.html" if len(demos) == 1 else \
            f"relatorio_{os.path.splitext(meta['arquivo'])[0]}.html"
        saida = os.path.join(PASTA, nome_rel)
        with open(saida, "w", encoding="utf-8") as f:
            f.write(gerar_html(jogadores, meta, hist))
        ultimo_relatorio = saida

        print(f"\n  Mapa {meta['mapa']} · {meta['rounds']} rounds · "
              f"{len(jogadores)} jogadores")
        for sid, p in sorted(jogadores.items(),
                             key=lambda kv: pontuar(kv[1])[0], reverse=True):
            score, comp = pontuar(p)
            rotulo, _, icone = classificar(score)
            if score > 0:
                principais = ", ".join(sorted(comp, key=comp.get, reverse=True)[:3])
                print(f"  {icone} [{rotulo:>6} {score:>3}/100] {p['nome']}: "
                      f"{principais}")
        print(f"  Relatório: {saida}")

    if ultimo_relatorio:
        webbrowser.open(f"file:///{ultimo_relatorio}")


if __name__ == "__main__":
    main()
