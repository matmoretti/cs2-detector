# -*- coding: utf-8 -*-
r"""
Contrato de evidência forense — Fase D0 do ROADMAP / M0 da ARQUITETURA-ML
========================================================================
Transforma cada lance suspeito (ou descartado) em um **episódio** versionado
e reproduzível: um registro que carrega, além do veredito da regra, todo o
contexto que justifica incluir ou excluir a suspeita.

Princípio (do contrato de dados forense da ARQUITETURA-ML):

  * toda fonte de informação legítima INDISPONÍVEL é gravada como
    ``desconhecido`` COM a razão da indisponibilidade — nunca como ``não``.
    "Sem evidência de call" não é "não houve call".
  * o episódio precisa poder ser reproduzido e explicado só pelos dados
    gravados: origem (que regra o abriu), janela temporal e valores ausentes.
  * ban, perfil Steam e score histórico NÃO entram como contexto do episódio
    comportamental — ficam separados (evita que o modelo aprenda atalhos).

Este módulo NÃO altera pontuação nem acusa ninguém: só materializa o que o
`analisar.py` já observa, num formato estável (JSONL) para calibração (D0.3),
revisão humana e, no futuro, treino de ML.
"""

import os
import json
import hashlib
import datetime

# Versões que tornam um episódio reproduzível. Suba a de features/regras
# sempre que a semântica de um campo mudar — o dataset guarda com qual versão
# cada linha foi gerada.
SCHEMA_VERSAO = "d0.1"      # formato do registro de episódio (este arquivo)
VERSAO_FEATURES = "d0.6"    # semântica dos campos de contexto/geometria/mira
VERSAO_REGRAS = "v6.12"     # versão do detector que emitiu a saída por regra

PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_DADOS = os.path.join(PASTA, "dados")
ARQ_EPISODIOS = os.path.join(PASTA_DADOS, "episodios.jsonl")
ARQ_SALT = os.path.join(PASTA_DADOS, ".salt")
ARQ_MAPA_JOGADORES = os.path.join(PASTA_DADOS, "mapa_jogadores.json")

# Razões padrão para fontes que a demo ainda não expõe de forma confiável.
# Ficam explícitas no episódio para que a incerteza seja auditável.
RAZAO_SPOTTED = "estado 'spotted'/radar por teammate ainda não extraído do demoparser2 (pendente D1.1)"
RAZAO_CALL = "voz/Discord não é observável na demo (limite declarado da fonte)"
RAZAO_SEM_GEOMETRIA = "geometria do mapa (awpy .tri) indisponível nesta análise"


# ---------------------------------------------------------------------------
# Helpers do padrão "valor + razão" (o contrato nunca usa None mudo p/ fonte
# que existe mas não foi extraída)
# ---------------------------------------------------------------------------

def conhecido(valor):
    """Fonte observada: valor presente, sem razão de ausência."""
    return {"valor": valor, "razao": None}


def desconhecido(razao):
    """Fonte não observável/não extraída: valor ausente COM justificativa."""
    return {"valor": "desconhecido", "razao": razao}


def tri_estado(flag, razao_ausente):
    """Mapeia um bool-ou-None para o vocabulário de contraprova.

    True -> 'sim', False -> 'nao', None -> desconhecido(razão).
    Use para contraprovas que só existem quando havia dado (ex.: geometria).
    """
    if flag is None:
        return desconhecido(razao_ausente)
    return conhecido("sim" if flag else "nao")


# ---------------------------------------------------------------------------
# Identidade e reprodutibilidade
# ---------------------------------------------------------------------------

def versao_demoparser():
    """String de versão do demoparser2 para o campo de reprodutibilidade."""
    try:
        from importlib.metadata import version
        return "demoparser2 " + version("demoparser2")
    except Exception:
        return "demoparser2 ?"


def hash_demo(caminho):
    """SHA-256 do arquivo .dem (lido em blocos — demos têm centenas de MB)."""
    h = hashlib.sha256()
    try:
        with open(caminho, "rb") as f:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
        return h.hexdigest()
    except OSError:
        return "?"


def episode_id(demo_hash, tick, a_sid, v_sid, tipo):
    """Id estável e determinístico de um episódio.

    Não depende do salt de pseudonimização: reanalisar a mesma demo produz
    exatamente os mesmos ids (permite dedup no dataset).
    """
    chave = f"{demo_hash}:{tick}:{a_sid}:{v_sid}:{tipo}"
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()[:16]


def _carregar_salt():
    """Salt local persistente para pseudonimizar SteamIDs.

    Gerado uma única vez e reutilizado, para que o pseudônimo de um jogador
    seja estável entre demos. Fica fora do Git (pasta dados/).
    """
    os.makedirs(PASTA_DADOS, exist_ok=True)
    if os.path.exists(ARQ_SALT):
        with open(ARQ_SALT, "rb") as f:
            s = f.read().strip()
            if s:
                return s
    s = os.urandom(16).hex().encode("ascii")
    with open(ARQ_SALT, "wb") as f:
        f.write(s)
    return s


_SALT = None


def pseudonimizar(sid):
    """Hash curto e estável de um SteamID (não reversível sem o mapa local).

    O contrato pede atacante/vítima pseudonimizados no dataset. O mapa reverso
    fica só na máquina do autor (mapa_jogadores.json, fora do Git) para permitir
    investigar um caso — pseudonimização reduz exposição, não é anonimização.
    """
    global _SALT
    if _SALT is None:
        _SALT = _carregar_salt()
    return hashlib.sha256(_SALT + str(sid).encode("utf-8")).hexdigest()[:16]


def registrar_jogadores(jogadores):
    """Atualiza o mapa local pseudônimo -> {sid, nome} (fora do Git).

    `jogadores` = dict {sid: {"nome": ...}} da análise. Idempotente.
    """
    os.makedirs(PASTA_DADOS, exist_ok=True)
    mapa = {}
    if os.path.exists(ARQ_MAPA_JOGADORES):
        try:
            with open(ARQ_MAPA_JOGADORES, encoding="utf-8") as f:
                mapa = json.load(f)
        except (OSError, ValueError):
            mapa = {}
    for sid, p in jogadores.items():
        mapa[pseudonimizar(sid)] = {"sid": str(sid), "nome": p.get("nome", "?")}
    with open(ARQ_MAPA_JOGADORES, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# Montagem do episódio a partir de um "momento" do analisar.py
# ---------------------------------------------------------------------------

def montar_episodio(mom, meta):
    """Constrói o registro de contrato completo de um momento.

    `mom` é o dict acumulado pelo analisar.py; espera-se em `mom["ctx"]` um
    dicionário com os observáveis já calculados (ausentes viram desconhecido):

        distancia_m, distancia_us, smoke (bool), velocidade_alvo_us,
        oclusao_frac, mudanca_angular_alvo_deg, desvio_min_deg, giro_mira_deg,
        duracao_s, viu_antes (bool|None), barulho_recente (bool|None),
        idade_ultima_visao_s (float|None), classe ('candidato'|'descartado'|'ambiguo')

    `meta` traz os dados da demo: demo_hash, arquivo, mapa, tickrate, tem_geometria.
    """
    ctx = mom.get("ctx", {}) or {}
    tipo = mom["tipo"]
    a_sid, v_sid = mom.get("a_sid"), mom.get("v_sid")
    tick = mom["tick"]
    tem_geo = meta.get("tem_geometria", False)
    razao_geo = None if tem_geo else RAZAO_SEM_GEOMETRIA

    return {
        "schema_versao": SCHEMA_VERSAO,
        "episode_id": episode_id(meta["demo_hash"], tick, a_sid, v_sid, tipo),

        "identidade": {
            "demo_hash": meta["demo_hash"],
            "demo_arquivo": meta.get("arquivo"),
            "mapa": meta.get("mapa"),
            "round": mom.get("round"),
            "tick": tick,
            "atacante_id": pseudonimizar(a_sid) if a_sid is not None else None,
            "vitima_id": pseudonimizar(v_sid) if v_sid is not None else None,
            "candidate_source": tipo,   # regra/evento que abriu o episódio
        },

        "tempo": {
            "t_decisao": tick,
            "janela_contexto_ini": ctx.get("janela_contexto_ini"),
            "janela_forense_ini": ctx.get("janela_forense_ini"),
            "janela_forense_fim": tick,
            "tickrate": meta.get("tickrate", 64),
            "data_analise": datetime.date.today().isoformat(),
        },

        "versoes": {
            "parser": meta.get("versao_parser", "?"),
            "features": VERSAO_FEATURES,
            "regras": VERSAO_REGRAS,
            "geometria": "awpy-tris" if tem_geo else "indisponivel",
        },

        "contexto": {
            "arma": mom.get("arma"),
            "distancia_m": ctx.get("distancia_m"),
            "smoke": bool(ctx.get("smoke", False)),
            "velocidade_alvo_us": ctx.get("velocidade_alvo_us"),
            # calibração futura: a 1ª revisão humana refutou exclusão por
            # timing (confirmado aos 9,2 s vs refutado aos 4,8 s)
            "segundos_no_round": ctx.get("segundos_no_round"),
            # D3.2: spam (vários tiros) vs tiro único no lance
            "tiros_2s": ctx.get("tiros_2s"),
            # D3.3 (v6.12): smoke real na LOS — idade importa (dissipando =
            # possível visão parcial legítima; thrusmoke não distingue)
            "idade_smoke_s": ctx.get("idade_smoke_s"),
            "tempo_restante_smoke_s": ctx.get("tempo_restante_smoke_s"),
            "dist_smoke_los_us": ctx.get("dist_smoke_los_us"),
            "idade_ultima_visao_s": (
                conhecido(ctx["idade_ultima_visao_s"])
                if ctx.get("idade_ultima_visao_s") is not None
                else desconhecido(razao_geo or "sem linha de visão direta registrada na janela")
            ),
            "objetivo_clutch": desconhecido(
                "estado de objetivo/clutch ainda não extraído (pendente D4.1)"),
        },

        "geometria": {
            "oclusao_frac": (
                conhecido(ctx["oclusao_frac"]) if ctx.get("oclusao_frac") is not None
                else desconhecido(razao_geo or "oclusão não aplicável a este sinal")
            ),
            "mudanca_angular_alvo_deg": ctx.get("mudanca_angular_alvo_deg"),
            "distancia_us": ctx.get("distancia_us"),
        },

        "mira": {
            "desvio_min_deg": ctx.get("desvio_min_deg"),
            "giro_mira_deg": ctx.get("giro_mira_deg"),
            "duracao_s": ctx.get("duracao_s"),
            # reação pós-LOS (v6.9): tempo LOS-abrir→tiro e desvio na abertura
            "reacao_pos_los_ms": ctx.get("reacao_pos_los_ms"),
            "desvio_abertura_deg": ctx.get("desvio_abertura_deg"),
            # D3.2 (v6.10): correção da mira no alvo oculto antes do wallbang
            "ajuste_oculto_deg": ctx.get("ajuste_oculto_deg"),
            # D2.1 (v6.11): a mira seguiu o alvo? corr das variações angulares
            "correlacao_mira_alvo": ctx.get("correlacao_mira_alvo"),
            "correlacao_max": ctx.get("correlacao_max"),
            "defasagem_ms": ctx.get("defasagem_ms"),
        },

        # Contraprovas: informação legítima que poderia explicar a suspeita.
        # Ausência de dado vira 'desconhecido' com razão — nunca 'nao'.
        "contraprovas": {
            "visao_recente": tri_estado(
                ctx.get("viu_antes"),
                razao_geo or "sem checagem de linha de visão anterior neste sinal"),
            "barulho_vitima": tri_estado(
                ctx.get("barulho_recente"),
                "barulho da vítima não avaliado neste tipo de sinal"),
            # D1.1: 'spotted' é nativo e confiável. Vira sim/nao real nos
            # trackings; nos demais sinais permanece desconhecido (não avaliado).
            "radar_spotted": tri_estado(ctx.get("spotted_por_teammate"),
                                        RAZAO_SPOTTED),
            # D1.2 (v6.10): ESTIMATIVA — corrida a ≤1100 u, sem oclusão de som.
            # Anotação para calibração; não é exclusão automática.
            "passos_audiveis_estimados": tri_estado(
                ctx.get("passos_audiveis_estimado"),
                "passos não avaliados neste tipo de sinal (estimativa sem "
                "oclusão acústica)"),
            "call_teammate": desconhecido(RAZAO_CALL),
        },

        "saida_regra": {
            "classe": ctx.get("classe", "candidato"),
            "tipo": tipo,
            "motivo": mom.get("desc"),
            "peso": mom.get("peso", 0),
        },

        # Preenchido depois pela revisão humana cega (D0.3). Nunca inferido aqui.
        "rotulo_humano": None,
    }


# ---------------------------------------------------------------------------
# Persistência (JSONL append + dedup por episode_id)
# ---------------------------------------------------------------------------

def _ids_existentes(caminho):
    ids = set()
    if not os.path.exists(caminho):
        return ids
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                ids.add(json.loads(linha)["episode_id"])
            except (ValueError, KeyError):
                continue
    return ids


def salvar_episodios(episodios, caminho=ARQ_EPISODIOS):
    """Anexa episódios ao JSONL, pulando ids já gravados (reanálise não duplica).

    Retorna (novos, ignorados). JSONL: uma linha JSON por episódio, formato
    ideal para crescer ao longo de muitas demos e ler em streaming depois.
    """
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    ja_tem = _ids_existentes(caminho)
    novos = ignorados = 0
    with open(caminho, "a", encoding="utf-8") as f:
        for ep in episodios:
            if ep["episode_id"] in ja_tem:
                ignorados += 1
                continue
            f.write(json.dumps(ep, ensure_ascii=False) + "\n")
            ja_tem.add(ep["episode_id"])
            novos += 1
    return novos, ignorados
