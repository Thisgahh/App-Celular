import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import secrets
from io import BytesIO
from urllib.parse import quote
import qrcode
import numpy as np
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from streamlit_drawable_canvas import st_canvas

# ============================================================
# FEITAL | GESTÃO DE ATIVOS - BUILD 02.4
# Assinatura pública pelo celular + PDF + câmera + QR Code
# ============================================================

APP_NAME = "Feital | Gestão de Ativos"
BUILD = "BUILD 02.4"
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "gestao_ativos.db"
LOGO_PATH = BASE_DIR / "assets" / "logo_feital_80.png"
UPLOAD_DIR = BASE_DIR / "uploads"
SIGN_DIR = BASE_DIR / "assinaturas"
PDF_DIR = BASE_DIR / "termos_pdf"
for d in (UPLOAD_DIR, SIGN_DIR, PDF_DIR):
    d.mkdir(exist_ok=True)

st.set_page_config(page_title=APP_NAME, page_icon="📱", layout="wide", initial_sidebar_state="collapsed")

# ------------------------- BANCO -----------------------------
def conectar():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_senha(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()

def agora_iso():
    return datetime.now().isoformat(timespec="seconds")

def inicializar_banco():
    with conectar() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
            perfil TEXT NOT NULL DEFAULT 'TI',
            ativo INTEGER NOT NULL DEFAULT 1)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS equipamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patrimonio TEXT UNIQUE NOT NULL,
            tipo TEXT NOT NULL,
            marca TEXT,
            modelo TEXT,
            serie_imei TEXT,
            status TEXT NOT NULL DEFAULT 'Disponível',
            observacoes TEXT,
            criado_em TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS movimentacoes (
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
            data_movimento TEXT NOT NULL,
            status_assinatura TEXT NOT NULL DEFAULT 'N/A',
            token_assinatura TEXT UNIQUE,
            token_expira_em TEXT,
            assinado_em TEXT,
            assinatura_path TEXT,
            foto_path TEXT,
            pdf_path TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT)""")
        # migração segura para bancos da Build 01
        cols = {r[1] for r in conn.execute("PRAGMA table_info(movimentacoes)").fetchall()}
        novos = {
            "status_assinatura": "TEXT NOT NULL DEFAULT 'N/A'",
            "token_assinatura": "TEXT",
            "token_expira_em": "TEXT",
            "assinado_em": "TEXT",
            "assinatura_path": "TEXT",
            "foto_path": "TEXT",
            "pdf_path": "TEXT",
        }
        for nome, tipo in novos.items():
            if nome not in cols:
                conn.execute(f"ALTER TABLE movimentacoes ADD COLUMN {nome} {tipo}")
        existe = conn.execute("SELECT 1 FROM usuarios WHERE usuario='admin'").fetchone()
        if not existe:
            conn.execute("INSERT INTO usuarios (usuario,nome,senha_hash,perfil) VALUES (?,?,?,?)",
                         ("admin", "Administrador TI", hash_senha("admin123"), "Administrador"))
        conn.commit()

inicializar_banco()

# ------------------------- CONFIG ----------------------------
def get_config(chave, padrao=""):
    with conectar() as conn:
        r = conn.execute("SELECT valor FROM configuracoes WHERE chave=?", (chave,)).fetchone()
    return r["valor"] if r else padrao

def set_config(chave, valor):
    with conectar() as conn:
        conn.execute("INSERT INTO configuracoes(chave,valor) VALUES(?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, valor))
        conn.commit()

def base_publica():
    cfg = get_config("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if cfg:
        return cfg
    try:
        sec = str(st.secrets.get("PUBLIC_BASE_URL", "")).strip().rstrip("/")
        if sec:
            return sec
    except Exception:
        pass
    return ""

def link_assinatura(token):
    base = base_publica()
    return f"{base}/?assinar={token}" if base and token else ""

def botao_copiar_link(link, chave):
    import html
    seguro = html.escape(link, quote=True)
    componente = f"""
    <div style="width:100%;">
      <input id="link_{chave}" value="{seguro}" readonly style="position:absolute;left:-9999px;top:-9999px;" />
      <button onclick="copiar_{chave}()" style="width:100%;height:46px;border:1px solid #d9dde5;border-radius:12px;background:white;font-family:Arial,sans-serif;font-size:14px;cursor:pointer;color:#1f2937;">📋 Copiar link</button>
      <div id="msg_{chave}" style="font-family:Arial,sans-serif;font-size:12px;margin-top:4px;color:#198754;"></div>
    </div>
    <script>
      async function copiar_{chave}() {{
        const campo = document.getElementById('link_{chave}');
        const msg = document.getElementById('msg_{chave}');
        try {{
          if (navigator.clipboard && window.isSecureContext) {{
            await navigator.clipboard.writeText(campo.value);
          }} else {{
            campo.style.position='fixed'; campo.style.left='0'; campo.style.top='0';
            campo.select(); campo.setSelectionRange(0,99999); document.execCommand('copy');
            campo.style.position='absolute'; campo.style.left='-9999px'; campo.style.top='-9999px';
          }}
          msg.innerText='Link copiado!';
          setTimeout(() => msg.innerText='',1800);
        }} catch(e) {{
          msg.innerText='Use o campo acima para copiar o link.';
        }}
      }}
    </script>
    """
    st.components.v1.html(componente, height=68)

# ------------------------- ESTILO ----------------------------
st.markdown("""
<style>
:root{--red:#d71920;--dark:#222b35;--muted:#6f7b88;--border:#e1e5ea;}
.stApp{background:linear-gradient(135deg,#fbfcfd 0%,#f3f5f7 100%)}
#MainMenu,footer{visibility:hidden} header[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1180px;padding-top:1rem;padding-bottom:2rem}
.login-wrap,.public-card{max-width:640px;margin:1vh auto;background:#fff;border:1px solid #edf0f3;border-radius:24px;padding:22px;box-shadow:0 18px 55px rgba(25,35,45,.11)}
.app-header{background:#fff;border:1px solid var(--border);border-radius:20px;padding:15px 18px;box-shadow:0 8px 26px rgba(30,42,55,.06);margin-bottom:12px}
.app-title{font-size:1.45rem;font-weight:850;color:var(--dark)} .app-subtitle{color:var(--muted);font-size:.92rem}
.hero{padding:20px;border-radius:20px;background:linear-gradient(135deg,#fff,#f8f8fa 72%,#fff0f0);border:1px solid var(--border);margin-bottom:13px}
.metric-card,.mobile-card{background:#fff;border:1px solid var(--border);border-radius:18px;padding:16px;box-shadow:0 6px 18px rgba(30,42,55,.045);margin-bottom:10px}
.metric-label{color:#7a8490;font-size:.86rem;font-weight:650}.metric-value{font-size:1.65rem;font-weight:850;color:#222b35;margin-top:6px}
.section-title{font-size:1.12rem;font-weight:850;color:#27303a;margin:14px 0 9px}
div.stButton>button{border-radius:14px;min-height:48px;font-weight:750} div.stButton>button[kind="primary"]{background:#d71920;border-color:#d71920}
.status{display:inline-block;padding:5px 10px;border-radius:999px;font-size:.78rem;font-weight:800}.green{background:#e8f7ef;color:#167a46}.orange{background:#fff1e4;color:#a35400}.red{background:#fdebec;color:#b81820}.blue{background:#e9f2ff;color:#275ea8}
.term-text{font-size:.95rem;line-height:1.55;color:#313943}.signature-box{border:2px dashed #cbd1d8;border-radius:15px;padding:8px;background:#fff}
@media(max-width:700px){.block-container{padding:.55rem .65rem 1.4rem}.login-wrap,.public-card{padding:15px;border-radius:19px}.app-title{font-size:1.2rem}div.stButton>button{min-height:54px}.term-text{font-size:.9rem}}
</style>
""", unsafe_allow_html=True)

# ------------------------- PDF -------------------------------
TERMO_PARAGRAFOS = [
    "Recebi da empresa InoxTech - Feital, a título de empréstimo, para meu uso exclusivo, conforme determinado, os equipamentos especificados neste termo de responsabilidade, comprometendo-me a mantê-los em perfeito estado de conservação, ficando ciente de que:",
    "1 - Se o equipamento for danificado ou inutilizado por emprego inadequado, mau uso, negligência ou extravio, a empresa poderá adotar as providências cabíveis conforme suas normas internas e legislação aplicável.",
    "2 - Em caso de dano, inutilização ou extravio do equipamento deverei comunicar imediatamente ao setor competente.",
    "3 - Terminando os serviços ou no caso de rescisão do contrato de trabalho, devolverei o equipamento completo e em perfeito estado de conservação, considerando-se o tempo de uso do mesmo, ao setor competente.",
    "4 - Estando os equipamentos em minha posse, estarei sujeito a inspeções conforme as normas internas da empresa.",
]

def gerar_pdf(mov):
    out = PDF_DIR / f"TERMO_{mov['patrimonio'].replace(' ','_')}_{mov['id']}.pdf"
    styles = getSampleStyleSheet()
    normal = ParagraphStyle('normal2', parent=styles['BodyText'], fontName='Helvetica', fontSize=10.2, leading=14, spaceAfter=8)
    title = ParagraphStyle('title2', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=13, leading=16, alignment=TA_CENTER, spaceAfter=13)
    small = ParagraphStyle('small2', parent=styles['BodyText'], fontName='Helvetica', fontSize=8.5, leading=11, textColor=colors.HexColor('#555555'))
    doc = SimpleDocTemplate(str(out), pagesize=A4, rightMargin=1.6*cm, leftMargin=1.6*cm, topMargin=1.3*cm, bottomMargin=1.3*cm)
    story=[]
    if LOGO_PATH.exists():
        story += [RLImage(str(LOGO_PATH), width=4.1*cm, height=2.2*cm), Spacer(1,5)]
    story += [Paragraph("TERMO DE USO, GUARDA E RESPONSABILIDADE", title)]
    dados = [
        ["Nome:", mov['colaborador'], "Matrícula/RG:", mov['matricula_rg'] or '-'],
        ["Empresa / Setor:", mov['empresa_setor'] or '-', "Telefone:", mov['telefone'] or '-'],
        ["E-mail:", mov['email'] or '-', "Chamado:", mov['chamado'] or '-'],
    ]
    t=Table(dados, colWidths=[2.6*cm,6.0*cm,2.6*cm,5.4*cm])
    t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),9),('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('FONTNAME',(2,0),(2,-1),'Helvetica-Bold'),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story += [t, Spacer(1,8)]
    for p in TERMO_PARAGRAFOS: story.append(Paragraph(p, normal))
    story += [Spacer(1,5)]
    eq = [["EQUIPAMENTO", mov['patrimonio']], ["CONDIÇÃO NA ENTREGA", mov['condicao'] or '-'], ["ACESSÓRIOS", mov['acessorios'] or '-']]
    te=Table(eq,colWidths=[5.0*cm,11.6*cm])
    te.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),colors.HexColor('#f2f3f5')),('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('FONTNAME',(1,0),(1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),9.5),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#d9dde2')),('PADDING',(0,0),(-1,-1),6)]))
    story += [te, Spacer(1,12)]
    if mov['assinatura_path'] and Path(mov['assinatura_path']).exists():
        story += [Paragraph("ASSINATURA DO COLABORADOR", ParagraphStyle('sigtitle', parent=normal, fontName='Helvetica-Bold', spaceAfter=3)), RLImage(mov['assinatura_path'], width=7.6*cm, height=2.4*cm), Paragraph(mov['aceite_nome'] or mov['colaborador'], normal)]
    story += [Paragraph(f"Assinado eletronicamente em: {mov['assinado_em'] or '-'}", small), Paragraph(f"Código de validação: {mov['token_assinatura'] or '-'}", small), Paragraph(f"Responsável TI: {mov['responsavel_ti'] or '-'}", small)]
    if mov['foto_path'] and Path(mov['foto_path']).exists():
        story += [PageBreak(), Paragraph("REGISTRO FOTOGRÁFICO DO EQUIPAMENTO", title), RLImage(mov['foto_path'], width=15.5*cm, height=11.5*cm)]
    doc.build(story)
    return str(out)

# ------------------------- QR --------------------------------
def qr_bytes(texto):
    qr=qrcode.QRCode(version=None, box_size=7, border=3)
    qr.add_data(texto); qr.make(fit=True)
    img=qr.make_image(fill_color="black", back_color="white")
    bio=BytesIO(); img.save(bio, format="PNG"); return bio.getvalue()

# ------------------------- SESSÃO ----------------------------
for k,v in {"logado":False,"usuario":"","nome_usuario":"","pagina":"inicio"}.items():
    if k not in st.session_state: st.session_state[k]=v

def navegar(p): st.session_state.pagina=p; st.rerun()
def logout():
    st.session_state.logado=False; st.session_state.usuario=""; st.session_state.nome_usuario=""; st.session_state.pagina="inicio"; st.rerun()

# ------------------- ASSINATURA PÚBLICA ----------------------
def buscar_por_token(token):
    with conectar() as conn:
        return conn.execute("SELECT * FROM movimentacoes WHERE token_assinatura=? LIMIT 1", (token,)).fetchone()

def tela_assinatura_publica(token):
    mov=buscar_por_token(token)
    st.markdown('<div class="public-card">', unsafe_allow_html=True)
    if LOGO_PATH.exists():
        a,b,c=st.columns([1,2.4,1])
        with b: st.image(str(LOGO_PATH), use_container_width=True)
    st.markdown("<h2 style='text-align:center;margin:.2rem 0'>Termo de Responsabilidade</h2>", unsafe_allow_html=True)
    st.caption("Feital | Gestão de Ativos - assinatura pelo celular")
    if not mov:
        st.error("Link de assinatura inválido ou não localizado."); st.markdown('</div>', unsafe_allow_html=True); return
    if mov['status_assinatura']=='ASSINADO':
        st.success("Este termo já foi assinado e o link foi encerrado.")
        st.write(f"**Colaborador:** {mov['colaborador']}")
        st.write(f"**Equipamento:** {mov['patrimonio']}")
        st.write(f"**Assinado em:** {mov['assinado_em']}")
        st.markdown('</div>', unsafe_allow_html=True); return
    if mov['token_expira_em']:
        exp=datetime.fromisoformat(mov['token_expira_em'])
        if datetime.now()>exp:
            with conectar() as conn:
                conn.execute("UPDATE movimentacoes SET status_assinatura='EXPIRADO' WHERE id=?", (mov['id'],)); conn.commit()
            st.error("Este link expirou. Solicite um novo link ao setor de TI."); st.markdown('</div>', unsafe_allow_html=True); return
    st.info(f"**{mov['colaborador']}**, confira os dados abaixo antes de assinar.")
    st.write(f"**Equipamento:** {mov['patrimonio']}")
    st.write(f"**Empresa / Setor:** {mov['empresa_setor'] or '-'}")
    st.write(f"**Matrícula / RG:** {mov['matricula_rg'] or '-'}")
    st.write(f"**Chamado:** {mov['chamado'] or '-'}")
    st.write(f"**Condição:** {mov['condicao'] or '-'}")
    if mov['acessorios']: st.write(f"**Acessórios:** {mov['acessorios']}")
    st.markdown("<div class='section-title'>Termo de uso, guarda e responsabilidade</div>", unsafe_allow_html=True)
    for p in TERMO_PARAGRAFOS: st.markdown(f"<div class='term-text'>{p}</div><br>", unsafe_allow_html=True)
    with st.expander("📷 Foto do equipamento (opcional)", expanded=False):
        foto=st.camera_input("Tire uma foto do equipamento", key=f"foto_{mov['id']}")
    st.markdown("<div class='section-title'>Assine com o dedo abaixo</div>", unsafe_allow_html=True)
    st.caption("Use o dedo na tela. Se errar, utilize a opção de limpar no quadro de assinatura.")
    canvas=st_canvas(stroke_width=3, stroke_color="#111111", background_color="#FFFFFF", height=180, width=620, drawing_mode="freedraw", return_image_data=True, key=f"sig_{mov['id']}")
    aceite_nome=st.text_input("Digite seu nome completo para confirmar", value=mov['colaborador'])
    aceite=st.checkbox("Li e estou de acordo com o termo acima e confirmo que esta assinatura é minha.")
    if st.button("✅ Confirmar e Assinar", type="primary", use_container_width=True):
        objetos=(canvas.json_data or {}).get('objects',[]) if canvas else []
        if not aceite_nome.strip() or not aceite:
            st.error("Digite seu nome e marque a confirmação do termo.")
        elif not objetos or canvas.image_data is None:
            st.error("Faça sua assinatura no quadro antes de confirmar.")
        else:
            arr=np.asarray(canvas.image_data).astype('uint8')
            sig=PILImage.fromarray(arr)
            sig_path=SIGN_DIR / f"assinatura_{mov['id']}_{token[:8]}.png"
            sig.save(sig_path)
            foto_path=""
            if foto is not None:
                foto_img=PILImage.open(foto)
                foto_path=str(UPLOAD_DIR / f"foto_{mov['id']}_{token[:8]}.jpg")
                foto_img.convert('RGB').save(foto_path, quality=88)
            assinado=agora_iso()
            with conectar() as conn:
                conn.execute("""UPDATE movimentacoes SET aceite_nome=?, aceite_confirmado=1,status_assinatura='ASSINADO',assinado_em=?,assinatura_path=?,foto_path=? WHERE id=?""",
                             (aceite_nome.strip(),assinado,str(sig_path),foto_path,mov['id']))
                conn.execute("UPDATE equipamentos SET status='Em uso' WHERE patrimonio=?", (mov['patrimonio'],))
                conn.commit()
            mov2=buscar_por_token(token)
            pdf=gerar_pdf(mov2)
            with conectar() as conn:
                conn.execute("UPDATE movimentacoes SET pdf_path=? WHERE id=?", (pdf,mov['id'])); conn.commit()
            st.success("Assinatura registrada com sucesso. Obrigado!")
            st.balloons()
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------- LOGIN ----------------------------
def tela_login():
    # Layout compacto inspirado no portal Gestão de Pagamentos
    st.markdown("""
    <style>
    .block-container{
        max-width:500px !important;
        padding-top:1.1rem !important;
        padding-left:1rem !important;
        padding-right:1rem !important;
    }
    [data-testid="stForm"]{
        background:#ffffff;
        border:1px solid #e1e5ea;
        border-radius:12px;
        padding:14px 14px 12px 14px;
        box-shadow:0 8px 22px rgba(30,42,55,.08);
    }
    .login-head{
        background:#ffffff;
        border:1px solid #e1e5ea;
        border-radius:18px;
        padding:14px 16px 16px 16px;
        box-shadow:0 8px 24px rgba(30,42,55,.08);
        margin-bottom:2px;
        text-align:center;
    }
    .login-title{font-size:1.55rem;font-weight:850;color:#16202c;margin:6px 0 2px}
    .login-sub{color:#d71920;font-size:.88rem;font-weight:800;margin-bottom:5px}
    .login-help{color:#7a8490;font-size:.80rem;margin-bottom:0}
    div.stButton>button{min-height:44px !important;border-radius:6px !important}
    @media(max-width:700px){
        .block-container{max-width:460px !important;padding-top:.55rem !important}
        .login-head{border-radius:15px;padding:12px}
        .login-title{font-size:1.35rem}
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-head">', unsafe_allow_html=True)
    if LOGO_PATH.exists():
        c1,c2,c3=st.columns([1.05,1.9,1.05])
        with c2:
            st.image(str(LOGO_PATH), use_container_width=True)
    st.markdown("<div class='login-title'>Acesse sua Conta</div>", unsafe_allow_html=True)
    st.markdown("<div class='login-sub'>Gestão de Ativos e Termos</div>", unsafe_allow_html=True)
    st.markdown("<div class='login-help'>Insira suas credenciais para continuar.</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    with st.form("login"):
        u=st.text_input("Usuário", placeholder="admin")
        s=st.text_input("Senha", type="password")
        entrar=st.form_submit_button("Entrar", type="primary", use_container_width=True)

    if entrar:
        with conectar() as conn:
            r=conn.execute("SELECT * FROM usuarios WHERE usuario=? AND ativo=1",(u.strip(),)).fetchone()
        if r and r['senha_hash']==hash_senha(s):
            st.session_state.logado=True
            st.session_state.usuario=r['usuario']
            st.session_state.nome_usuario=r['nome']
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")

    st.caption("GRUPO FEITAL | Gestão de Ativos · Build 02.4")

# ------------------------- CABEÇALHO -------------------------
def cabecalho(titulo="Gestão de Ativos", subtitulo="Controle de equipamentos e termos digitais"):
    a,b,c=st.columns([1.1,4.5,1.1])
    with a:
        if LOGO_PATH.exists(): st.image(str(LOGO_PATH), use_container_width=True)
    with b: st.markdown(f'<div class="app-header"><div class="app-title">{titulo}</div><div class="app-subtitle">{subtitulo}</div></div>', unsafe_allow_html=True)
    with c:
        st.caption(f"👤 {st.session_state.nome_usuario}")
        if st.button("Sair",use_container_width=True): logout()

def contagens():
    with conectar() as conn:
        total=conn.execute("SELECT COUNT(*) FROM equipamentos").fetchone()[0]
        uso=conn.execute("SELECT COUNT(*) FROM equipamentos WHERE status='Em uso'").fetchone()[0]
        pend=conn.execute("SELECT COUNT(*) FROM movimentacoes WHERE status_assinatura='PENDENTE'").fetchone()[0]
        ass=conn.execute("SELECT COUNT(*) FROM movimentacoes WHERE status_assinatura='ASSINADO'").fetchone()[0]
    return total,uso,pend,ass

# ----------------------- DASHBOARD ---------------------------
def tela_inicio():
    cabecalho(); nome=(st.session_state.nome_usuario or 'Usuário').split()[0]
    st.markdown(f'<div class="hero"><h2>Olá, {nome} 👋</h2><p>Envie termos para assinatura no celular, acompanhe pendências e gere o PDF automaticamente.</p></div>', unsafe_allow_html=True)
    total,uso,pend,ass=contagens(); cols=st.columns(4)
    for col,(rot,val) in zip(cols,[("Equipamentos",total),("Em uso",uso),("Aguardando assinatura",pend),("Termos assinados",ass)]):
        with col: st.markdown(f'<div class="metric-card"><div class="metric-label">{rot}</div><div class="metric-value">{val}</div></div>',unsafe_allow_html=True)
    st.markdown('<div class="section-title">Ações rápidas</div>',unsafe_allow_html=True)
    a,b=st.columns(2)
    with a:
        if st.button("📤 Nova Entrega / Enviar para assinatura",type="primary",use_container_width=True): navegar('entrega')
    with b:
        if st.button("📥 Devolução",use_container_width=True): navegar('devolucao')
    a,b=st.columns(2)
    with a:
        if st.button("📄 Termos / Assinaturas",use_container_width=True): navegar('historico')
    with b:
        if st.button("🔎 Consultar Equipamento",use_container_width=True): navegar('consulta')
    a,b=st.columns(2)
    with a:
        if st.button("➕ Cadastrar Equipamento",use_container_width=True): navegar('cadastro')
    with b:
        if st.button("⚙️ Configurações",use_container_width=True): navegar('config')
    st.caption("Build 02.4 · assinatura pública + WhatsApp + abrir/copiar link + renovar/cancelar + PDF + QR Code.")

# ------------------------ CONFIG -----------------------------
def tela_config():
    cabecalho("Configurações", "Endereço público usado nos links de assinatura")
    if st.button("← Voltar"): navegar('inicio')
    atual=base_publica()
    url=st.text_input("URL pública do Streamlit", value=atual, placeholder="https://seu-app.streamlit.app")
    st.caption("Informe somente a URL principal, sem /assinar. Ex.: https://feital-gestao-ativos.streamlit.app")
    if st.button("💾 Salvar URL",type="primary"):
        if not url.startswith('http'):
            st.error("Informe uma URL iniciando com https://")
        else:
            set_config('PUBLIC_BASE_URL',url.strip().rstrip('/')); st.success("URL pública salva.")
    st.warning("Build 02.4 é para testes. No Streamlit Community Cloud, SQLite e arquivos locais não são armazenamento permanente.")

# ------------------- CADASTRAR EQUIPAMENTO -------------------
def tela_cadastro():
    cabecalho("Cadastrar Equipamento", "Notebook, smartphone ou outro ativo")
    if st.button("← Voltar"): navegar('inicio')
    with st.form('cadastro'):
        patrimonio=st.text_input("Patrimônio / identificação *",placeholder="Ex.: NOTE 125 ou CEL 226")
        tipo=st.selectbox("Tipo *",["Notebook","Smartphone","Desktop","Monitor","Tablet","Outro"])
        marca=st.text_input("Marca"); modelo=st.text_input("Modelo"); serie=st.text_input("Nº de série / IMEI"); obs=st.text_area("Observações")
        salvar=st.form_submit_button("💾 Salvar equipamento",type="primary",use_container_width=True)
    if salvar:
        if not patrimonio.strip(): st.error("Informe o patrimônio."); return
        try:
            with conectar() as conn:
                conn.execute("INSERT INTO equipamentos(patrimonio,tipo,marca,modelo,serie_imei,status,observacoes,criado_em) VALUES(?,?,?,?,?,'Disponível',?,?)",(patrimonio.strip().upper(),tipo,marca.strip(),modelo.strip(),serie.strip(),obs.strip(),agora_iso())); conn.commit()
            st.success("Equipamento cadastrado.")
        except sqlite3.IntegrityError: st.error("Patrimônio já cadastrado.")

def disponiveis():
    with conectar() as conn: return conn.execute("SELECT * FROM equipamentos WHERE status='Disponível' ORDER BY patrimonio").fetchall()

# --------------------------- ENTREGA -------------------------
def tela_entrega():
    cabecalho("Nova Entrega", "Crie o termo e envie o link para o colaborador assinar")
    if st.button("← Voltar"): navegar('inicio')
    eqs=disponiveis()
    if not eqs: st.warning("Não há equipamentos disponíveis."); return
    mapa={f"{r['patrimonio']} · {r['tipo']} · {r['marca'] or ''} {r['modelo'] or ''}".strip():r for r in eqs}
    with st.form('entrega'):
        escolha=st.selectbox("Equipamento *",list(mapa.keys())); colab=st.text_input("Nome do colaborador *"); empresa=st.text_input("Empresa / setor"); rg=st.text_input("Matrícula / RG"); tel=st.text_input("Telefone"); email=st.text_input("E-mail"); chamado=st.text_input("Chamado")
        acess=st.multiselect("Acessórios",["Carregador","Mouse","Mochila","Teclado","Dock station","Cabo de rede","Outro"])
        cond=st.selectbox("Condição na entrega",["Perfeito estado","Com marcas de uso","Outro"]); obs=st.text_area("Observações")
        validade=st.selectbox("Validade do link",["24 horas","48 horas","72 horas","7 dias"],index=2)
        criar=st.form_submit_button("🔗 Criar termo e link de assinatura",type="primary",use_container_width=True)
    if criar:
        if not colab.strip(): st.error("Informe o colaborador."); return
        eq=mapa[escolha]; horas={"24 horas":24,"48 horas":48,"72 horas":72,"7 dias":168}[validade]
        token=secrets.token_urlsafe(24); exp=(datetime.now()+timedelta(hours=horas)).isoformat(timespec='seconds')
        with conectar() as conn:
            cur=conn.execute("""INSERT INTO movimentacoes(tipo_movimento,patrimonio,colaborador,empresa_setor,matricula_rg,telefone,email,chamado,condicao,acessorios,observacoes,responsavel_ti,aceite_nome,aceite_confirmado,data_movimento,status_assinatura,token_assinatura,token_expira_em) VALUES('ENTREGA',?,?,?,?,?,?,?,?,?,?,?,?,0,?,'PENDENTE',?,?)""",
                (eq['patrimonio'],colab.strip(),empresa.strip(),rg.strip(),tel.strip(),email.strip(),chamado.strip(),cond,', '.join(acess),obs.strip(),st.session_state.nome_usuario,'',agora_iso(),token,exp))
            movid=cur.lastrowid
            conn.execute("UPDATE equipamentos SET status='Aguardando assinatura' WHERE patrimonio=?",(eq['patrimonio'],)); conn.commit()
        st.session_state['ultimo_token']=token; st.session_state['ultimo_movid']=movid; st.rerun()
    token=st.session_state.get('ultimo_token')
    if token:
        mov=buscar_por_token(token)
        if mov and mov['status_assinatura']=='PENDENTE':
            st.success("Termo criado. Agora envie o link ao colaborador.")
            base=base_publica()
            if not base:
                st.warning("Primeiro informe a URL pública em **Configurações**.")
                if st.button("Abrir Configurações"): navegar('config')
            else:
                link=link_assinatura(token)
                st.text_input("Link para assinatura",value=link,key="link_ultima_entrega")
                st.markdown("**Ações do termo**")
                a1,a2,a3=st.columns(3)
                msg=quote(f"Olá {mov['colaborador']}, segue o termo de responsabilidade da Feital para assinatura: {link}")
                with a1:
                    st.link_button("📱 Enviar WhatsApp",f"https://wa.me/?text={msg}",use_container_width=True)
                with a2:
                    st.link_button("🔗 Abrir assinatura",link,use_container_width=True)
                with a3:
                    botao_copiar_link(link, f"ultima_{mov['id']}")
                c1,c2=st.columns([1,2])
                with c1: st.image(qr_bytes(link),caption="Aponte a câmera do celular",width=210)
                with c2:
                    st.write(f"**Colaborador:** {mov['colaborador']}")
                    st.write(f"**Equipamento:** {mov['patrimonio']}")
                    st.write(f"**Expira em:** {mov['token_expira_em'].replace('T',' ')}")
                st.info("Quando o colaborador assinar pelo celular, o status mudará automaticamente para **Assinado** e o PDF será gerado.")

# -------------------------- DEVOLUÇÃO ------------------------
def em_uso():
    with conectar() as conn: return conn.execute("SELECT * FROM equipamentos WHERE status='Em uso' ORDER BY patrimonio").fetchall()
def ultimo_colab(p):
    with conectar() as conn: r=conn.execute("SELECT colaborador FROM movimentacoes WHERE patrimonio=? AND tipo_movimento='ENTREGA' AND status_assinatura='ASSINADO' ORDER BY id DESC LIMIT 1",(p,)).fetchone()
    return r['colaborador'] if r else ''
def tela_devolucao():
    cabecalho("Devolução","Registre o retorno e a condição do equipamento")
    if st.button("← Voltar"): navegar('inicio')
    eqs=em_uso()
    if not eqs: st.info("Não há equipamentos em uso."); return
    mapa={f"{r['patrimonio']} · {r['tipo']}":r for r in eqs}; escolha=st.selectbox("Equipamento",list(mapa)); eq=mapa[escolha]; colab=ultimo_colab(eq['patrimonio']); st.info(f"Último responsável: **{colab or '-'}**")
    with st.form('devolucao'):
        cond=st.radio("Condição",["Em perfeito estado","Apresentando defeito","Quebrado"]); obs=st.text_area("Observações / descrição"); resp=st.text_input("Responsável pela devolução",value=colab); ok=st.checkbox("Confirmo o recebimento e a condição acima."); salvar=st.form_submit_button("📥 Registrar Devolução",type="primary",use_container_width=True)
    if salvar:
        if not resp.strip() or not ok: st.error("Informe o responsável e confirme."); return
        status={"Em perfeito estado":"Disponível","Apresentando defeito":"Com defeito","Quebrado":"Quebrado"}[cond]
        with conectar() as conn:
            conn.execute("INSERT INTO movimentacoes(tipo_movimento,patrimonio,colaborador,condicao,observacoes,responsavel_ti,aceite_nome,aceite_confirmado,data_movimento,status_assinatura) VALUES('DEVOLUÇÃO',?,?,?,?,?,?,1,?,'N/A')",(eq['patrimonio'],resp.strip(),cond,obs.strip(),st.session_state.nome_usuario,resp.strip(),agora_iso())); conn.execute("UPDATE equipamentos SET status=? WHERE patrimonio=?",(status,eq['patrimonio'])); conn.commit()
        st.success(f"Devolução registrada: {cond}.")

# --------------------------- CONSULTA ------------------------
def badge(s):
    cl='green' if s=='Disponível' else ('blue' if s=='Aguardando assinatura' else ('orange' if s=='Em uso' else 'red'))
    return f'<span class="status {cl}">{s}</span>'
def tela_consulta():
    cabecalho("Consultar Equipamento","Patrimônio, modelo, série ou IMEI")
    if st.button("← Voltar"): navegar('inicio')
    q=st.text_input("Pesquisar"); t=f"%{q.strip()}%"
    with conectar() as conn:
        rows=conn.execute("SELECT * FROM equipamentos WHERE patrimonio LIKE ? OR tipo LIKE ? OR marca LIKE ? OR modelo LIKE ? OR serie_imei LIKE ? ORDER BY patrimonio",(t,t,t,t,t)).fetchall() if q.strip() else conn.execute("SELECT * FROM equipamentos ORDER BY patrimonio").fetchall()
    for r in rows:
        st.markdown('<div class="mobile-card">',unsafe_allow_html=True); a,b=st.columns([3,1])
        with a: st.markdown(f"### {r['patrimonio']} · {r['tipo']}"); st.write(f"**Marca/Modelo:** {r['marca'] or '-'} {r['modelo'] or ''}"); st.write(f"**Série/IMEI:** {r['serie_imei'] or '-'}")
        with b: st.markdown(badge(r['status']),unsafe_allow_html=True)
        st.markdown('</div>',unsafe_allow_html=True)

# --------------------------- HISTÓRICO -----------------------
def tela_historico():
    cabecalho("Termos e Assinaturas","Pendências, termos assinados e PDFs")
    if st.button("← Voltar"): navegar('inicio')
    q=st.text_input("Pesquisar",placeholder="Patrimônio ou colaborador"); t=f"%{q.strip()}%"
    with conectar() as conn:
        rows=conn.execute("SELECT * FROM movimentacoes WHERE patrimonio LIKE ? OR colaborador LIKE ? ORDER BY id DESC LIMIT 150",(t,t)).fetchall() if q.strip() else conn.execute("SELECT * FROM movimentacoes ORDER BY id DESC LIMIT 150").fetchall()
    if not rows: st.info("Sem movimentações."); return
    for r in rows:
        st.markdown('<div class="mobile-card">',unsafe_allow_html=True); st.markdown(f"#### {'📤' if r['tipo_movimento']=='ENTREGA' else '📥'} {r['tipo_movimento']} · {r['patrimonio']}"); st.write(f"**Colaborador:** {r['colaborador']}")
        if r['tipo_movimento']=='ENTREGA':
            status=r['status_assinatura']; cl='green' if status=='ASSINADO' else ('red' if status in ('EXPIRADO','CANCELADO') else 'orange'); st.markdown(f'<span class="status {cl}">{status}</span>',unsafe_allow_html=True)
            if status=='PENDENTE':
                base=base_publica()
                if not base:
                    st.warning("Configure a **URL pública** em Configurações para liberar os botões de assinatura.")
                else:
                    link=link_assinatura(r['token_assinatura'])
                    st.text_input("Link para assinatura",value=link,key=f"link{r['id']}")
                    msg=quote(f"Olá {r['colaborador']}, segue o termo de responsabilidade da Feital para assinatura: {link}")
                    b1,b2,b3=st.columns(3)
                    with b1:
                        st.link_button("📱 Enviar WhatsApp",f"https://wa.me/?text={msg}",use_container_width=True)
                    with b2:
                        st.link_button("🔗 Abrir assinatura",link,use_container_width=True)
                    with b3:
                        botao_copiar_link(link, f"hist_{r['id']}")
                    st.image(qr_bytes(link),caption="QR Code da assinatura",width=130)

                c1,c2=st.columns(2)
                with c1:
                    if st.button("🔄 Renovar link",key=f"novo{r['id']}",use_container_width=True):
                        novo=secrets.token_urlsafe(24)
                        exp=(datetime.now()+timedelta(hours=72)).isoformat(timespec='seconds')
                        with conectar() as conn:
                            conn.execute("UPDATE movimentacoes SET token_assinatura=?,token_expira_em=?,status_assinatura='PENDENTE' WHERE id=?",(novo,exp,r['id']))
                            conn.commit()
                        st.success("Link renovado por mais 72 horas.")
                        st.rerun()
                with c2:
                    if st.button("❌ Cancelar termo",key=f"cancelar{r['id']}",use_container_width=True):
                        st.session_state[f"confirmar_cancelamento_{r['id']}"]=True

                if st.session_state.get(f"confirmar_cancelamento_{r['id']}"):
                    st.warning("Cancelar este termo libera o equipamento novamente. Esta ação não pode ser desfeita automaticamente.")
                    cc1,cc2=st.columns(2)
                    with cc1:
                        if st.button("✅ Confirmar cancelamento",key=f"confirmacancel{r['id']}",type="primary",use_container_width=True):
                            with conectar() as conn:
                                conn.execute("UPDATE movimentacoes SET status_assinatura='CANCELADO', token_assinatura=NULL, token_expira_em=NULL WHERE id=?",(r['id'],))
                                conn.execute("UPDATE equipamentos SET status='Disponível' WHERE patrimonio=? AND status='Aguardando assinatura'",(r['patrimonio'],))
                                conn.commit()
                            st.session_state.pop(f"confirmar_cancelamento_{r['id']}",None)
                            st.success("Termo cancelado e equipamento liberado.")
                            st.rerun()
                    with cc2:
                        if st.button("↩️ Não cancelar",key=f"naocancel{r['id']}",use_container_width=True):
                            st.session_state.pop(f"confirmar_cancelamento_{r['id']}",None)
                            st.rerun()

            if status=='ASSINADO' and r['pdf_path'] and Path(r['pdf_path']).exists():
                with open(r['pdf_path'],'rb') as f: st.download_button("⬇️ Baixar PDF assinado",f.read(),file_name=Path(r['pdf_path']).name,mime='application/pdf',key=f"pdf{r['id']}")
        st.caption(f"Criado: {r['data_movimento'].replace('T',' ')} · TI: {r['responsavel_ti'] or '-'}")
        if r['assinado_em']: st.caption(f"Assinado: {r['assinado_em'].replace('T',' ')}")
        st.markdown('</div>',unsafe_allow_html=True)

# ---------------------------- ROTA ---------------------------
# Rota pública não exige login. Exemplo: https://app.streamlit.app/?assinar=TOKEN
try:
    token_publico=st.query_params.get('assinar','')
    if isinstance(token_publico,list): token_publico=token_publico[0] if token_publico else ''
except Exception:
    token_publico=''

if token_publico:
    tela_assinatura_publica(str(token_publico))
elif not st.session_state.logado:
    tela_login()
else:
    paginas={'inicio':tela_inicio,'config':tela_config,'cadastro':tela_cadastro,'entrega':tela_entrega,'devolucao':tela_devolucao,'consulta':tela_consulta,'historico':tela_historico}
    paginas.get(st.session_state.pagina,tela_inicio)()
