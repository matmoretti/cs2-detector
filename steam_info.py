# -*- coding: utf-8 -*-
"""
Consulta dados públicos da Steam para os jogadores analisados:
bans (VAC / de jogo), idade da conta, nível, horas de CS2, privacidade.

Com chave de API (config.json -> steam_api_key): usa a API oficial (mais campos).
Sem chave: usa o perfil público em XML (menos campos, mas já pega VAC ban).
Chave grátis em https://steamcommunity.com/dev/apikey (domínio: localhost).
"""

import json
import os
import re
import time
import datetime
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_CONFIG = os.path.join(PASTA, "config.json")
CABECALHOS = {"User-Agent": "Mozilla/5.0 (cs2-detector; uso pessoal)"}
APP_CS2 = 730


def carregar_config():
    if os.path.exists(ARQ_CONFIG):
        try:
            with open(ARQ_CONFIG, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    cfg = {"steam_api_key": ""}
    with open(ARQ_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    return cfg


def _json(url):
    req = urllib.request.Request(url, headers=CABECALHOS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _texto(url):
    req = urllib.request.Request(url, headers=CABECALHOS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# API oficial (com chave)
# ---------------------------------------------------------------------------

def _api_bans(chave, sids):
    saida = {}
    for i in range(0, len(sids), 100):
        lote = sids[i:i + 100]
        url = ("https://api.steampowered.com/ISteamUser/GetPlayerBans/v1/?"
               + urllib.parse.urlencode({"key": chave,
                                         "steamids": ",".join(lote)}))
        for p in _json(url).get("players", []):
            saida[str(p["SteamId"])] = {
                "vac": bool(p.get("VACBanned")),
                "n_vac": int(p.get("NumberOfVACBans", 0)),
                "bans_jogo": int(p.get("NumberOfGameBans", 0)),
                "dias_desde_ban": int(p.get("DaysSinceLastBan", 0)),
            }
    return saida


def _api_perfis(chave, sids):
    saida = {}
    for i in range(0, len(sids), 100):
        lote = sids[i:i + 100]
        url = ("https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?"
               + urllib.parse.urlencode({"key": chave,
                                         "steamids": ",".join(lote)}))
        for p in _json(url).get("response", {}).get("players", []):
            criada = p.get("timecreated")
            saida[str(p["steamid"])] = {
                "nome": p.get("personaname"),
                "privado": p.get("communityvisibilitystate") != 3,
                "conta_criada": (datetime.date.fromtimestamp(criada).isoformat()
                                 if criada else None),
            }
    return saida


def _api_nivel(chave, sid):
    url = ("https://api.steampowered.com/IPlayerService/GetSteamLevel/v1/?"
           + urllib.parse.urlencode({"key": chave, "steamid": sid}))
    return _json(url).get("response", {}).get("player_level")


def _api_horas_cs2(chave, sid):
    url = ("https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?"
           + urllib.parse.urlencode({
               "key": chave, "steamid": sid,
               "include_played_free_games": 1,
               "appids_filter[0]": APP_CS2}))
    for jogo in _json(url).get("response", {}).get("games", []):
        if jogo.get("appid") == APP_CS2:
            return round(jogo.get("playtime_forever", 0) / 60)
    return None


# ---------------------------------------------------------------------------
# Fallback sem chave: perfil público em XML
# ---------------------------------------------------------------------------

def _xml_perfil(sid):
    url = f"https://steamcommunity.com/profiles/{sid}?xml=1"
    raiz = ET.fromstring(_texto(url).encode("utf-8"))
    if raiz.tag == "response":  # perfil inexistente/deletado
        return None

    def campo(nome):
        el = raiz.find(nome)
        return el.text if el is not None else None

    membro = campo("memberSince")
    ano = None
    if membro:
        m = re.search(r"(\d{4})", membro)
        ano = int(m.group(1)) if m else None

    return {
        "nome": campo("steamID"),
        "vac": campo("vacBanned") == "1",
        "ban_troca": (campo("tradeBanState") or "None") != "None",
        "conta_limitada": campo("isLimitedAccount") == "1",
        "privado": (campo("privacyState") or "") != "public",
        "conta_criada": f"{ano}-01-01" if ano else None,
        "membro_desde": membro,
    }


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

def consultar_jogadores(sids, chave=None, atraso=0.4, detalhes=True):
    """Retorna {sid: dados}. Nunca lança exceção por jogador individual."""
    sids = [str(s) for s in sids]
    hoje = datetime.date.today().isoformat()
    saida = {}

    if chave:
        try:
            bans = _api_bans(chave, sids)
            perfis = _api_perfis(chave, sids)
        except Exception as e:
            print(f"  [steam] API oficial falhou ({e}); usando fallback público.")
            chave = None

    if chave:
        for sid in sids:
            d = {"checado_em": hoje, "fonte": "api"}
            d.update(bans.get(sid, {}))
            d.update(perfis.get(sid, {}))
            if detalhes:
                try:
                    d["nivel"] = _api_nivel(chave, sid)
                    time.sleep(atraso)
                    d["horas_cs2"] = _api_horas_cs2(chave, sid)
                    time.sleep(atraso)
                except Exception:
                    pass
            saida[sid] = d
        return saida

    for sid in sids:
        try:
            d = _xml_perfil(sid)
            if d is None:
                d = {"perfil_inexistente": True}
            d.update({"checado_em": hoje, "fonte": "xml"})
            saida[sid] = d
        except Exception as e:
            saida[sid] = {"erro": str(e), "checado_em": hoje, "fonte": "xml"}
        time.sleep(atraso)
    return saida


def idade_conta_anos(dados):
    criada = (dados or {}).get("conta_criada")
    if not criada:
        return None
    try:
        d = datetime.date.fromisoformat(criada)
        return (datetime.date.today() - d).days / 365.25
    except ValueError:
        return None
