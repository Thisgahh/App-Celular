
import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime, date
import hashlib
import os

# ============================================================
# FEITAL | GESTÃO DE ATIVOS - BUILD 01
# Aplicação responsiva para celular / tablet / computador
# ============================================================

APP_NAME = "Feital | Gestão de Ativos"
BUILD = "BUILD 01"
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "gestao_ativos.db"
LOGO_PATH = BASE_DIR / "assets" / "logo_feital_80.png"

st.set_page_config(
    page_title=APP_NAME,
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ------------------------- BANCO -----------------------------

def conectar():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_senha(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()

def inicializar_banco():
    with conectar() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                senha_hash TEXT NOT NULL,
                perfil TEXT NOT NULL DEFAULT 'TI',
                ativo INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS equipamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patrimonio TEXT UNIQUE NOT NULL,
                tipo TEXT NOT NULL,
                marca TEXT,
                modelo TEXT,
                serie_imei TEXT,
                status TEXT NOT NULL DEFAULT 'Disponível',
                observacoes TEXT,
                criado_em TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS movimentacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_movimento TEXT NOT NULL,
                patrimonio TEXT NOT NULL,
                colaborador TEXT NOT NULL,
                empresa_setor TEXT,
                matricula_rg TEXT,
                telefone TEXT,
                email TEXT,
                chamado TEXT,
                condicao TEXT,
                acessorios TEXT,
                observacoes TEXT,
                responsavel_ti TEXT,
                aceite_nome TEXT,
                aceite_confirmado INTEGER NOT NULL DEFAULT 0,
                data_movimento TEXT NOT NULL
            )
        """)
        # Usuário inicial de demonstração
        existe = conn.execute(
            "SELECT 1 FROM usuarios WHERE usuario = ?",
            ("admin",)
        ).fetchone()
        if not existe:
            conn.execute(
                "INSERT INTO usuarios (usuario, nome, senha_hash, perfil) VALUES (?, ?, ?, ?)",
                ("admin", "Administrador TI", hash_senha("admin123"), "Administrador")
            )
        conn.commit()

inicializar_banco()

# ------------------------- ESTILO ----------------------------

st.markdown("""
<style>
    :root {
        --feital-red: #d71920;
        --feital-red-dark: #a90d13;
        --feital-bg: #f4f6f8;
        --feital-text: #222b35;
        --feital-muted: #6f7b88;
        --feital-border: #e1e5ea;
    }

    .stApp {
        background:
            radial-gradient(circle at 8% 5%, rgba(215,25,32,.035), transparent 24%),
            linear-gradient(135deg, #fbfcfd 0%, #f3f5f7 100%);
    }

    #MainMenu, footer {visibility: hidden;}
    header[data-testid="stHeader"] {background: transparent;}

    .block-container {
        max-width: 1180px;
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }

    .login-wrap {
        max-width: 470px;
        margin: 2vh auto 0 auto;
        background: rgba(255,255,255,.98);
        border: 1px solid #edf0f3;
        border-radius: 24px;
        padding: 22px 24px 18px 24px;
        box-shadow: 0 18px 55px rgba(25,35,45,.12);
    }

    .login-title {
        text-align:center;
        font-weight:800;
        font-size:1.65rem;
        color:#20262d;
        margin: 6px 0 0 0;
    }

    .login-subtitle {
        text-align:center;
        color:var(--feital-red);
        font-weight:700;
        margin-top:2px;
    }

    .login-hint {
        text-align:center;
        color:#7b8490;
        font-size:.92rem;
        margin-bottom:12px;
    }

    .brand-footer {
        text-align:center;
        color:#7b8490;
        font-size:.78rem;
        margin-top:18px;
        letter-spacing:.02em;
    }

    .app-header {
        background: rgba(255,255,255,.96);
        border: 1px solid var(--feital-border);
        border-radius: 20px;
        padding: 16px 18px;
        box-shadow: 0 8px 26px rgba(30,42,55,.07);
        margin-bottom: 14px;
    }

    .app-title {
        font-size:1.55rem;
        font-weight:800;
        color:var(--feital-text);
        margin:0;
    }

    .app-subtitle {
        color:var(--feital-muted);
        margin-top:2px;
        font-size:.92rem;
    }

    .hero {
        padding: 22px;
        border-radius: 22px;
        background: linear-gradient(135deg, #ffffff 0%, #f7f8fa 70%, #fff0f0 100%);
        border: 1px solid var(--feital-border);
        box-shadow: 0 10px 30px rgba(30,42,55,.06);
        margin-bottom: 14px;
    }

    .hero h2 {margin:0;color:#242b33;font-size:1.45rem;}
    .hero p {color:#6d7783;margin:.35rem 0 0 0;}

    .metric-card {
        background:#fff;
        border:1px solid var(--feital-border);
        border-radius:18px;
        padding:18px;
        min-height:112px;
        box-shadow:0 6px 18px rgba(30,42,55,.05);
    }

    .metric-label {color:#7a8490;font-size:.86rem;font-weight:650;}
    .metric-value {font-size:1.75rem;font-weight:850;color:#222b35;margin-top:6px;}
    .metric-red {color:var(--feital-red);}

    .section-title {
        font-size:1.15rem;
        font-weight:800;
        color:#27303a;
        margin:12px 0 10px 0;
    }

    .mobile-card {
        background:#fff;
        border:1px solid var(--feital-border);
        border-radius:18px;
        padding:16px;
        margin-bottom:10px;
    }

    div.stButton > button {
        border-radius: 14px;
        min-height: 48px;
        font-weight: 750;
        transition: all .15s ease-in-out;
    }

    div.stButton > button[kind="primary"] {
        background: linear-gradient(180deg, #e51c24 0%, #c91017 100%);
        border-color: #c91017;
    }

    div.stButton > button[kind="primary"]:hover {
        background: linear-gradient(180deg, #cc151c 0%, #aa0c12 100%);
        border-color:#aa0c12;
    }

    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stSelectbox"] > div > div,
    div[data-testid="stDateInput"] input {
        border-radius: 12px !important;
    }

    .status-ok {
        display:inline-block;
        padding:4px 9px;
        border-radius:999px;
        background:#e8f7ef;
        color:#167a46;
        font-size:.78rem;
        font-weight:750;
    }

    .status-use {
        display:inline-block;
        padding:4px 9px;
        border-radius:999px;
        background:#fff1e4;
        color:#a35400;
        font-size:.78rem;
        font-weight:750;
    }

    .status-bad {
        display:inline-block;
        padding:4px 9px;
        border-radius:999px;
        background:#fdebec;
        color:#b81820;
        font-size:.78rem;
        font-weight:750;
    }

    @media (max-width: 700px) {
        .block-container {
            padding: .65rem .72rem 1.5rem .72rem;
        }

        .login-wrap {
            margin-top: .5vh;
            padding: 16px 15px 14px 15px;
            border-radius: 20px;
        }

        .app-header {
            padding: 13px 14px;
            border-radius: 17px;
        }

        .app-title {font-size:1.25rem;}
        .hero {padding:17px;border-radius:18px;}
        .hero h2 {font-size:1.2rem;}

        div.stButton > button {
            min-height: 54px;
            font-size: .98rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# ------------------------- SESSÃO ----------------------------

for chave, valor in {
    "logado": False,
    "usuario": "",
    "nome_usuario": "",
    "pagina": "inicio",
}.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor

def navegar(pagina):
    st.session_state.pagina = pagina
    st.rerun()

def logout():
    st.session_state.logado = False
    st.session_state.usuario = ""
    st.session_state.nome_usuario = ""
    st.session_state.pagina = "inicio"
    st.rerun()

# -------------------------- LOGIN ----------------------------

def tela_login():
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)

    if LOGO_PATH.exists():
        c1, c2, c3 = st.columns([1, 3.2, 1])
        with c2:
            st.image(str(LOGO_PATH), use_container_width=True)

    st.markdown('<div class="login-title">Acesse sua Conta</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">Gestão de Ativos e Termos</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-hint">Insira suas credenciais para continuar.</div>', unsafe_allow_html=True)

    with st.form("form_login", clear_on_submit=False):
        usuario = st.text_input("Usuário", placeholder="admin ou seu usuário")
        senha = st.text_input("Senha", type="password", placeholder="••••••••")
        lembrar = st.checkbox("Lembrar de mim")
        entrar = st.form_submit_button("🔐  Entrar", type="primary", use_container_width=True)

    if entrar:
        with conectar() as conn:
            registro = conn.execute(
                "SELECT * FROM usuarios WHERE usuario = ? AND ativo = 1",
                (usuario.strip(),)
            ).fetchone()

        if registro and registro["senha_hash"] == hash_senha(senha):
            st.session_state.logado = True
            st.session_state.usuario = registro["usuario"]
            st.session_state.nome_usuario = registro["nome"]
            st.session_state.pagina = "inicio"
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")

    st.info("Primeiro acesso da Build 01: **admin** / **admin123**. Altere antes do uso definitivo.")
    st.markdown(
        '<div class="brand-footer"><b>GRUPO FEITAL</b> &nbsp;|&nbsp; GESTÃO DE ATIVOS<br>'
        'Tradição que conecta o futuro · Build 01</div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------- CABEÇALHO -------------------------

def cabecalho(titulo="Gestão de Ativos", subtitulo="Controle de equipamentos e termos de responsabilidade"):
    c_logo, c_titulo, c_sair = st.columns([1.15, 4.5, 1.2])
    with c_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
    with c_titulo:
        st.markdown(
            f'<div class="app-header"><div class="app-title">{titulo}</div>'
            f'<div class="app-subtitle">{subtitulo}</div></div>',
            unsafe_allow_html=True,
        )
    with c_sair:
        st.caption(f"👤 {st.session_state.nome_usuario}")
        if st.button("Sair", use_container_width=True):
            logout()

# ----------------------- DASHBOARD ---------------------------

def contagens():
    with conectar() as conn:
        total = conn.execute("SELECT COUNT(*) FROM equipamentos").fetchone()[0]
        uso = conn.execute("SELECT COUNT(*) FROM equipamentos WHERE status = 'Em uso'").fetchone()[0]
        disponiveis = conn.execute("SELECT COUNT(*) FROM equipamentos WHERE status = 'Disponível'").fetchone()[0]
        avarias = conn.execute("SELECT COUNT(*) FROM equipamentos WHERE status IN ('Quebrado','Com defeito')").fetchone()[0]
    return total, uso, disponiveis, avarias

def tela_inicio():
    cabecalho()
    nome = st.session_state.nome_usuario.split()[0] if st.session_state.nome_usuario else "Usuário"

    st.markdown(
        f'<div class="hero"><h2>Olá, {nome} 👋</h2>'
        '<p>Registre entregas e devoluções de notebooks, celulares e outros equipamentos diretamente pelo celular.</p></div>',
        unsafe_allow_html=True,
    )

    total, uso, disponiveis, avarias = contagens()
    cols = st.columns(4)
    valores = [
        ("Equipamentos", total, ""),
        ("Em uso", uso, "metric-red"),
        ("Disponíveis", disponiveis, ""),
        ("Com avaria", avarias, "metric-red"),
    ]
    for col, (rotulo, valor, classe) in zip(cols, valores):
        with col:
            st.markdown(
                f'<div class="metric-card"><div class="metric-label">{rotulo}</div>'
                f'<div class="metric-value {classe}">{valor}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div class="section-title">Ações rápidas</div>', unsafe_allow_html=True)

    a, b = st.columns(2)
    with a:
        if st.button("📤  Nova Entrega", type="primary", use_container_width=True):
            navegar("entrega")
    with b:
        if st.button("📥  Devolução", use_container_width=True):
            navegar("devolucao")

    a, b = st.columns(2)
    with a:
        if st.button("🔎  Consultar Equipamento", use_container_width=True):
            navegar("consulta")
    with b:
        if st.button("📄  Termos / Histórico", use_container_width=True):
            navegar("historico")

    if st.button("➕  Cadastrar Equipamento", use_container_width=True):
        navegar("cadastro")

    st.caption("Build 01 · versão inicial responsiva para testes em celular.")

# ------------------- CADASTRAR EQUIPAMENTO -------------------

def tela_cadastro():
    cabecalho("Cadastrar Equipamento", "Inclua notebook, celular, monitor ou outro ativo")
    if st.button("← Voltar", use_container_width=False):
        navegar("inicio")

    with st.form("cadastro_equipamento"):
        patrimonio = st.text_input("Patrimônio / identificação *", placeholder="Ex.: NOTE 125 ou CEL 226")
        tipo = st.selectbox("Tipo *", ["Notebook", "Smartphone", "Desktop", "Monitor", "Tablet", "Outro"])
        marca = st.text_input("Marca", placeholder="Ex.: Dell, Lenovo, Samsung")
        modelo = st.text_input("Modelo")
        serie_imei = st.text_input("Nº de série / IMEI")
        observacoes = st.text_area("Observações")
        salvar = st.form_submit_button("💾 Salvar equipamento", type="primary", use_container_width=True)

    if salvar:
        if not patrimonio.strip():
            st.error("Informe o patrimônio/identificação.")
            return
        try:
            with conectar() as conn:
                conn.execute("""
                    INSERT INTO equipamentos
                    (patrimonio, tipo, marca, modelo, serie_imei, status, observacoes, criado_em)
                    VALUES (?, ?, ?, ?, ?, 'Disponível', ?, ?)
                """, (
                    patrimonio.strip().upper(), tipo, marca.strip(), modelo.strip(),
                    serie_imei.strip(), observacoes.strip(), datetime.now().isoformat(timespec="seconds")
                ))
                conn.commit()
            st.success("Equipamento cadastrado com sucesso.")
        except sqlite3.IntegrityError:
            st.error("Já existe um equipamento com esse patrimônio/identificação.")

# --------------------------- ENTREGA -------------------------

def listar_disponiveis():
    with conectar() as conn:
        return conn.execute(
            "SELECT * FROM equipamentos WHERE status = 'Disponível' ORDER BY patrimonio"
        ).fetchall()

def tela_entrega():
    cabecalho("Nova Entrega", "Termo de uso, guarda e responsabilidade")
    if st.button("← Voltar", use_container_width=False):
        navegar("inicio")

    equipamentos = listar_disponiveis()
    if not equipamentos:
        st.warning("Não há equipamentos disponíveis. Cadastre um equipamento primeiro.")
        if st.button("Cadastrar equipamento agora", type="primary"):
            navegar("cadastro")
        return

    mapa = {f'{r["patrimonio"]} · {r["tipo"]} · {r["marca"] or ""} {r["modelo"] or ""}'.strip(): r for r in equipamentos}

    with st.form("form_entrega"):
        escolha = st.selectbox("Equipamento *", list(mapa.keys()))
        colaborador = st.text_input("Nome do colaborador *")
        empresa_setor = st.text_input("Empresa / setor", placeholder="Ex.: Inox Tech / Produção")
        matricula_rg = st.text_input("Matrícula / RG")
        telefone = st.text_input("Telefone / ramal")
        email = st.text_input("E-mail")
        chamado = st.text_input("Chamado")
        acessorios = st.multiselect(
            "Acessórios entregues",
            ["Carregador", "Mouse", "Mochila", "Teclado", "Dock station", "Cabo de rede", "Outro"]
        )
        condicao = st.selectbox("Condição na entrega", ["Perfeito estado", "Com marcas de uso", "Outro"])
        observacoes = st.text_area("Observações")
        st.markdown("**Aceite do termo**")
        aceite_nome = st.text_input("Nome para aceite *", placeholder="Digite o nome do colaborador")
        aceite = st.checkbox(
            "Declaro que recebi o equipamento e estou ciente das condições do termo de uso, guarda e responsabilidade."
        )
        salvar = st.form_submit_button("✅ Finalizar Entrega", type="primary", use_container_width=True)

    if salvar:
        if not colaborador.strip() or not aceite_nome.strip() or not aceite:
            st.error("Preencha o colaborador, o nome do aceite e confirme o termo.")
            return

        eq = mapa[escolha]
        agora = datetime.now().isoformat(timespec="seconds")
        with conectar() as conn:
            conn.execute("""
                INSERT INTO movimentacoes
                (tipo_movimento, patrimonio, colaborador, empresa_setor, matricula_rg,
                 telefone, email, chamado, condicao, acessorios, observacoes,
                 responsavel_ti, aceite_nome, aceite_confirmado, data_movimento)
                VALUES ('ENTREGA', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                eq["patrimonio"], colaborador.strip(), empresa_setor.strip(), matricula_rg.strip(),
                telefone.strip(), email.strip(), chamado.strip(), condicao,
                ", ".join(acessorios), observacoes.strip(), st.session_state.nome_usuario,
                aceite_nome.strip(), agora
            ))
            conn.execute(
                "UPDATE equipamentos SET status = 'Em uso' WHERE patrimonio = ?",
                (eq["patrimonio"],)
            )
            conn.commit()

        st.success(f"Entrega do equipamento {eq['patrimonio']} registrada com sucesso.")
        st.balloons()

# -------------------------- DEVOLUÇÃO ------------------------

def listar_em_uso():
    with conectar() as conn:
        return conn.execute(
            "SELECT * FROM equipamentos WHERE status = 'Em uso' ORDER BY patrimonio"
        ).fetchall()

def ultimo_colaborador(patrimonio):
    with conectar() as conn:
        r = conn.execute("""
            SELECT colaborador FROM movimentacoes
            WHERE patrimonio = ? AND tipo_movimento = 'ENTREGA'
            ORDER BY id DESC LIMIT 1
        """, (patrimonio,)).fetchone()
    return r["colaborador"] if r else ""

def tela_devolucao():
    cabecalho("Devolução", "Registre o retorno e a condição do equipamento")
    if st.button("← Voltar", use_container_width=False):
        navegar("inicio")

    equipamentos = listar_em_uso()
    if not equipamentos:
        st.info("Não existem equipamentos marcados como 'Em uso'.")
        return

    mapa = {f'{r["patrimonio"]} · {r["tipo"]} · {r["marca"] or ""} {r["modelo"] or ""}'.strip(): r for r in equipamentos}
    escolha = st.selectbox("Equipamento *", list(mapa.keys()), key="dev_equip")
    eq = mapa[escolha]
    colaborador_atual = ultimo_colaborador(eq["patrimonio"])
    st.info(f"Último responsável registrado: **{colaborador_atual or 'não localizado'}**")

    with st.form("form_devolucao"):
        condicao = st.radio(
            "Condição na devolução *",
            ["Em perfeito estado", "Apresentando defeito", "Quebrado"],
            horizontal=False
        )
        observacoes = st.text_area("Observações / descrição do problema")
        responsavel = st.text_input(
            "Responsável pela devolução",
            value=colaborador_atual
        )
        aceite = st.checkbox("Confirmo o recebimento e a condição informada acima.")
        salvar = st.form_submit_button("📥 Registrar Devolução", type="primary", use_container_width=True)

    if salvar:
        if not responsavel.strip() or not aceite:
            st.error("Informe o responsável e confirme o recebimento.")
            return

        novo_status = {
            "Em perfeito estado": "Disponível",
            "Apresentando defeito": "Com defeito",
            "Quebrado": "Quebrado",
        }[condicao]

        agora = datetime.now().isoformat(timespec="seconds")
        with conectar() as conn:
            conn.execute("""
                INSERT INTO movimentacoes
                (tipo_movimento, patrimonio, colaborador, condicao, observacoes,
                 responsavel_ti, aceite_nome, aceite_confirmado, data_movimento)
                VALUES ('DEVOLUÇÃO', ?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                eq["patrimonio"], responsavel.strip(), condicao, observacoes.strip(),
                st.session_state.nome_usuario, responsavel.strip(), agora
            ))
            conn.execute(
                "UPDATE equipamentos SET status = ? WHERE patrimonio = ?",
                (novo_status, eq["patrimonio"])
            )
            conn.commit()

        st.success(f"Devolução do equipamento {eq['patrimonio']} registrada como: {condicao}.")

# --------------------------- CONSULTA ------------------------

def status_html(status):
    if status == "Disponível":
        classe = "status-ok"
    elif status == "Em uso":
        classe = "status-use"
    else:
        classe = "status-bad"
    return f'<span class="{classe}">{status}</span>'

def tela_consulta():
    cabecalho("Consultar Equipamento", "Pesquise por patrimônio, modelo, série ou IMEI")
    if st.button("← Voltar", use_container_width=False):
        navegar("inicio")

    busca = st.text_input("Pesquisar", placeholder="Ex.: CEL 226, Dell, serial...")
    termo = f"%{busca.strip()}%"

    with conectar() as conn:
        if busca.strip():
            registros = conn.execute("""
                SELECT * FROM equipamentos
                WHERE patrimonio LIKE ? OR tipo LIKE ? OR marca LIKE ?
                   OR modelo LIKE ? OR serie_imei LIKE ?
                ORDER BY patrimonio
            """, (termo, termo, termo, termo, termo)).fetchall()
        else:
            registros = conn.execute("SELECT * FROM equipamentos ORDER BY patrimonio").fetchall()

    if not registros:
        st.info("Nenhum equipamento encontrado.")
        return

    for r in registros:
        st.markdown('<div class="mobile-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([3,1])
        with c1:
            st.markdown(f"### {r['patrimonio']} · {r['tipo']}")
            st.write(f"**Marca/Modelo:** {r['marca'] or '-'} {r['modelo'] or ''}")
            st.write(f"**Série/IMEI:** {r['serie_imei'] or '-'}")
        with c2:
            st.markdown(status_html(r["status"]), unsafe_allow_html=True)
        if r["observacoes"]:
            st.caption(r["observacoes"])
        st.markdown("</div>", unsafe_allow_html=True)

# --------------------------- HISTÓRICO -----------------------

def tela_historico():
    cabecalho("Termos e Histórico", "Movimentações registradas no sistema")
    if st.button("← Voltar", use_container_width=False):
        navegar("inicio")

    filtro = st.text_input("Pesquisar", placeholder="Patrimônio ou colaborador")
    termo = f"%{filtro.strip()}%"

    with conectar() as conn:
        if filtro.strip():
            rows = conn.execute("""
                SELECT * FROM movimentacoes
                WHERE patrimonio LIKE ? OR colaborador LIKE ?
                ORDER BY id DESC LIMIT 100
            """, (termo, termo)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM movimentacoes ORDER BY id DESC LIMIT 100"
            ).fetchall()

    if not rows:
        st.info("Ainda não existem movimentações.")
        return

    for r in rows:
        icone = "📤" if r["tipo_movimento"] == "ENTREGA" else "📥"
        data_fmt = r["data_movimento"].replace("T", " ")
        st.markdown('<div class="mobile-card">', unsafe_allow_html=True)
        st.markdown(f"#### {icone} {r['tipo_movimento']} · {r['patrimonio']}")
        st.write(f"**Colaborador:** {r['colaborador']}")
        st.write(f"**Condição:** {r['condicao'] or '-'}")
        st.caption(f"{data_fmt} · TI: {r['responsavel_ti'] or '-'}")
        if r["observacoes"]:
            st.write(r["observacoes"])
        st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------- ROTA ---------------------------

if not st.session_state.logado:
    tela_login()
else:
    paginas = {
        "inicio": tela_inicio,
        "cadastro": tela_cadastro,
        "entrega": tela_entrega,
        "devolucao": tela_devolucao,
        "consulta": tela_consulta,
        "historico": tela_historico,
    }
    paginas.get(st.session_state.pagina, tela_inicio)()
