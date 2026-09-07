import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import html
import json
import secrets
import time
import inspect
from io import BytesIO
from urllib.parse import quote
import qrcode
import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from streamlit_drawable_canvas import st_canvas

# ============================================================
# FEITAL | GESTÃO DE ATIVOS - BUILD 02.9.7
# Assinatura pública pelo celular + PDF + câmera + QR Code
# ============================================================

APP_NAME = "Feital | Gestão de Ativos"
BUILD = "BUILD 02.9.7"
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
        conn.execute("""CREATE TABLE IF NOT EXISTS alteracoes_equipamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipamento_id INTEGER NOT NULL,
            patrimonio_anterior TEXT NOT NULL,
            patrimonio_novo TEXT NOT NULL,
            campos_alterados TEXT,
            pecas_trocadas TEXT,
            observacoes TEXT,
            responsavel TEXT NOT NULL,
            data_alteracao TEXT NOT NULL)""")
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
.metric-defeito{border-color:#f1c4c6;background:#fff8f8}.metric-defeito .metric-label,.metric-defeito .metric-value{color:#b81820}
.section-title{font-size:1.12rem;font-weight:850;color:#27303a;margin:14px 0 9px}
div.stButton>button{border-radius:14px;min-height:48px;font-weight:750} div.stButton>button[kind="primary"]{background:#d71920;border-color:#d71920}
.status{display:inline-block;padding:5px 10px;border-radius:999px;font-size:.78rem;font-weight:800}.green{background:#e8f7ef;color:#167a46}.orange{background:#fff1e4;color:#a35400}.red{background:#fdebec;color:#b81820}.blue{background:#e9f2ff;color:#275ea8}
.term-text{font-size:.95rem;line-height:1.55;color:#313943}.signature-box{border:2px dashed #cbd1d8;border-radius:15px;padding:8px;background:#fff}
.foto-status-list{margin:8px 0 14px;padding:8px 11px;border:1px solid #e5e9ee;border-radius:12px;background:#fafbfc}
.foto-status{display:flex;align-items:center;gap:6px;padding:5px 0;font-size:.86rem;color:#596575;border-bottom:1px solid #eef1f4}
.foto-status:last-child{border-bottom:0}.foto-status span{width:18px;font-weight:800;color:#27303a}.foto-status strong{margin-left:auto;font-size:.75rem;font-weight:750}
.foto-status.ok strong{color:#16834a}.foto-status.pendente strong{color:#8a929c}
[data-testid="stExpander"]{border:2px solid #d9e7df;border-radius:14px;background:#f8fcfa;margin:10px 0}
[data-testid="stFileUploaderDropzone"]{min-height:76px!important;padding:8px 12px!important}
[data-testid="stFileUploaderDropzone"] span{font-size:0!important}
[data-testid="stFileUploaderDropzone"] span:after{content:"Escolher foto";font-size:.9rem;color:#4b5563}
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

def parse_foto_paths(valor):
    if not valor:
        return []
    try:
        parsed = json.loads(valor)
        if isinstance(parsed, list):
            return [str(p) for p in parsed if str(p).strip()]
    except Exception:
        pass
    return [str(valor)] if str(valor).strip() else []


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
    fotos = parse_foto_paths(mov['foto_path'])
    if fotos:
        for arq in fotos:
            p = Path(arq)
            if p.exists():
                story += [PageBreak(), Paragraph("REGISTRO FOTOGRÁFICO DO EQUIPAMENTO", title), RLImage(str(p), width=15.5*cm, height=11.5*cm)]
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

def criar_canvas_assinatura(*, key, width=620, height=180):
    """
    Compatibilidade entre diferentes versões/forks do streamlit-drawable-canvas.
    Algumas aceitam return_image_data=True e outras não.
    """
    kwargs = dict(
        stroke_width=3,
        stroke_color="#111111",
        background_color="#FFFFFF",
        height=height,
        width=width,
        drawing_mode="freedraw",
        key=key,
    )

    try:
        parametros = inspect.signature(st_canvas).parameters
        if "return_image_data" in parametros:
            kwargs["return_image_data"] = True
    except Exception:
        pass

    try:
        return st_canvas(**kwargs)
    except TypeError as exc:
        # Fallback para versões antigas que rejeitam argumentos mais novos.
        if "return_image_data" in str(exc):
            kwargs.pop("return_image_data", None)
            return st_canvas(**kwargs)
        raise


def renderizar_assinatura_json(json_data, width=620, height=180):
    """
    Fallback para versões do canvas que não entregam image_data.
    Reconstrói aproximadamente os traços livres a partir do JSON do Fabric.js.
    """
    if not json_data:
        return None

    objetos = json_data.get("objects", []) if isinstance(json_data, dict) else []
    if not objetos:
        return None

    img = PILImage.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    desenhou = False

    for obj in objetos:
        if not isinstance(obj, dict):
            continue
        path = obj.get("path")
        if not path:
            continue

        stroke_width = int(round(float(obj.get("strokeWidth", 3) or 3)))
        scale_x = float(obj.get("scaleX", 1) or 1)
        scale_y = float(obj.get("scaleY", 1) or 1)

        pontos = []
        for cmd in path:
            if not isinstance(cmd, (list, tuple)) or len(cmd) < 3:
                continue
            op = str(cmd[0]).upper()

            # Para M/L usa o primeiro par; para Q/C usa o último par (endpoint).
            if op in ("M", "L") and len(cmd) >= 3:
                x, y = cmd[-2], cmd[-1]
            elif op in ("Q", "C") and len(cmd) >= 3:
                x, y = cmd[-2], cmd[-1]
            else:
                continue

            try:
                x = float(x) * scale_x
                y = float(y) * scale_y
                pontos.append((x, y))
            except Exception:
                continue

        if len(pontos) >= 2:
            draw.line(pontos, fill=(17, 17, 17, 255), width=max(2, stroke_width), joint="curve")
            desenhou = True

    return np.asarray(img) if desenhou else None


def obter_imagem_canvas(canvas):
    if canvas is None:
        return None

    try:
        dados = canvas.image_data
        if dados is not None:
            return dados
    except Exception:
        pass

    try:
        return renderizar_assinatura_json(canvas.json_data)
    except Exception:
        return None


# ------------------- ASSINATURA PÚBLICA ----------------------
def buscar_por_token(token):
    with conectar() as conn:
        return conn.execute("SELECT * FROM movimentacoes WHERE token_assinatura=? LIMIT 1", (token,)).fetchone()

def tela_assinatura_publica(token):
    mov=buscar_por_token(token)
    st.markdown('<div class="public-card">', unsafe_allow_html=True)
    if LOGO_PATH.exists():
        a,b,c=st.columns([1,2.4,1])
        with b: st.image(str(LOGO_PATH), width=220)
    st.markdown("<h2 style='text-align:center;margin:.2rem 0'>Termo de Responsabilidade</h2>", unsafe_allow_html=True)
    st.caption("Feital | Gestão de Ativos - assinatura pelo celular")
    if not mov:
        st.error("Link de assinatura inválido ou não localizado."); st.markdown('</div>', unsafe_allow_html=True); return
    if mov['status_assinatura']=='ASSINADO':
        st.success("Este termo já foi assinado e o link foi encerrado.")
        st.write(f"**Colaborador:** {mov['colaborador']}")
        st.write(f"**Equipamento:** {mov['patrimonio']}")
        st.write(f"**Assinado em:** {mov['assinado_em']}")
        pdf_assinado = Path(mov['pdf_path']) if mov['pdf_path'] else None
        if pdf_assinado and pdf_assinado.exists():
            with pdf_assinado.open("rb") as arquivo_pdf:
                st.download_button(
                    "📥 Baixar cópia do termo (PDF)",
                    data=arquivo_pdf.read(),
                    file_name=f"Termo_{mov['patrimonio'].replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"download_termo_{mov['id']}"
                )
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
    st.markdown("<div class='section-title'>Fotos do equipamento (até 5)</div>", unsafe_allow_html=True)

    labels = [
        "Frente do celular",
        "Parte de trás do celular",
        "Lado direito",
        "Lado esquerdo",
        "Detalhe adicional"
    ]

    foto_estado = st.session_state.setdefault(f"fotos_publicas_{mov['id']}", {})
    foto_reset = st.session_state.setdefault(f"fotos_reset_{mov['id']}", {})
    foto_pendente = st.session_state.setdefault(f"fotos_pendentes_{mov['id']}", {})
    foto_mensagem_key = f"fotos_mensagem_{mov['id']}"

    posicao = st.selectbox(
        "Qual parte do celular?",
        labels,
        key=f"foto_posicao_{mov['id']}"
    )
    idx_foto = labels.index(posicao)

    fonte = st.radio(
        "Como adicionar?",
        ["Câmera", "Galeria"],
        horizontal=True,
        key=f"foto_fonte_{mov['id']}"
    )

    # Se não existe foto aguardando conferência, libera câmera/galeria.
    pendente = foto_pendente.get(idx_foto)
    recebido = None

    if pendente is None:
        if fonte == "Câmera":
            recebido = st.camera_input(
                "📷 Tirar foto",
                key=f"foto_camera_{mov['id']}_{idx_foto}_{foto_reset.get(idx_foto, 0)}"
            )
        else:
            recebido = st.file_uploader(
                "🖼️ Escolher foto da galeria",
                type=["png", "jpg", "jpeg"],
                key=f"foto_arquivo_{mov['id']}_{idx_foto}_{foto_reset.get(idx_foto, 0)}"
            )

    # Assim que recebe a foto, guarda temporariamente e continua na MESMA execução.
    # Não usamos st.rerun() aqui porque em alguns navegadores móveis o rerender
    # imediato do st.camera_input pode deixar a tela travada/congelada.
    if recebido is not None:
        foto_bytes = recebido.getvalue()
        if foto_bytes:
            foto_pendente[idx_foto] = {
                "bytes": foto_bytes,
                "label": posicao
            }
            st.session_state[foto_mensagem_key] = ""
            pendente = foto_pendente.get(idx_foto)

    # Painel de conferência da foto.
    pendente = foto_pendente.get(idx_foto)
    if pendente is not None:
        st.markdown("""
        <div style="
            background:#ffffff;
            border:2px solid #dce3ea;
            border-radius:18px;
            padding:14px 14px 8px 14px;
            margin:14px 0;
            box-shadow:0 10px 28px rgba(30,42,55,.10);
        ">
            <div style="font-size:1.15rem;font-weight:850;color:#27303a;margin-bottom:5px;">
                📸 Conferir foto
            </div>
            <div style="font-size:.90rem;color:#6f7b88;margin-bottom:8px;">
                Confira a imagem antes de continuar.
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.info(
            f"Confira a foto de **{pendente['label'].lower()}**. "
            "Se estiver boa, toque em **✅ Foto OK**. "
            "Se não estiver boa, toque em **🗑 Excluir e tirar novamente**."
        )

        # Sem use_container_width/use_column_width para manter compatibilidade
        # com a versão de Streamlit em uso.
        st.image(pendente["bytes"], caption=f"Pré-visualização — {pendente['label']}")

        col_ok, col_excluir = st.columns(2)

        with col_ok:
            confirmar_foto = st.button(
                "✅ Foto OK",
                type="primary",
                use_container_width=True,
                key=f"foto_ok_{mov['id']}_{idx_foto}"
            )

        with col_excluir:
            excluir_foto = st.button(
                "🗑 Excluir",
                use_container_width=True,
                key=f"foto_excluir_revisao_{mov['id']}_{idx_foto}"
            )

        if confirmar_foto:
            foto_estado[idx_foto] = pendente["bytes"]
            foto_pendente.pop(idx_foto, None)
            st.session_state[foto_mensagem_key] = f"✅ {posicao}: foto confirmada como OK."
            st.success(f"✅ {posicao}: foto confirmada como OK.")

        if excluir_foto:
            foto_pendente.pop(idx_foto, None)
            foto_estado.pop(idx_foto, None)
            foto_reset[idx_foto] = foto_reset.get(idx_foto, 0) + 1
            st.session_state[foto_mensagem_key] = f"🟠 {posicao}: PENDENTE. Tire uma nova foto."
            st.warning(f"🟠 {posicao}: foto excluída. Tire outra foto.")

    # Se uma foto já foi confirmada, permite excluí-la e refazer.
    if idx_foto in foto_estado and pendente is None:
        st.success(f"✅ {posicao}: foto OK.")
        if st.button(
            "🗑 Excluir foto confirmada e refazer",
            use_container_width=True,
            key=f"foto_excluir_confirmada_{mov['id']}_{idx_foto}"
        ):
            foto_estado.pop(idx_foto, None)
            foto_reset[idx_foto] = foto_reset.get(idx_foto, 0) + 1
            st.session_state[foto_mensagem_key] = f"🟠 {posicao}: PENDENTE. Tire uma nova foto."
            st.warning(f"🟠 {posicao}: foto removida. Tire uma nova foto.")

    foto_mensagem = st.session_state.get(foto_mensagem_key, "")
    if foto_mensagem:
        if "✅" in foto_mensagem:
            st.success(foto_mensagem)
        else:
            st.warning(foto_mensagem)

    # Lista de conferência: exatamente OK ou PENDENTE.
    lista_fotos = "".join(
        f"<div class='foto-status {'ok' if indice in foto_estado else 'pendente'}'>"
        f"<span>{indice + 1}.</span> {label} "
        f"<strong>{'OK' if indice in foto_estado else 'PENDENTE'}</strong></div>"
        for indice, label in enumerate(labels)
    )
    st.markdown(
        f"<div class='foto-status-list'>{lista_fotos}</div>",
        unsafe_allow_html=True
    )

    total_ok = len(foto_estado)
    st.caption(f"Fotos confirmadas: {total_ok} de 5")

    st.markdown("<div class='section-title'>Assine com o dedo abaixo</div>", unsafe_allow_html=True)
    st.caption("Use o dedo na tela.")

    if "sig_reset" not in st.session_state:
        st.session_state.sig_reset = {}

    mov_id = int(mov["id"])
    if mov_id not in st.session_state.sig_reset:
        st.session_state.sig_reset[mov_id] = 0

    canvas_key = f"sig_{mov_id}_{st.session_state.sig_reset[mov_id]}"
    canvas = criar_canvas_assinatura(
        key=canvas_key,
        width=620,
        height=180
    )

    if st.button("🧹 Limpar assinatura", use_container_width=True, key=f"limpar_sig_{mov_id}"):
        st.session_state.sig_reset[mov_id] += 1
        st.rerun()

    aceite_nome=st.text_input("Digite seu nome completo para confirmar", value=mov['colaborador'])
    aceite=st.checkbox("Li e estou de acordo com o termo acima e confirmo que esta assinatura é minha.")
    if st.button("✅ Confirmar e Assinar", type="primary", use_container_width=True):
        objetos=(canvas.json_data or {}).get('objects',[]) if canvas else []
        imagem_assinatura = obter_imagem_canvas(canvas)
        if not aceite_nome.strip() or not aceite:
            st.error("Digite seu nome e marque a confirmação do termo.")
        elif not objetos or imagem_assinatura is None:
            st.error("Faça sua assinatura no quadro antes de confirmar.")
        else:
            arr=np.asarray(imagem_assinatura).astype('uint8')
            sig=PILImage.fromarray(arr)
            sig_path=SIGN_DIR / f"assinatura_{mov['id']}_{token[:8]}.png"
            sig.save(sig_path)

            foto_paths=[]
            for ordem, foto_bytes in sorted(foto_estado.items()):
                img=PILImage.open(BytesIO(foto_bytes))
                target=UPLOAD_DIR / f"foto_{mov['id']}_{token[:8]}_{ordem}.jpg"
                img.convert('RGB').save(target, quality=88)
                foto_paths.append(str(target))

            foto_path = json.dumps(foto_paths) if foto_paths else ""
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
            # Evita st.rerun() imediatamente após remover o componente de assinatura.
            # Em alguns navegadores móveis isso causava NotFoundError/removeChild no frontend.
            st.success("✅ Termo enviado e assinatura registrada com sucesso!")
            st.info("O processo foi concluído. Você já pode fechar esta página.")

            pdf_final = Path(pdf) if pdf else None
            if pdf_final and pdf_final.exists():
                with pdf_final.open("rb") as arquivo_pdf:
                    st.download_button(
                        "📥 Baixar cópia do termo (PDF)",
                        data=arquivo_pdf.read(),
                        file_name=f"Termo_{mov['patrimonio'].replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key=f"download_pos_assinatura_{mov['id']}"
                    )

            st.markdown('</div>', unsafe_allow_html=True)
            st.stop()

    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------- LOGIN ----------------------------
def tela_login():
    st.markdown("""
    <style>
    .block-container {
        max-width: 520px !important;
        padding-top: 1rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-bottom: 1rem !important;
    }
    [data-testid="stAppViewBlockContainer"] {
        padding-top: 1rem !important;
    }
    [data-testid="stForm"] {
        background:#ffffff;
        border:1px solid #dfe4ea;
        border-radius:14px;
        padding:16px 16px 14px 16px;
        box-shadow:0 10px 28px rgba(27,39,51,.08);
        margin-top:10px;
    }
    .login-head {
        background:#ffffff;
        border:1px solid #e1e5ea;
        border-radius:18px;
        padding:16px 18px 15px 18px;
        box-shadow:0 10px 30px rgba(27,39,51,.08);
        text-align:center;
    }
    .login-logo {
        width:205px;
        max-width:72%;
        height:auto;
        display:block;
        margin:0 auto 8px auto;
    }
    .login-title {
        font-size:1.58rem;
        line-height:1.15;
        font-weight:850;
        color:#152232;
        margin:4px 0 5px 0;
    }
    .login-sub {
        color:#d71920;
        font-size:.92rem;
        line-height:1.3;
        font-weight:800;
        margin:0 0 5px 0;
    }
    .login-help {
        color:#7b8591;
        font-size:.82rem;
        line-height:1.35;
        margin:0;
    }
    [data-testid="stFormSubmitButton"] button {
        min-height:44px !important;
        border-radius:7px !important;
        font-weight:750 !important;
    }
    @media(max-width:700px) {
        .block-container {
            max-width:470px !important;
            padding-top:.65rem !important;
        }
        [data-testid="stAppViewBlockContainer"] {
            padding-top:.65rem !important;
        }
        .login-head {
            padding:13px 14px 14px 14px;
            border-radius:15px;
        }
        .login-logo { width:190px; }
        .login-title { font-size:1.42rem; }
        .login-sub { font-size:.87rem; }
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="login-head">
        <img class="login-logo" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAWMAAAC+CAIAAABvd/nzAAEAAElEQVR4nJz9abBlSXIeiLl7RJxzl7flVplZWXt1VVd1dXc10CsaxAAEiSbFfUQjTdQMJZNEEzWSxjTULOJImh8y2Ug2PzSiTGMcShQ5AEfEDIbkQFgaCwE0gG6g0Xt1175XZlXu+fb37nLOiXDXjwiPiPteVhM217qz7jv3nDixuH/+uYdHBIbAUH9EJH5BBP0KWP8jACCACCc+IoDxn3QvAKYvsnKffsHTF6X8WL8gXsX4K1bFVQXH+1felKq7WtNUCOorJDboxINV5U8Wp6Wk/kA51cbqguh/ShXh5I36a/5veoPkH/F0b2sJ6QUgVccg4snmCMDpa4K5TZjvu3+jcfWKrN5atXGlanWzqqex6sgTJZxup5Tmp5YKAKROv1+/nGonQBFlWb0McLrJRShS56ff7zPMJy7pYJ8eZilVuO9Qysrd9/3c97FT8o/lso5S9TOuPiyrDyNiuSgnq4Se+dSYV3feR10A0mjcRxpXal1LuFTduaogddOSWEp5dhVjysDVo6MqW5VxqtzV953+RKVZBRsRgR+ipLGFeTjwVAdk/cnFnkKTk7UoP6/gD8oJJCtSUT1aI0Vp1SqsVhcy8EZlPFVBXPlyqvppkKJ9qFsqIGUoU8WwPKWFaF21IXFwEU6qejWEuS/zT5jhNTdsBZur+t4HDkoT8gO4Wn559ypS1L2V+1obvvKSXFRu7ynohNKd1Y1ZolfwBytI1fE8VfMi8JL7DE/VrHCClareX9wF6IfoD94HJgRAQOR+zAA/FPekkg451VFRTmuzgakD7ls1SaXEd67IKZwUEEyvk1OSc7IGcD/jhx8OE1riqh6eeH5FurC6+GHFVhiHqyOYzRqeGFW8T8VXfseThZxuCdyXU1XPrAz4ijrU9hNPXYFVITpl0PHkfaLCfd9K4omXYVKZ+0npyUr8cT5YdVSp3gmRkoJkWI/k/epRX8P7l7fy84m+k2QIo8yIwghW/yt/30fGE0Lcp2ZSGexTP92vhgjoQ4AKcmuDispJIvrE/1ckR19ZoBWxqsFpOlCbQsn/lTIsxTIkjllbHsD6kfs0ZkUhUFtRqpIImNq9XKv0Y6YBp0s+AURF6VeKkNU6nMCuuuhSkerZRAuqKlVm+YdouZzAM1lRZVRmcYKLZZPyoUqUwanCiKrME88JCoBSIazuLvbv1KswPym1ofhw3Dpd11WBx3KtSOgKM8w+9UmWtlJ+VU76tjJ6qKxJJSBSbMHqYrxQKlGXumpmK2nK2rRqJCoDkv9f1OVkn+kIVKxUB6AacSyvPeWGVE9UrQ4h1J2Uq1J3b11RrO/OCr36mtVnVlpw4lu5p9IxrAhkiSqcqMd9P7mDV+t3H5N0om51EbjyV67Ih1a+xoL7tuw+9TwlkuU9p7zcE+88MYbyQ9tV33wCTz7sXX+Mz31kozYj9dXKilTX79OGU+/4ULBIRZ4U5A/9Y0WG8ps/lEQBAFR4l03OSnVPtv/+YgofatVO2Jzq4v3Q9IfqS37NfSWt3KCwfKJsWHVRV0NC9cdq5WppxbojMqeoq3z/5p9oqHzojac+q80uVT8NbX+8z30fuk/16rfLfW46wQvgVBCrfO6Dwv/qyq+amvt9ThVSP/JhzSzff0jhPwxuq3tOj/kfe1AKGVmF7z/e46uvwVOVqZuGFSTXUZFT+vihpLEqavVuuY/QnFJJvJ8HeB8B0y/F5N+3TlV97v/C09hRcwGBzM6xqGEhPOnO9AOuDOyHu6Heh5qYisZIV4DzfhHR+I1KTOl+kHgK/O7T0lPWWvJoS2WU6o5N775fg1YaWjlVmdT9cDnFk8h5okYf2pJixn8onGo1VqXoX12vP87v93+kgv1seUQdG6puPP2S1RarjPxQa/xDPllAap5xUp5OvfV+dTrNxLToipjqrz/MywC+3+tOs6X73fWvHo7TT/4rLO0P/fzwblGxLVMIq/fUmKlDoPAhpYAfMo9ns0repw4iUs2VYuVpICLl51SzlLjUrkQFWPehViuNXKncKZ8leyQoCiOrErSKWACAJVCsZciHVERqOa0IlPYDIuZgklSYSKu8qdKjk5NSCYYFZHWU4uAI1tUH7fkTvXRiCKBoGsb3nrAa2lYRqaSj/k9d9SgzyueiD3h/cExP1LKI6p1nUctih1BC8BI7ATU4JSnIIilYAaX/K4dZr0nNFgCAtY2nRGIFiouRq4qEU19PNxDqepxCueqW+9nIf0Xhf7xPFKjKdt/fqEht0+/P+SgWkgIqeYQrOTxhBk7NWtpTCJ3VDAAAuGRbiAKEIATPgTmEEEREpBQiK3kYeWxEJE6jp5CnVF2LUmxcNn5c2pfK1YgDIiUsWfXGU38yVlO4KUqJgJWSRhUvcrwSb0flsVJ1uOQEhRNIgcVTQohFss5mKXynt8RyBEVyj67qQgGJaiTii7VsOCkCJ3gWRpUtY1HZmjR+AnzKYmD+Kqmg+0h/paWxSsIlpwQyO6nV/AROn+7hBG2i6LGC/CvAl4Qb09DG+0/WrBqv3ArJs6BlOKt0DpSTFaxUUiDZmhXfvXzHlRGrYeh+Y/XH+NRCWK58mPLXdb6/KJXiAAmNIUtkCJMZkAQwtaFbeU4EAFghw554o+ApU636H8vpvPc++MDMwhHqWdLIYTQkeNI9zFiS8pREbdbKK6A4m7ja+yuWGzFUpeo1SqqYW1hXAVWHuOILeTSzZtYdUexpsmYrklbdl79JLi3eSfeLZiIgVwpRSZRopUoMdhUpTskLwmoH5abmTqhRTPOdVMu146omIEjOTsl4XkCx7k/lCJLFNA/KSscgIud7KoOSIBdXR1FAVK+1LaVu8c7y3op1FDxeCWDnnjntOVaqeAJm/jhIgdVI189SGrN0KYu36Ivkfh1RfoW6JfXoSSF7pQXla92rp5oKCrmIYAiJ0FrbGFMm+yqTWJ45xaxtNbYS4fr0u5AAkPzgl4MfvAdOeBT1T3QeGHXunopJSU2Jo0yI6o9g9Q9K1UC9Vnqh6rQV4M7dg4gAlIs5AVOpaoCAsWJJcpHLK+7zWXX4YoNOpe9Uf2Yg03+xIiIV+0Gqaya5/PRcjQeI2jmwCl7lTSu9dqIrT/xVprcRpIR4kLLmak+VlmGZHllpqqRck9pIp99WAFYiCU25EqtDcmKII3LgKbct31OKj+h5yjur6wNqfOo+PA2nsKIc+mzVqSsZHFW1kWKOicJ47i4EAoxqdELtk2YmYl2GZmWYqs6u52oIge/XLasVo9xFpVEVxxcRzwIBfBBPoW2stSb+EO8lBc7K6qbrAIDeZ40p3mNdhViPZe+7vg9BTiiMSNJ9ZiHCiCCZK8b6IaIIx+sno2v5nuyE5NBtakN6giU9hLklUaYQYMUV11cUBMRsWeLEvfCqsKTXSU11tKbFRmUbg8kbwXhTlQ2eastSxj26Nkm+le/lrqu+JIc9vRsQSBul/QWrg1PqdOKPmnZgBP/UbxhTKk/geBam3N4IviIrSFEFECqOGBVBKHdW7qQqXJialpw49QZQRD2k1LdV/4gOUMVsJMtoRCkRqXAXlMOtdPOqJFaGqMganLL/K9hXhCnqIOlYJMHTRkafKOt6TuOIgq5sIhOIuvezHGmahGRZzAOJAkDAIqgEqywkqCUik9C6VzIslrkLMQYbZ9vGgeR70o+S6587r4po5h5dYSCIKILLvu+6gZkza0gIUQZRIsoW7QIAYAUOTlqAOl4KmBV2SDWaMa6hXRkvVfKd5F0kjU0K/0XoTsMSnaAka7U4cIUjGjcROZ2ZxBVi5c5IIpJqqdi3Gl9P4laLWsEb0GDlCgGqRlQDWJWWaIswYVOBppUKS3laFVPjRuldabwUNRIWnJRbEBFtF+QlC5kfC6gxSLcCqFuHyf1MykrqDjDHhzhLGgAwQxUwyO3QrhWpgggFyHPFtRDW96rYYClIpbFQYFDsVnlLyqyul9ZlRdsQAEE49TvHbkZhUAqkdU704QR4JVqjAT3FlVKy6iZok2VVyABERZzid6m6WvtnRbqKfGTzs1IjRAxBFqHjwKO2SfMTVYPrT3yUMgFOX9KIl0TmZdcvl11NB7SkeGs1+LnREOUDoDArzCHN1B7BHLAmfZvE96ZxVzRBqBexCUT3pmB21UBR2UAVDREpC1ti4YRAhAnbs5FJ35Jdogo4EHNoNdowghJs1X6MZSqX0L5CJMDUPKQyIAjqh0WpwGSD4/eYgZ5jmCvmPzU0QrZA7q34PwQG5Ar4UIcz3yNFilIVAQCIkOJNqnaVkiZ5S+VokIC03/Qd2sOl2Dp9lCFBRnmzZBHSxmWemOUgwWp6j1YKBVGKeCPkBhaHACWaqFwjvSn9JeVfVNGVJAD5Lsy8ofaIkdLtqta1LUoFCYBwtJaqU7E80jqhCgwRli5FQIh9qwYj0ecS8k1+LRZ5K0iwqqOI2SzF21PPskRswmU/LJZ9TQ8ggWnW8vRe9W3q0La+jJD6wS/7bhX2BfS5gu6IiRbVUh1fE/EiTkCURDIUEOGCHCBY401NKhNbUjqUQBhTHaq87GjlEPPIa4dFxNAGqqpQkv/4fGF6mYoobGPqjaI/VBQWy/0fkuEBKgQJ5VZ+SU2DIq6RWAoICOugJVlQalJHAeP/48XKWxFtskpRNfTayqw52cxRBtSk9+qM55u0QATtRe1E1N4pjky2QHWgQPQXTBCZv2tX6SujzlbGEQFAWNRrARCkrC8iwrXUaGfonGCu26nuh6o3k7nM5jP3DQKARu3rTmIAhkyIMYmXYPUuLQwpkx9FVgRAJHU6UCGpcJNCqyTxEiz2EHT4KlMvUbOz2RdRlRA1slKajYDQe7/se+007dhaDABAhNSKohocUKMsXsKi60Ww9pjKmOWKZmzUS7U6VeORxkopWz2mWpZwxA+IipKYMFYlJRcGAAFoJWM9TTdkeI99pkOC6ntH7IoIsULhVToRkl4jmJoFaLVVZNOzhNlZJo2Zql9WhkxyeDP+kO0Mld7EWgAEWIDjy6gMnqQ0ApFsLqKPUARYqmAjighHmYj4KozZPNR6w6yzp2otU9yTJb6WoApaFEspABHvRZNvpO4eYQGNn2ZingI3srrdQWy16qiwrGhwwVPMYwXKnEASgU01FEX4NJMSH2JJHkQebR1TgGxgijnMJkxUzVTfsuelvF605gmgo9WoOAyDcFRgERFmbaP2QM5bQoKCLPqjUhTItpmjC1RBUQ1sGYsL5KmrBQlGCDTAigQA3TB4H4og1mOieEErir/CY2DZDYFLLgFkNJIU262dMrVGkEcm+2ilKVGM0vNYXoUgUcAT0EbxjAHILBp5eXASj2zHojSIZLshUWxK2ldkdeVtaoaVVBZuSYCIBEKIqK5AvJ8QKCpZUk5MOoAQiXCcqMVi/aRuemxBUqCVumS+D6nGVaAbQQhEnWOI9iTzn+xyC6rjVkRHxwsro5OlfaU/YjwJUE7E1yP+qGOdwihqZEWK1hUrpw/oQKQXCWYHszbS8fnKRq1akBgrym53mdnUkU4tLGS5Cs6nBqbsm2IROIu7dnrsz3pAKjyqbKwGCzJ9SB1bYBkBhCOCCwISagkRLk7mbiRgFS7UvFCI1E3FSGKizFDXX1u1UujK9cI/Mn5jAmtMgRUAZlh0PQtX3qJ2QCpVTWZlX2JVaGAYfABI2H8Cw7hCZhEu89iS2V4WUF1ihwkcOLabAAkFJfWrJluteOnqqufeVhIVR4ArqyJx+E4SFkruhZpWqD1qwmRqs4yRVhoBSCexKYdzEChBCOU2Vg3mKPBEEqGJCBBFsSNJH2VcEBHm5DYBQLTfqkjRKKke6O/R8icbVklItpQSG1Nbm2j9UiA34Rlg4XZFenJHI0XjhkAEoARMi5eiSjFkGsdLItSkKGPqz8ocgIIdQQm1YgYyxBxTkMoIskg9jZjoNyTrnBLJBDAKYaJhtdAkQ54olXpVUatTL0omcanTMoNPBUnuZCnp/oiClPik8t70D4s+JrnXIHEYUhoZtSILLyAAR09GWxCHCasWxWnnRFBTD2jBSVr0lyIeAhhLBgHJsedktXV8hhB677U2K5/4N1V/rTCLrvfMyVFW7cGkWYixl2v8UvalFdXwlxaY2WqekKkqlCyRIg7WvS9V4DENhP4tmRPG0U8yhkjlvdWrVuByhQRBFexKwUbRyAqoP629WIy3mq3oQYIKd2QiCRFydBNji1JXlPkSNb9JllNHV/VK0J/n7DNTgyTjKnNJNItcAyohTCBFOoy5B/LAysnrpUM0Fqc8PNch31L+ozZDVgpM81SVWcNaIHPD65HIhC9SuOxMgqhpBYXgE2a1dKPiYEVCkqWpNCmJWayb+uIqZPqeRMd0wrN24CW/KXslAMjKPHXEo9GorXuMI0WeIgIrKXmpd8uYl1HW7q/brMZH8bwMShV/ywQNipeXCkIBgWHwq+YnQyxIytFM4YryVgbw3rPkgGdUWJ2XT++INyMiSpoyqiyiNlgU5yowE0AUBp0P1jvyr0nCJelWGoaY/gkpji+oE3gaGC++UPSq439JjSaBCrHU6U8aipbYX5EuxOaIAAIl51fyiAMCoBCmbMvcHwBAkSSvzFpQ5gDa/0BQz+YUUkoIOZFAUgsLa8ntE8lamDC5Rh6omFjElOjY5YCoaAA79Uue8gSkOLGJCBLX/klBYABCEhAiwuJi55xeREqT25QqkzlfnvDLhj41i2IGZ+w7nUrNHD91ZaHmuavr+WpFQShSkAWLRVCDWTGApHiOWdgwW4UcjcNIvJKhiDCAoKqWIRkjCUykSt+ueTjpC4oA5QyjOCwMCk8ljCIsybaUgabcB6ntVSZCan4yipnJi4JSlFiFMQFEEuQ4tgzq1qvIxOI5MAsbQ6KZMJgQDQBE9acOWSL44FkyPugspbCytyqsXYYJtCBMaiXZEFb4l/0FhcnMf9IflfdQ+aax1li9qL6uvatAWfjDSQ6QTLT2c1XMSrWyMSzAnmIYSdASiCfbg5CCupWZTS8ueFqu5vhLJtz1rZkZVV2Xw0lVu2IHqRrHuWSVknxDNpxl6qcSENSUiyqJOkdNMpmTGLXF1JByU5X6U8tP0qdcf2WbonalmMd8U2FYRbKi7EsmL6iGKT+UhWel60o0rTAYSMotyAkrSyGx+wQwpTkKVGH+9B84nfCqxg1EMNnRyrAXaaz+rex7paUAImkxk3ZTpgU5npPMHGhIvC6tFFqLdSUwKTVGQ7xSGi6aNQcIDOKZK/GPLU1/rKz7iPcQQvBBguAJPYXEIVMnJusQ+UlCTYbkfGbSkmoh+aqyAioRXR1MxXTU+1JbonylwdEMSM4WvtL3eBMC5xRLjuaEUFJ/aXJSrFEqVyE/onvqHqIiR7EvSCVJGFbmO3NMAyA2DVImKEhlOTN8IkS2xBqkzO1MVrT0CagDoaOrw1p0QMlCFrJU/ShqDHVmGeWxxJWpI0TlPakOOmMnEmc9JM3rJAJCCZiyudb6swisLOBS9FJzoN0CGtZGjVNk3zOpuHZorloSxAoAU/kAhJQZC0TxUK0trCTfjZSNfxzcqD+C2cAXhCgmDLLFBqW0mCEttQHLcl/RapSqgIJ7aYLoV1Qyl1BX0hI8rIl57OeimMIsyczosGWuDcxRvLX9idpmVgRZi6MhYZEQBF2GnEoOAW2lajkXFZnVOle0HPQdkQxJeU8sDjNOaZOULkEkYOkdihqYCcApswAacUnlKccuXmEZdb2g8TEp+gRSbGMuDaEeuEIfKmtaGEBl6IsvkBeixvYkJwWzRoLuFAf62GqNAVPqOsTM74x0CFXjPuyTfWHVT8yoV78iozkIiMbhT5SP1asjxYkak1QBV2/JfVwBD+Z3RsTT2Ku+O3WRdjkD48pgJPWELPtRTVemjouAiKxO1+vYRyDK08gqRPkPxSOB3BHKDSH3nsKTpNhiLIYBFdxW+7d0SfJaTlh4gUINVmRehxB1FuGE0GHVLenREoxTA5MdkhM9UVUsEfJsfdN6blSZAf3CDIk6CHIESa1Y7CT1ojG3C5OWSUpvycYWJFryum1JbSUFZyWLC0UIrMBfLbZATFnU9kt+d5GpCNtJFiXn1SNomDcbpEROcLUEDVrkW4sMgGjqGwBAtpC5IA1fUmQOKTuCKP2b5gOieJVJv6KiAEAEeYARSpIXxvlUAQIkoNSpeVd0AUg3lIB7wV3Oxjv1BFSdApBte+oeUjaVzGR6BiT3Q5YtpSUFDSh2kSAgpTwIteVZgHT2N5J1TQBIDVQVL/SedLBF5Uw0ul3BgySDwJLFJsoCp/WIxS5UIZ5Km7R9KGmSnArKYa1FCEWqVP6izCXWoGVL8W5EJCVcRuqTtAPViS/iJrmCSQkwznNnUVlVwxUbBxUwa8FVEFSHW5+XDNgiua4xIzkFUmKnSXm2lhNRppcFQye4ALNXIMUmrnofCnCcLEDGOQ101dKmdkCqcEIOrkf94KpGSdSKtQBQC5MJdhXrzmEwVEKjPV9zAUFY5bkVYKfKVjYp1i3RMygMMwcLGNK8scbVsnCBgmIldClemORCCrAnLcd6qkekcBEqM3IrQI0CgCwafatuyK9X/yJpX7QaiuaQEl1RBQvVXitJSL0a4SN1VeEFuTvyWKQYGWr6cGy75KGUuHAJQSmiAp1UfZ71QRApzR1I1b+5KwqrBjUVorPMkZ9mTS6GOHVVIVpq4FfoRyQH+d5C1bUiyVxHHFDqLVmfta/Lu0WNRLp91cep5Bky7ksuQhuhvaAamQc9u2C51xmQ1LVRUVZPs3RKAbrcQ5ApE8QZ6oRoKgSkEVkBQF5Rl4hM8XWKFNqE2uRgGW7WwY0DIxhXyKjgJr4K2mjEuGuFdotCcWl86v0khUqmWVmtulNFBkWJExRHJ2sXpmFIAylVH0GshsaVi64ns5JXyBMQkMRXl9A0Y5ocqV1qEZYUzVvFb2FAAiqZdmqAavcAsjlV9qUIrmOffPjMkDIpq7qwzHBUoyZQAm8lIJ15Y2lILTaKaVnqs2KDapXqTALmHP5MzYp6wvXIQYpmR3ZI1TLiCDM5jC+isysIEC+LygjU+UGYL6TCi4FWEQIlUaXtItp/eYZH68i5AZDjiCuoASgoClaQeikJhIgawhyAzH5IlCbgCmSjUubYkjJxtX5JenWg88JSjXoo/mHWlxQUx6zzAmW2pXIgMqRnWFKwReCcwZy0KYUHs0wpWEhBCvVpVJBL4yT3PIiGXYtux99Q5bUYniR9BSqEU7SnQG8Mg6sXkgS8Ns0K4RUU50mHdG9286PSZz1iIAQkqglPhYQleKYL10T5R6LrKecIKReQsp4IkQw6ozQEkw8mnOoDLBxAAESACIlU1yXpnqQBymNZhjRjMQgyqrZWuUbaAoEcXUOoUy0KN9AK5m7EfDF/kqhRNly6uh9BB0YznRCVAFYiCAqVxdZm1CMVSgRJq5B1Wrk0OUmfDqL+oI5/jjViWnBdRBSS2cgAl4SOICYmZSHTdqohUYGsyEkFNazhR2X2IMkwZByAvNlXJZfF/86MO80Vx8kFBJAYIl8FWVW8LOSx5ZSUSlbHMCV9aP9HOFMBSB1fkUQsXVuJlnZeJQyKF6khtdrlX6x2Vxqb9D9MKItlzhkyHFX1yWYhqXi2+9p3dapleoeSTCVF1WwzpRBfHqscScaqF0osY0UxQMdJ4kpQLKKgKQOFE6nmSNxwQATjGgtUgwii2w2IMDMHGXrxA4kYY0lFBkAwZTCGBDNEQUCAZfBAJG4ErtHoQdqfmKOjqyZeUSpLv1ZN7bxShtwnJQxaka/UlFqdsBKpAhOIeaQwTn8igHB81CSxREIQjAF4oXpg43CwACIhARFLBEGd4UFNhikRvCy6WZe0BpBlLBGsgna1eUy0IyX+KRxJJZ86PwUAAATIoG5sdmBVSwA4561AJUVQIE5xuSIaylcg4ZO+UatWjZ7SSAChlfHF1YFOLcLSvhyyUQhQ1pDlXkd0lXGotKZh0nfl+uBJsQHQu7ORWOEQ1c3xF6tAUbqrDFQZqgob0nfJph0qQiA53hxjqIr0K8y7vEeJUVbPYttW5D1TFO1WjT7WKWglZUB1IpoyzKyiTO5kgYzp5EQWUVBYOIiPnJPFe1gscbGA42Mzm+HsSOZHMJvLfD7M5zx07L0MPtJuRERrxTUwnuBkQpOWjKXJBNbPwNZmmK7haMK2AWsADRLpwuW4WEcbokRdrVPyqCTJMADWQ6VBGsmzjan/koVXzE3+Qf4jWw4ChBwcN0hxjpOBA7AIB2KWEBABBZBIIGYDiaCwoCAGQCALRGQNWgsCzKzLbkomNxFypGOSRwKrkEnmoVGLowOWZQBzBBLUh1P5h2STIMNlUqbYoVGRM3NRWZViMCtxz3iqCCtaeZICkgJ55BQmEKCIoQY26jn8uhZZvlXkY2VUBYsF1pZlfUUp8quUI6Mq6s/1zIWoMii5QCUN1QdPVHQFHaDqH5ttWnmtMqLaK0aozfKKy6flpfkbSKQhiXYyLGU/5ux9xGCHmoIqryEPVoZtSMwkbvOJxSNIcQa1KAX+i1hg7vMUVowMFRgEiSwZEoBhEN8F71EYF0s63Ie93XBvh+/che17sLsHRwcym0nXyTBIYOEgEgKzeGFm5hBYvMggEADEEriWppPm3JY5c665eME+cKG9+IA5dw62zslkTUZjsQ0aC0SMIBxAIU37UplnouzFliWhSiZJihCp6Ui9J4AEwpJ4i6oTZm1IxpkQEAmYBZgheOmWspzjcgFHRzI7hqMj9J57n15iEI2hxtF4JNPpYB23Y2gbmUyxmWDjjCEAG0IQYawQoIC4QCVC8e+aUGeRk4rRo1QiB8W3KMQzWzF147WJIllys8Km2cIi20mhEj1JzKb054oJq0RfKSEXjVYFUuAvXDg2VVSFRb9l1lCe1l4SzkhYyFfqgkxsFDcR07ob1AlR0N7PDKJy/ZNlz/qlaFhgRDm7CkwIOQyfsNYQHR4tumGgTG+UPZQhSSZrhYpkx7EeNv2p3JgpUXplheyZI+UAWC5JeVEqkLRReSjjK6hMflaUg3Q2GEA5DBkyBkT6jhfzMDvC5dLMZrS/76+9P7zx5vD+e2Fnj+YLI0DWmsZhY9FZtIREzCIIwsKB2QcO3vvQe78cfAjsfeh9GLzv/DAwo7HNdLp26YH1xx5ef+qJ8SOP2EuX+NwFWNvgZkLtGAjiJudEKRlK9zIWKYthRE1jNjuggw5qBhVtUP+MdBqT2CgwIAAYMpFtoIjwEJZLmM/xYA+27/HOtuzs8J27vHMv7OzBbMn9kpklCCGCNdS0MJnQ+bPm3DnzwFnY2oTNLb95Ftc3YWPDrq1BMxIgDqG45aqoWdxrK1wFq7CWxiyTWfZqK1vUQIm6klvQWaeMBzkgqwy+ZEgVUQRlMwlFMxtYlZ0q7ljVoabDxc/Kr86x30RHUuZgfnlF9U9+VuwlFPasprp234o6VW5FrkX90furvhSwzm5Mx8mdLHcigJ4MlImNABjCCimqQEgJbmWsyu7DyQFLEe4kCiUwloZB657QtEqYq8UkdYdOfiSfR2G1OnAksw8B3UEoA0ua9YxcG0EAjbGGkJczv7fHx0dmGNz8SG7c7F59Y/HiS8v3r9Oid61r1lrjnLUmMinUPUCiDxoQxQdhEAjB+957H9iLeAbP4hEYhAE8QAhh6Idl3/eDd+PJ5kOXz3/86a1nn20ffQQeuGLOXaC1DXGOQdiHRDFZ4n7/8XU5g6CKpdccFUGXb+juSaXzopARom76gsaauIKDA4P3sFziwTbeu823bw/vvdtfvbq8cRsOjmS+JAkgYJJNUa8ZUUSCCCMykJmOcW29feiSe/QRevCyP3+Bz1+w5x5oz56Hpg3MHIIKa7J1SfPLmCYqnRhBsSoVay04A0lJM0GP6l0/puZdaWa2wHlmRKev1WNVKlBYbcXOtIJJ+1XPALIlzdWEug6SFSPzlorqAgCc1C+dBKqUCuvKgb5ViVi5mDQsq2CcT1D9KqJSIQjWsBzfY63dmI5DDMBhjn8BAKAPKxuKKFLMu2GoQFKLK41V5pPxtQqXQPTmWCQvK6goVImv5IIVNwrTysNWQgqgId4Vc4rZqGZDq2vptXfSEkoAMdYSWey75b3b3c7tNsgU0N+8dfj1rx9+69v+7l7j3Gh9ai0hcwyzGEIUIGPApFfFFEJhFuHAIsw+hMH7nrkPHAQHloAQRIJIEAbCuI8FAwx9WC7mIfD4zNkHf+TZ85/+1PjJJ8zlR/CBSzBZFzJBAgeO0JiQourTPEYnLCdCjkIkvy2bxSgE0Z4ZMkQGQbjrQhhgGNz+vnzwwfDGK8vXXp1f+2DYPXAIzjbGGkIwCOIDqEfAMXtSLUGcYGWW0HtmHsg2ly+Mn3rcPvEIX7hID15pHnzEnr3A1nnvhVmFW6OR2ZKXfE3IGVurzAKkupbRRBmE1CUnPIiEUmq/u8LVIj6nfxPl8DUm1B5JobLFN8nVr9hFodb6LqxuyKAfB4hzW3WWOTWtPF3GvkBoAkr1hJSPrzYzPakIllQpO4baqyACztn16ZiD5J7/74gUsTrlFVIolhIrKd+y15weLbWqGcrKUJUclOqqdk0iaroDQWx5ypvMmK1yhpFc6AuIyFhDIfQ7u4sPrsFitrGx0SwWu7/zlVu//Xu8u7cxndhJiwLig5FgEAzGzMy0pgARrSG0BEgMEJiFhVnYBxYemD1z56WT0LEEgMDCAEGESTgEQN1+gogR+67vl8vR5tZjn/2RBz//GXriMbj0iD1/ScbjEDhwULObZr1r4yNqHKCw8YQP2lEKsInRMaIxRAYwLI/90RENwygMcuvG4rsvHH3nu93NmxTYjseuccagBMbAIAzMcTMpjsFkKiEAAADC6CWhJRAWltAPvgvu3ObkycfNk4/BlYfoqafax56S6YYPnjlkxc02RqEw+dBY6KO+qzIVmZWkmzNvzNJVmV/IvZRseIKQrGC5bMlWWIWw6DcVLzqrWC2SOfgca5Lm/Wtal5MjoOQNgfLCVOsKazLtyNqxSk0EqrAUlCKyxqzqd8UjpCZTFdTWfspppCgA7QNXVxUpjhcRKfSqQA6iYG5WMmjFF9MrudaV01SQsiITuWka/4jZXGmld/IDK5jWJfxlmiOfMiYIUNbt6jZXsUhjLCHy8fHivXe6mx9sbaxvnDt/8NKLt37hnx+/+e5kbaNdG+PQM7NBIEADYhENQpw6NYQNIhEOIDPhA8/7PhwPfe8DsxCAA3SWRuQaMoDAzD7wwFHbgFE40nUQQOTASEBEaMyyD/2yO3Ph4pNf+vFzP/J8uPQwXX64OXdhYAnBx/HWNquBypCgQpFECjOZ0IBdDFYjEpJBwr4ftu/w7GB91NLu7uKb39n92lf7m3eJ0K2NyVgEYGYSiXMzzIyAJu7EiwQIDEICDMwCnpklLaWKu/FgssMSvPeL3p49u/bU4/Yjj4Ynn26e+xF76UEvMAQfZ0C0LZpfWoIQaVyr2HYyM5IYdpLwaP4hXVePWFBbnUUnUxIAjZJmLEgTQcm6FKqrWq3FVvSg0glFo8plUbkHZR2lmIJ7Ol7aOJDcLjWU+X1RqTOwxgV+IieqUawzFI0rZqOuR8mSqKMUSmKctevT8ephHek+9D7o3akNCSn6IdnkFZZSELmmUlnlExJk7IdSdkXDZKUL9eFVc4UQtyyo+YPWW8mTBs1VdEpOeKqzAAIaiwyLmzcXb77ujvbOP/JQY9ztX/uVW7/8ZfA4ObsFLBK8I6K4vFrEGDQCKGIAHSEh9hBuL5evHhy9eXR8c7ncG8ISOARBBIPUIIyM2XTNxaZ5cDo937Qb1hrgCBmMEACCSOHbCMJCBtA4g2Y567yERz/7/GP/vZ+Whx/DK4+PLz0UQLz3AinqH0e+KgGxpp1ZgLQD8kgZIuqD7O90Nz5ocdjc3Fy+9fb2v/il4zffNkTN2jQnVyISIRoAEkREQ0jGBpAOpAthEBaAEeIYyVBaO+tFhhhHQZEgBAIpvcSEwXMfxg+eHz/zVHj6afOpz7cfedqT8cGjjlk29yuhtSK+K+qlIrci2XqjOr8C9a1YBEQlR93grPtVsDBa2oRjWD9Q+yaZrRQ5zD6SRs0y/YaShFEGBXTasnBtrYiqvZz00AsuKMeqcK2KWWQBS81XGJXcEUVZVzqxeB8TjWiuRBdPrfsArZGOJNTegPZRYmtYh2wV1hLbyfXJP+UhVvvBOsDK3SB3adrnJp+yU8kIgkiVOgmQ/cr0t251KSJirPPzxf5bb4S339mQcPaxh2g+f/u//Pntb3xrunnGTm23XJC1BlEABJFBiBDLF+hA3pnP//Deve/t7t0YfA9gCa0hh+QIrSEkFDKBaB9gf7l8ez4fIz48njy5ufaAawxh3Mw2hioK6iOIgPiAyJOJQ2k++Pb3j7d3n/mrf86wzAaePvyIGPKBS2ws959qSxr8YjrK4DEzGUIG3Nvvrl2F7dvTjbXp2Y3D3/itO//tr/r5otmaAlNY9oiABkEASBHJGIOmF/7gePbq/uHN4+O9rutBhGVE5kLTXJ6MHt6YXllbX3Mtgfi4eh5FkBiYEIWFrDGE3Z174fB4cjT3B0fD0eHkkz9qXBP8UOqam1VovgCU0FwON2RsqTqwzmKCbLCLeui1rKAC0YsigZVzjysx1QyJxMqKEidU1qRc1YACG6DebkEPFWptY5TjPEtbdCQrTflByhfEKj9K1a3MF+VyyntLvGflwRNgejqckRW3uj19r2ZJ0z0ap/BYdUIqphhrAChrk+DUC7WppSoZQaoeWK1PjYs5ZJtrkK5LbmDhNVVoqBIcccYtDw7uvfKSuX7tjLFnHn+E7957+2f/ydHVq+ubZ9l3wAGNBTKGyAKggCEwiCRgQGxD9wb/e7duf+XW3eshsKXWkIk0W6BBbIgaIkdmZI1DcIgGDQP2gWfd0AZ+dm36sXNba0jDELymF+ZURtHUfRRAAmeaYblst9af/it/YfLJT/qHPzJ57LE+cPA+e6mV7cXSczV5E4hbLCMiDSHcuslvv+mO99cfetiO2/2f/4XbX/1a24zZORGPaYuaqOOpv51FbNz1rv/KzVvf3tm/NXgwQIjWoAMcGTs1pkHTBn95PPrkua1nzp5bR/Ixw5lixp3EfZWQmQhDHxDN5Okn+NHH/Kd/bOPHvhjaZggelIPWQqPBlTq5WalkZsyJPZXGqyte/VwJeRZAFbkVYRUAwJzgiACakqM2uMrROsFEMoPIxFcpCeaDeuNucKtymhEvwmCtAplnaPGRSZa4yqrTU3gHrqgP6KxiYVMYUQNgpc9R6VJqb/Q+0qYTBZsBP5RTRKuPJzpbH9UZ4swZdCyLl4AlbJIaVmqeWXJq0wk+lsuo7SQAgi59x3zchrAom2CQtKuAgAhz6+x85+7N771g797ZdHbzoSt8/fZbP/ezx7duTM6c890Cgjdk8iuC7r4tAgJClm513T9774Pf29kZnDWtJeHomxtAC0BoDBmDhIBehIE8i4QeCAQQLBwb+ubR8fXl8gsXz11uWul93GY7Wi1GzQUWAQFkCbxsneXDw3d+6Zcf75drwXco7aNPLIZed+IV4dT4zFS1wckDBxQJQMbgYrl4623z7jsTGKaPPYbi7/3Df7T9ne8261vMwuzjmCBCOj5Hcb239L1727/w/q3X+2Xj3KhtrEEjYhFbazZH7XrbtEDC4fYwvH/j5lv7ez915eGLTSuS1oxL9F+i5Q1ChAJy/Pqb0/mcjo8Oudv48Z/0beu9j6diJgVSANBWgcYGq0UNKXImRakx0YTixuosQNp9MaORoorKrWSwzgCVTVsm+fkgOfW6K+u3ao/rGbuEGSlsqeOEOcejdrSxKFVqgO6QhHmPem0aKPNGDd4U7axCwlBdzs3KSoZY3qXGWnJpiCefUyX+MKRINS4YrVUFKBXKwZTiTpbYMEA9TJJZhlYxD2Cabo0ykE7GRgA9o1BZDOfUmpX2QVyaEHubY7yNR409uHPv5ve+53buTcWffeSi2bn9xs/+3Oz6rcnmpp8fI+h2j0EQhYUJKe7AzYEbQ7e77r969/3f39uVxgGI94HiduIChNKQcQgY0gyo9yAQBBgQ2cuyHxiACKyxt9j/we17nz9/5onxZOj7AQEiBw5xw2+JC6kYkUVYvHFueTR79zd/51ng0bLrAdpLV+Z+SEMoAJwwV4PquTOEmRGBkML+4fzFFzfu3GwRp089KRTu/cOf23vx1XbzjPcDECIQEWIQQIkrP0QEDQTnfv3m7Z+/+sGBsW3bGpHAARliPgazAEsYwoDBGTNuG7L2ldls5+23/8LDjzw8mbAPQChEwmAg+jIpcQkJ59euTXwXFvMjNNM/8ZNsDfsQp9JY1NLUhLoSHcRMFzFNkK1mMUSWgfUTySoWd1gZmaKqChOC7naKIJCWg0lllZWklq6GEoYo0aLo8qqdTyJfno8qrowgAmtKoYUyV4Gg+cyJnoAuytaOyWxCqVX0NlUnIbWw4EB8MIJufFZ7qPpg+re0qDhgESmkjIveXxRRB6hCbdEACWbelZ3JBEn1ohONQejYZUKnMZ7ykQqLQGdVsgHVEisGGO/EuMozxce8D40zs+2d97/zLbpzdzR0W1cemCyXb/78Pzu8en20uTksF6kgiu61EDMRRZgRRGPxIPCXP7j5e3u7oXVBBJiR0CBZJGPIIRKSALBAJx4GQEAwyCKeYZBkr5HZyDB2bhfkO7t77iw/0k4gDJ7ilmJJJLkMMDJgYLbGHR8cv/WVr30MrQxeTGO2znTBExHkCTuRtEFd7BZOO9JbwG5/7+B7P3hg++6kEXflCsiw84/+i90X37KbZ4bQg4mBS0RAIMF0iImIADXmd2/f/blrN+ZNawwxB45LrRBIEFCMNWTMwEKNHUJgkT6EYN17y+UvXn33rzz0yEPtWFji7oBJ3QAFJB0OaezhrTvjIOE3f3M2aief+0JPpOcYSKbHajpUSxVbo7ipjK/w8GTIqyxvJNA8MWXzic9Fm5qnQFKZOdkYdaIhD0u+vZZdyMQHi/6UaCjm9aZYKEDxkqPXKZx/wjJ9m9Ram6bKoJWplDVPHwvkvOsKczS+pVqNAkKZ62flWdH83MZyJb/wBKfIKi0gcVVdsl9JsrMap4HSMqtwROwLhTOlAZCXjqU2gmTfs0Lu2FNpF8yEBYlnQIxzrjaDI81MOMGDt9YMR4fXvv2dcOPGuJuP2/GZdvTBr//G9suvmrWtRbeEdPojUohRCRYGGQQNYsymJvvtvZ3f2ttZNhYJQhDrmmY8Ho3HTdtYYzAeasriB5ZhGZZdGLowDMjCDH1OvgdxRNwP0th9Y1/aP2w34OJoFOKUiQjoYTFIlJsMIMEACR3c3r/6tW98BLEXO/oTP7kE8MgUEy1j8aFYhehYWoHF3Z2dF164dHg4hd5sXrJb6zv/r3+498rrbn2j80ukuPoTAREIMW3RhRJCY8zLx4e/8MHN+ahprGkIXTN2xhIDAId+AAlBZDF4g9R1vSB2wXf94DkYojcH/tX33/9rjz62ZUlYyBgRPaARkZOEMpJd7u6NxQy/+iuda0af+swCCCTUKphFIkfsdP4STppozUjIew9I1q60zAwLfS0aohxcy4uyBcn8ZF1NwYKUxpWwQ2cx9d7sE5XZyqRDUXmAqwO79J44+nEjdFZTXCVr5oBG1SKIZabWIOdZG+VIaW1hLk6xonRdXmYFiY3WYZdE0AvvX2EQESmK+VezLknlK2dBa1VVBAqGoVZLq5ozUhQ/Smvj88X7yjQuQ4y2TU0NZozVYYZ8L6BmWQQfEAGG7sarrx5fvbrZdY3vLjz60OEPvn/nD74hzbiHEJgJkZFIU2RE0AADAwoxhrZpri+Xv3/33i1A5xwAt9Pp+saZdrpG1gBgYBFNYgEAkE3kAF3Hx4fD4ZFfLiMixm34BgFB6FjmIncEX5/PJ40dp/gfSFzTkWOcWXqZEdEi3L12c/OlV7d6GR54YPT0czM/oEldRhS30gUUYARgNoDL7e073/r2xaP5mh3MmXX3yOWDn/+v91541WysDdynniNEgwIIhjBu/yfQkDkC/sWbt+9au3V2Y9qONjc2sHHOWgYRlrAchsV8uX9wvOwJPBJ2fvACQ2BCAB8s2ZeX3cXbt//MQ1esBAhRCEizZVFAkGLwVJZ7uy2axZd/xW1uuSef6n2ihqlHWde/5EBuHbjDLJmY9TKTXHUEAEqqYhKvWFBWSLXwK2G/WqmyuNZuCBQbHadAlNAUDlSGEUSrq0CYcSyrEpZ8Lsy6re9N2gCSQnMJOjOsKI3KzD8BWHl/7pn4NtEbUDFWi1KtTNVK+/spFADgKqdQb6j4JgUVmCsHRpW/OISiQQP1pjOtSpwuwUbajTpjMECKfGU4KGijtiANXim0uEdR1wGAmUMIrcV777xz7/XXJ77D5Wxra6vZ27nxR988mnWyteFDMGpniIEIUIADB4SGEEJAxF7kB/v7P5gvpGmwcdP1tcn6lnVOEH30X9FEqsPx/QSCBsdjN2rNdGO+t7M8PgTvHRIKsDAZYsGFF+PMdZYzs/kza2siwoIMIgABss3kmIaeDhtBBOYPXnt7sr7B3/3u2sOPLJtRCEwIghQkuSssIAgOuN/ZvfONb50/PFwnYJH2iccXX/3a9te+bqZrwzCwITQIBMIgBGgopqwYZhOCtfb37+682odzD1+ebKwb23qi3nvxnLbSsMasrdvReLmz2x0dwTAEgSEwMxMBMBNy09hvHh4/cXT89Ppa8MEhAXsjJq3DIeI440sYeOgPdpu3+Pg3f3X9b/xN3DrPw0AJ/QFj0pcOdbJAMRCYnM4cd0i3xS/Z/1XJSl43ZEOfwAIy8BT5Vu1CdYGy3dW4qGRPItNfldzk0ECpQdJ3QMB0vEdCgbxLu+gZj+o61B9hjWWKxkhKZbMfXllyfVcCi9QeVhc9Eix1jnLlouBx9We0YMVw5Tfcfx/N058KMhWeaoYBgNVkcP6SNL0UIdkTySOa2yXVm5TFpEZmjpNJRgXiMUskhGAdze7dvf3Kq3x4LBJaxDMTd/Dyi3ffveZHo6BZXMlP0d1iRcCA9IIGpDHm7rL7zu7+HuHG2mRtfX00XRdCBjFAaEw2GqIetQCLSBAOQjidTMcj2p/O9raHvm8FTRxsQibyRPso7wd+oOvXrAsgInpQdun8jL0iQEB0uOxuvXdty43MG6+3z//obPBiKK6hAEx0FBHD8fH2Cz8Yb29vNVbCcuO5T4YPPtj75V+z7XgA5rxILnqU2RSLoLAhvL5Yfn33YHzpgXZzYxCcLTsBjNNKifuEIMCE0J49i4jz/X0Jg0CkDum4VhTZJ3xhZ/fKZLxm4v7RcccYAcAYcmMRAEaiYbkwzuF3vj+/8lD7pb+wtC2wJwVNqJSuyA4A5h3daq9WdUTvT9eSUmESGlQfNUFQNMlJVTPHF3U8svjWWpDrVpQlalZZk5jqq1Ea0QMX1cLnG9N6xcJpIJdcFKhUC+o/U71SpDBpERZdU2qSJub1lIVSshQvCnJspLymYERVt+j5FI6Rf1E0wKTXJRCR3qp+YzHymAM3UtMWUFqBOsGR3pmO5cRCqyqIgaiIEJdJJckRQOEIzALALByptwgADn77rbfmt285A33ft01rdnd3X3trsejZko8HJAGE9D+JO0p4lAFhEPECAejqbPH2srPj8ebm5mgyZUQkMtaRNdaSscY4a5x1jTXWWmusdda6xrXOtmiMWDs6d279gUvYtgMiGATEICBES5El0r0gN7rBswSWAcADxB2fmUUEQoruiQgHCQPBAvHWzt787r3D779E3RKYg/eSz+BkBgIcup2XXrYfvH+5sbI8bi9ewOl471d+ZZh7NtZHwSeMh4ejxEPUBQIjC3gJQF/fP7g7ntBkOh94MfhBwHNCMU7HTiAQDQzHzLh1xmys9yJemEU8c5y48SLB0Dtd98HxMSIKMxgUBI57hokws7CXwGHwzHJ8sM9Hh8Pv/C6//ooBCSAsDBi7IpvQJGYgcZGNZJMoVUSsCnyDTpIm50UShUjokHYbL3Q8WzxJDDXLWJLHJOqiERJl71n1sHoWQH0E1I9WSTW++NMo2QUolCGJNmJWIgQ9yg+q8osGimqL5Gu5VYTasmjfFHVyFCTTL0i1XAXHgjyINj2bcz8LXqygQ0GZVGZV9SoIW78+VRkrW7k6GZSJWkG1qo6i0CKps0+1QGNggYO15vjmrd33rkHf46ghlPWRnb93bfvOXRmPOFJIAgYhFZGgtCbCERlaAF9bzHcRNre23GgsxqAxxlqDZMigiXs7oMQdH0AkTc7Hg4WF2foQvPhmaxMIj+/eZT8AoBjjI41GOiLYBrkiHJB8YmNJzItyIEYIFiEmXPb94c722tV3h5s36MojQ8qGRiICROP94Vtv+9dfuYRgA5ut6doTjy+//o3Zm1dxfcOHHoypguccl7YCo2DcGR3vLrvvzRbLrS0vEDjuyq5b5sWACICwgLAxhkU6YXPmDPV9f3gYc0c4R/0QZ4jvLBaPrE/XDQkRiE5g5aU6Ue0MCsvi6GiM2H3lX7YXL/H5B6RkCNYBBVkRsCROMZ8Jq0dOCHf+e9VsFuar9lgKdcm8GCsTnJ7L2IKl2OitVDG8/AACaBBhpWYaCqxiJQCCmlec9aoEF1TZsknGKgQDio+Ycw+rJLSc4p6oSlahHMuoNBxXOq5i+JAKWI1TVAQE8r0IIPlALMkjFG9LsJb5hyguxC5Y4VeKuznegeoVZqLIJckIy9xoDgkl/z0dri4AICGwCAPL3vUPFrs7jaF+GCYB7Hx+fOPmbNbz+np+l+T9iTBODWIAEUAGdoDHg7/ZdWE0mUzXwThjyVhnjLFkjLVEZIgASaj0OABIiNY9hMAUAjIOPri1zaYfuu17FqO2CIJ4kQ5pJtCzAIhPlifF27NLA8KJUCMjkmc43Dtwk7uL995rH35sOQSDgIhevEGa37p99P3vnuNhZJ0Xnj78UDg+2v3d35N2HCikw9fjNFOcBhZhlugTCQtY+/LR0TXEJaIMA5JJZ5kYgrSIFgBRSCKRobiIVmBy/nzX9WG5MFJCdx4ArLk9hL1lvz4dS4oflM1yY3yBJR06PnSdW8ybl17unvl289N/ZiDDzGVTeYFonNVsYs6khiJBulAym6fKJqX7VQCzqQPIYpmnJxVNdCduDVXW3hAqXUnREw2mJGcDU4Z4XsAKAKvUP2FgoTUam1QSoJVJGiG6aCRiSxXkyFpTL/+RaiYgtT8diKdsIiJYCRVXdYBS6xg5Ua8iQYJd5QerjplCgQ5BhqJEmzRoXzlAqSoJJoqvUuOM9q1SJciIecI0VPFT5Vg5B0X5AAuTsUd7O9sfXA9DD+M2LJZrroHD3Z3bd4K1aA2HCAhElHsk53NCAEYRBLMMwx57O542o5aMMdZa55y1zlpjDJExJp7sk2la2pBWWEIIIQQ/ePIGoe+Rms0tv1j081mDQEheUES8wRnzceCpQY7LX/XsHABNlITsp6Uvve/m+7vNtaste0EMIijMCMPs6OgH31/b3VlrGyuDPXvWnt06+KVf6XeOcGM6BM9FQyTOsoAICCMCMRjAmfffmy+O2gYonXaEhEREhEhkyCSykGLHIsJGxHMAM56cO3t05zYxUzruGATREx0BbPvhcmgsGUn2oWLG1YQYoCwWc3vU+K//gf3ox/GRx1i8yjRmmqUiDjWjrQLqqhWqjKAIk+5KjUeEcghiEeTi+UImz8XCJtRQSAIEKAqphjGJfnSp0wElmh+6wqFrydbHRf2lmjZXSYvKvaWc96GykauY+Jqe2x1VKjOnHC9H9TBW1Sx3WiEYoI5S0cjViKZWP7a55vw1e1PboKHbwsky9MebqoKVZSjpgNy8vBl3wW+uQtmpMpB4JsddHmIkUUJgDmyd2b95/ejOLQsyDL14j92w/fa1nYPjMHLEQSuvsWAFPQZJVCYIkCwHvwSw45FtGiJyzlnXNE1jjbHWWGvJmKhDonSNmTntpMneB6QBqBcAhsGMRmZjo18sTMI1QTSDyHGAbQwjY0JFsHMCb4T/aJgQEZkNEQ9hfnxs3n//7HyGbRtCEAQIw/yVV9t33tpCdF0HaCaXHuB33z381gswbgc/pNmZ5OABSqJjhIAMEhitvbHs3ui9H08MIiIhGmMsERlDcWssPVANAYRZYriBOPjgJ1tnlvNZODxwgAxxayxcBp5Zsz2ERT9MG2ACFiCB7IDngRcRQxgCL5bz5urV4Tt/5C5dCq4JwRsiZiQlflGiVNGi+mWWzkl/JIpFMUUVlKhpRHVl8gH2WcvzvL4+qNy+JGtinoRRT131tlqpWTgz6DxbqnOCCAHQQ2VBOYkSCJ3pjdIer5x0GhJTQihao+NT1BVTemzE+Vht3XhRlThXO3VjDl5gOaYNK5S2GWFqxY6GTZ2o+v7aYcvzUVpCfDAHVvWa1lkd1tyEMpJcACWn3+rwoe4IJIUPCDCwSODAAMvFbO/69e7wyFjT96FB6g8OlrfuDSzYWg6M8RS9jBA58TZxLEAEQmAQsXY0nrSjERK1TWOtix9rjHHGGkvJzGKuN4fAHAKzHzwZQ4YQURA9ip1Ow7jlZU+gMXCkrqEd7y8EY5wTgHIsToSMRJoYAVAkzmwC4bLrwt3tS8dHMh71nkkg3LwBr756ZtFNGmMQRmcvAeLBV37PzweY2sCcByAzc4n7jCIwg7FGrHvr+GiHnGlaS9YastZF9mStJUPGpIzO2HUsiT1xXPpl7NrWmb3ZLISQ5ucQBoSlge3BHwduRUQgRDUjzKKZErIjLyXsht4ul/Ldb8HzPwpPPCXKwBniiVRRCSSePwaabZEcVkxJVit+NgIAcElmy65+nUSQAUeybBZbmFS7TLJl1c5+QvWTvkISIdQURU3ZFMiWLnsZmUdj5UiBMhzUDR9WEADzs1lhRe+C7LNgpldlxlRXAOSkBFWlul/qgMApQABbsf6KP4CCgyJ11VMxSKnOVYZs9bhSFTNK1OiVuzUzllwdTMObiorPcvFASj3j0g5hYPaDB2MOd/f2b9/23XLA1vcDoZkfHfr53CdYFmWB6o2JQNpkHkEk5T0ykODIulHbNm1ryDRNY51zzjrjbEKLSCsQCVlJedQcH3wCCUQACCIOxLUjP5mGZWcpua+EyAh7gz8me9a5YYV3ZeezsE6BuL82hMDzvb3F8bF54GLgAYahf+Ots9vbI0IKgJOJ3dr0r7+2/8pbbMe+70MCRJ2lzIQulmtIBJYAr3S9H7etcdZa56whY6yx1hpjjTHGGCIiYyIjEJHAHEII3qOHbvCT9a2jye5weGQRAwsZJIA5w+3gd4ew7hgkAFkV4KSvIskSexZjkIXnXb9+6073g++ZK496ZyAEIiocAYGQIn0AAGbOSivJ0agIKZST1rOR1lhGjmuU+1GJRib7WfdWYSI7OFEScTWQodAVf9O3Z4uYLELagB5i4kwd39ecGqhUqgoeFKMWhbcECkHjGtklySCqIRHQoS/MbCUQUOVoptI4G/1CJGylq3DiI7nNuv5EstZieWfdO4rikcVliMo0K7tklR3V9iEgKEdK8/D6WBIBwTg1KnHOLATvAyIe7O4e7ezA0PcgHIJHWs6PwtAzEHAk82lAKS4OTOYCEIXSScVIiCOirdYdjtrxaGyMaVxjnLPGOKUWMa5JRk/PAQjMLBwC+8EPNCASAImIZ3YgbjTy40mwRyRIiMYaYw0KDEAL7y3EuZg0StpDZa47SgcDoDV98LPFou+7MQGIhDt3mmvXpgab85vt5pofmNnf+/q3uqWXsfex2aTWScl7XN0SC7Zkbi4X14bQnBm71lqTGmgjTqT/GjIGk5mSEBJMeCJAZABrcLq5eTibsYghAkJG7AH2Ce9xuBhCSyYwp3MTpMSCk3lFDCCA2A1Du+zwxRfbT38OrjwcOCavkuoeMOZcLA0BJOFTKlCsD2rugr4naWa2Z6D3QzWnl0hBYeDZViuPFp0bUcTNcdDEv/PMKqhfE8k/5BVMUAh/1AbJvn617iPrqTYXyrSIwlEGCyI9rE0rlZUzZX+XN1eKj4kHSPoNqh9WPqrPeZY0Ey79jtF5SwibPYUCl6B9j6XA7DNpDEYyxiHq2rnMDqpga2F62ovqjwkgps1gAIBDPIZd2AfvfT8MwuFwZ2e+f2D7wYeADBAg7B3ZYTCuiW45aD0FME0OpjZiTGcmAWaeGLpMo4OmGU/GhqyLwQnnnLWNc8ZaY4yxtuLSIMyBgw/BGhvNIAB6CY6DE24C+2YkxmAIztjYTGfQEVgRB+IFCKWIaO1Yl/OfAVh6lnk39CKNsOm7xdvvnO/69uEr7txGP1uizIe3Pth/4wPftIMfBONO4gIpwwcR4yqD9AeyEMEHi8WRa9rR2LnGOWeMdW3jrDPGpLYbS4biOheOCWY+DMMQrSuDDINMNrYOt7d91xnCEJVfYE74zrJ/yLnzhhkQieO0ZhxrzUWKIwuIEJiPZ8vx1ff5lR+0Fy4GJPaBjACkrkbUo+ZRlaQSu0xPlZdDMVhqZjGP+klBRrXXOreGmSkoXVFcSBJa8XMtJ/6To5g59qbSllVfe6Ga+60UVPUtd1AmAsrlMwPKhD42DQXTeuuK3MSyeVWxqunnHNjQftP3ZvwsMyU2GzPRUGdxikqCZQnp1OUmbysPTHVdMSIltKfs1EKrS73T7XVLoMBwPPAOSl6JQMzdjufxeD8M4Wh/dzE/HmM88Q9k8N1yNhFujb4uoi+AxHwKUoOglYkbq07JPNi4260bT8ZI1hlrnWucM8nzSP9PPBoRQJglhGBCCCZtUMwgDbfM4gUGFjtqvXNGwBAZQ03j1gyeH5qtgRvEgMpvY8qCio5kkyfJiC3CMCcZHHnm4dZ1+ODGeDqyTrrbd4fdw7MXz+y/+tqyH6Qd9WlWJ502GvvTAAtg0CkBItOJvDcEWF8bTcbJvWpc5E6RUKRoBZkUFwAJIXjjc+AgOiNuMmmm037oLQAiBQAiGJx5ezZ/rKOt1pmckRyDqlm60nDG4YXOL0fHR8O3v2U+9rxcuATMaf5OiAiJkAEwhjlN3teiFnPIJCKlu8CKAFfMAos6ZUaQAwSZLq7YzQoSspuTwiSQ6DFLviMLeibEFYvPAbo0k1JtC11US3EGCkvK1L+AnVTKeaL2ueLZdqcrWFC0JnigmoKIAKHSSOX8tio/8wSovqAOwgmYyG4I6jgAQPH2yrknFVVY4T8Ss3JONUf9yDQsmfCwRAc1zkcG5qH3gx+WfXd8cLicLygGCIn6RYeLznrvNHIVW8AiBHE9lRjdlEEAQAgRBg5T115xzXuC4hrbjgyaqDzquVtjDGCcQtSYCbOhYEzoVXuCSODgOTjmhqVv2uCcC9xY07SNQRobc7kdn8OeBBwiIDKzaJA1y0PdgSHIrA8DITnbzY52X375zP6uHzd7r9/BRd+MnGyMd9/5IJANaZoxk8bS5YRg0kJSQITF4G96dtO1tmmddbZpmsZZ1yT2FMEiNRYBgIV9COhj+CBOgggFj8yj9fXFwT4LMIJBEkAvsgd4reueE7bxdL4qaBji+dKJdoN4EUSWsCBj3r7av/m6O3M2CHIQMpEJEQAhMhEyGGRWs4UgurWfAJiik8lxrXh7jlBAttxRJ4H0ujq5UZXU41jRpWzGlW0k8eTEOLAodmYuq6E4LCINSj/g1KdE/XBFETNi1BkkILVmZnmHFYWt66BFZjBVI5XvWqlL7M9TmVepNfW1XDgWZc/AcmKOEys+hrHrQO/LjdSSVzqpoljqmyBEsJbcNmYWkUQnwuC977vl8vi47/sGKYCgMew9DMM0kZDUnygE6lAl56qMJHM8KQf4cuMeQrwJMJ5OScA1TUSJyCoQKR4pGusvgQWYmbynxAzjVCKHENgHDiKDc2Jt60I7atvGWjIbiJc4bErTx9Abgo/HdgIwIGtwiNUisUDgMOsGHo+habevvnvrjbdcxzuH++3xYmRo49JDy3s7s+MFTNY8AEcqBmoxBag+sRcRQZzBo4Xft260PmnbtmlbG6GiaVzjYipJDGciRQIMHAL6EGeIGSQwBxbnfe99O51i04Suc4BkCMkIIFqzx2GQMEEbZTcinySAwLgeW3SYWGC+7Cf7B4sXXrQffS5sbGBgESEjMbpiDCV1ZECDGrbTsCfmyYIifyp6mcmIusZV5ooa7BwQhZINlaiEZovkVCuJqpWj+um2SOTiAJKuRQNd5oW1s1QMq2pr/U1ENMESMIXwUgNKuhfASaxINAOzexGBDdTtSyQ9v7Uo3ml+ARlo0hsUKU54FjnsKSd+wdXWxWmFCBAKIDoIUiKt2QPIYFMVGtPadcm9aBUxrh0AAACO+7SwMOfwe/BDGIah7/qu77vBN46DMAQW7zkEz2nvikjCGTgGNFPnx+WKhAE4pkQaMgs/XDT0ZOvu9t1oMsEQjG2stc6kZApjKIpFkiQbT0EPKWtJkvsexPvAnjkANI1jZ8cgk6Yloumo2ez8JhqH7AEcEQsj4lB1kKQjgRL/ZJYwhMVyMTl/wQO8+c1vLq7dnJIN7C82DjqUZnr3lbd7EEEIwoIUNYFBSP0aQhIBBpC0qBB3l2HWjEfjsWvath0517imca5xjY3TH0SGTGIgzMKGkTwkfiHBhcAcfGP84CYTOxrzoks73rAIwqRxoQuLftgyTRTP7IQCxG0ZMKa3AgALCoLnwXaGX31tfPMGTKc+sAFBgphiTkiAgsiARleRxnCwkGYWJeuk3ViEWUrfQsnoyqJZ0fNidDEvvcjhiVpDVPtFjVqynDpyCQG18KyttSktRriuTvTvypyLvgAylq08XuotCoIFOKSqf1K/nKoh9YNa5OlPuqxIsQoT6d9MEKv+KeAjyuziyCgZKzNMiClOGSMuVdhZ/cY0v6E0TpEwxzLLumrQZDBOn5h0FYIPwQszig8hMIMhABkQPAohcF7MmNhYHL8EcnFPGYyybWkxiOfwyNi+G4YlSDuZIGDrGoPWWkOGyBosTERiKC7GKYgoncUerRKDiASAxlpwdp1w0rbW0mbTXBDaAJYhWGYPabaNUQBJgDGe08XClXAcDcOuNecff/Te9u13XnxxazY7cmbEvPR2+sBZg7h7/SY3TUDmBASiExbAAka/ECADWERCuecH3Noaj0emaSOtcM5FDuWsM9YiYUoeAYw9jhTXqmOIvI5ZAje+YZDJ2vr84JAAQcQaQ4Bj68zQHwfPkOhkXJimjBEhHYACEcsY0DMQB7xzp3vn7eaxx8RYZg4BCZEARTgSQ5VdjTNhWj1dVFA1ajUAn6ciQGMNBZ41clFMN1QDnbVFCwIAEI76rPKcH6h5t8p79gWqWyAVVWVA1XUt1UjKVZWJmTCU+lfqu+o6nWRVNTTl51ID65XNkPkDCsj9Vp1HfZKK82TUKf5DyZuoksYTZUMBWe0QDW2KxuwKn8g+3QoMQ1xDGq9wPKGKWTjEcIXEiGZKGkRELzJwEBEJAiI9ogdB4XgWp7AgQa6Zzl2LQNxNGvSAA9w9OHjk0oVnps0Lx/vt2ce5DzZG+IyJsUzKcSwUADDC7CnofnPRP4mxPhEIIt7ZxroN58aNnYyadTQPAGywPwxsLLEwC5KAIQRmBGKEeCQPZcZIsD+Eo7W16eVLV199ff/udtPzzjK4gGPEBx998PjOrfnxwq2vDxwY1e2IrVV6LqI5VwAC2LG/44OZjpumtU3rmsY51zSta5y1Lu6CZ8ho1hUyC3NK8kZWF4uFPTvrgvBkfWNh7sQON/E4EA5ozH7f+xDAmCAS/YYsFREL4wkHAhBIGGARghsWx6+/sfW5L8jmFnOgeF40SVw+olvl66JQyPMHGpHMSp/FUj/MdQgi63D6hlqWxENeVfxWNDgOfJ1vqpKQ2EGxhogZqjRQkouqg7GlMpVNz15NpbTVTEn8sZrTFU1Xry9lTpFVr6hdrhaA3ln9oq/MDQMEW8HAiQ+W+3P7BeokFZASKFLno56iBl2ik30TZVsaQI9/VYGdqi0CceInws+JT7qNBRHJWkGKK4WFhRAHa3pABDGZgDHUopDejMAaTfEc0JijRb9/d+eJyxe3ud8b/GRtjQI3zlljgMia6CdhCmjFmAmZENiQ8URDtH8gAhIQvYgnR227aWlEdqN1G2IutW6dw7GwRSsigTAEsYBE5IVBgChOKgIAMkIX/Lbv3KOPQ+s++NYL/uh4MGbBfLwcZDKZjNq7t+4wIgMyxFTwjOpU6VSSCQAhhGXwO0ij9bWcg6reh7POkaG4zIUw7qJAIhJ8OuA1rnj3EpwE8c63jZcwXltz4wYXS2OQEA0ioBhLs2XXcXCxepKyBov9iBv5iAhAPLYqiJDI8up7YW8XNjYZQEAoG1qKyolEAnHTOSoiX8SycIEkRav8O7qfkkqLBVUSn9GEMQaWta7JHEoxdZiCqYR55iRHF1KqQyr4FK3PFYoKVTOcUvm8ZlnnsGJZSVuSbVaKJAUns96W90U0qQKXBaxQq17rY01fAADA3hcmIicvqFmltWV91ozYpIcascqPKXbmqYxMJ0qvZRxLo6kN0RBH4hgS070VJApesAgikLNAFDd3CMIWgI0dAIkZEXyJMmE8L08AggjFw0ZFog8vAeJGj3dv39t6cPcTFy58fXubpufGLRtAawygITWraopEREIIxrCJidwwJMrBwoLeD4LcOrduzXrjpsadbZuLY8O7uxYRkEKcIyKMrgExgiAjJ2lgEIvbXX8b4NLDjxwez29evSbz5cygG8J06d1o0jLu3d4WYz2ELMuJk6edoCDurc0shgWBSXDW9TNLbjI2zsZ5D+ucdc42zlhr0vGMSGQipseEafFBRBpmDty4BgSgBc8ycJDxpJ1MqesaY5LAggjSPMi879fHNjALoh63GiNIaRtRSeY77XNDYMOde8PtO/bhx5g0EbMi8GQwexui2oQV2Rcl2bl8Vcns+UDaBCibvKJBUn2RCFUZJZRAnFQnAMEs15FNaC+QekLqMgDEGV/Vy5g/IFprjU0o7VLrljaLK7G/BBYJJKUsSMOsN4hZK9VLyU7WiRboDFG5GB8o+HXS+1AjVPM6fQALaucC0v8TpIHuS66LZ6FgF0LdUHXmqhCOwkaZgE6ImRouEWXSkKUkeRFA07Zgbej7FHsjksYuDQbm1qLPfatsgkAAMDAgCBEFEBIAQB+CNWbehWtvvPP0lUufunD+jbvvt08+zcOAhMYZQDREBEQGk3sQhI1h5kAhrgmJs4oCPBAPHRmQ9aY50zYb1q637aULWxecuf3iq601AmwAQcQSehHPTATxsM8oAIy48OGdRTfb2ly7fOn2nZsHO7uu7y1B63kY/NrEsfjZ3r5rpoH1dPYylLqQQLll2qAYce6HZTMZjUfGOmussc46pwncxhprjAHAlKAJENKmemmgGskRHwkSvAQAnEynw9EhIZKJCQ8gAD3AMoSJSNzjSzTvrgAExvCOpP1rEJkA5ov+5g0bOrQtICPoWhuIe3FiZBMKFkIxOEMgwsBxQ6DkmooSmSiIhgxZgwJUzgMBQuEgMYODo4an8Jgkc0gYk4KTVMeFK8ofCMESEZEIiw+IaJwRQgmeBAJl/dEAR4UaiMiI4n2MaokwApGhzN2Bg4QgiIhE1kLGIHWfVbEq2oLVdIlEYg+YQ4xJU5PRzgwjM5ES8Cm+zP2QIjMcVVed09fYRP3JyV8xMUJhNy3OyfCWoUGK76TMsCRP5PXBSU9ixpUoO8nzo7EYERFMDrNrx2iNXwQyNgijILTtgswy8JRMLzEUkDw/AUhh8ui/scSsHhJGgQBMTbOzf/Tet1946md+nJx59+rVjSefYvAQpHEubmltlJajlbgJV6DgjTGUMhpF2HMYQjCDPzMen5uON4GmZzaufPQJeOc9OZq7ZtqHYCWdGE6IRBQkxFNOmCUwCMLN5fJdP6xdedib5vY7b80ODyeBB4TAwMKb043Z0VE/DM3YMHsdsdT7mVsrrQABCQKe5WgIfhSXzBrjHEJkSwaRrImzPIaQkCjpJwhzyEMtagE5iLOhcUEER2trTLpUBAQFvWBPNPd+3cdQqw68ZFOBmgENakWZDQGHxfUPxssFjEZx+krUb4pNNFWs0hBZASRktGKIjDNECEgx2hA4xNR2QiM8DN1i6AVA4ghKBDsYjdpmPBIkL4A2GWyT9vaEvgsc2BrDzKy+BAIAS/S2ALnrBmPMaNoIwHIABhi7pJN5NS4oWzCqGl0v3HXt2jpYQAYrslwu530H6XRKbNpJMxoBQPC+75ccAoIABwIBYyDH/gpMAOddRTm9N2cxcu2ZobI0LNWDGhtWL3zoyUDJX1sNyVTOUsGgapwhv1ZjGxL/0Kz2lYpUlYzOCUZSqoB3qt6SL0haFyIgIs14bEajfv/QEcekY2rconGzvr9ISEGCsk6BavCURwoDUiwbQSQI46i9ceMOf+WPPvpT/1o7bt9+7+2Np55GR973zjaWCIAMGRCIfrIwh0AmkI8LSIAD+6Ej13dTC2enkwvj6Wbr1p57+szHnjn4gz8wMaebdVKeUEAMIjMSmSBBUIThiP2L89nx+sYDlx88ns12b9/ul31r7cDMDJbMxsba/v4+xr2DIbUw0tCMhKD2SwBZ4jQ/H/rA49a4lKydPkhRzw0ZMjb5WZTEDBEBKe5zA5DW1gELSwjMDDCaTJfWEkYtTXEcDzj3zAABhNPMRRGwNM5aV5CY3A5I2N26LUdHuHUmxr4iyjCiHsOWHG8Jsn5m7fX/zz8++q3fnYwaRBNzR0zTgiHkgCjeOhQZWQTfT//UT0//1Jd849gzkolUYW0ymb/wg7v/8itN6HgyptZRCDhfoF/AcumJ2j/xBe798Q9ewTAsu64bsJmMnSXwvmmJ54vw6IOTv/CX+1vbR1//Q1hfD5/8eEsw++73wtFyID94YTFCQADkB/DeOHESBpbxT33pgR/78Z3/5p8c/+4f0cTNjZv+yT+59af/5OJ4Rsa4xi2/+827/+2v0HxBn3juzN/4a9i0wQ9+2XWLxXTrjGtbZlb9gaKSGuuVDAoioOtWyxwQZLqTBwRPDFDW2RWkSAbdZB9q5SHRjBTFiXitpJEjaqxBFEuUMCQDkiM3iKBnlKWIo6RdZEHJKWI630M4kRfJtkyfAEQJ3DSjZjw5DB6JQggc2Bi3aNqdrntUgEAG3bNQEnClfZ8Q4pxI3A4WBZgE0kIfa6+/d707/u3nfuqL04uX33zjFfvYU2tntrrlUggbZw2hMGqCoFCcAAEAFrbOugGHvpkdX5yMLq6tbVAzeujy+T/xk+HqO8s337OTSRB2FIktAAIJDsBAxBwCICMsSH6wd3jV+8mli8Ga2eHB4c6u9z5Y6pk9w8g1Fmhv98A0LQurRxl979jNuhQ3kdXU80Hk2DO2I7IuLqtIm3nFRCskMhEkovcRTS8QETLHvYBADQMK+xC8D565HY2scziEmFjJARigF1n6MDAzmlg71IrmyHwOJKAGRdDQsLM77O20Dz0ESMxsxMRZLyIjLJwP8AFGQP+NH8Cv/Ao1TYdGIAgIAcYTZgPz3f7YtmsPTNb94U1q282f/lPejL3vDCIGJhYjcPO//qXD/+I/P2cn1DSEDCLEYlEgLIflDN+6fnx4MP/m18aTLQ/ovfcEBGBRgiOYHcqPfNo/8Yl7v/prwz/9R+sbZ9q//JfDfDb88pfbySYP3i/7wEEQBmsZjUG2job53nzrgennfvro97/53r/9v9+cHQ6Gjnnphsb9xT+72DukpsWj+fY//cWjn/v7G2Fj9Nf+++5/+j/p/WDAoDED5sXtxYzGPszx/hS1UJcgCmo27RoiKFMykP1/UMpRgcAKUiDoFC1KHS9QzFrBn2rSJ83eQ1mCn4Wg3J+OC1TyttLIHJ7BXFuQ6GiwxGLTZrQYr8XlpAIiwXvj3Gh9jQkHPwigBI+ENGrvzmHPD5vGdiKQMrsAUlJfdJLrd4LEXG+QuPk1uubWnXuLL//Ws5/99Cee/si7r/5gcfmRzSefZILBD840ZPOMKWLyOxCAPQdi4cP9jeAvrG1sTdfcZHrmC18cP3Rl9+//P+zRktfXqR8agwRiEIyIJzQBu7TzLjCElw+OXpgv5OKF8bmzw9B3h/uzwyNG6kAsgBeeNC0Gf3y0sM7pBh9lAjCjbvLvIRENBGDgWRA7GpOJqzriP+lfSsssiDRHM04wsDAwUcyCStPhAsxN8MF7H8JoPLbWomdDBMJIMWyAAwfPMX87BhHTQocceNJ8xep/hHx8FHZ3hIMYzXMXloACJCbG91JUe/DdiIMAGTaWpIuyym4GZjFpF+c2p89/7Ox0Ct97Sfa2TTNhwHi+rIAwBzeadLduL3/w4qQbYAg7s3sIEsBYkDG4AY7dlacnZ87z2+9SZ8FBd3zYgZe4FSDIGtpBlmeeeCps3wl/+M12LvbBC25tuvfa27ODw2YOw9CvN9OJGYfBH85mx7BswWwA7sB866/+ubVzF977D/+j0cGddvIw9rPWB9t59gFRXGP5vTv+hRfbgfD8xcmnP23WxrK7tNYZg2uuQWtyzCMTiqTuqmgZlLPiKaBkCw0ab9Ef82OremoLFFRvqHUYESHPQOWYAqqLU6/GrzmBEp6MFfGJEv9I8KAkAzBSbkiR8BRQ4pW5jhjtY2b2HFgCMwcOgNBubKJz/dGxaZoQAgRwbbvn2veX3cetIwYWEcoVTtsdAiCzUNrkJutaSigUgzJutmeL7/zuHz5+48ZHnv/4gQ83791d+8THz1y8vFgcM4ttXAoYkgEE5gDBAAPv79L27S0D56fTlox5+MrWpz91+M9/YfGVb66try+ZDRlAJGYHzIQDgDEgTMHCsvcv7e9/8/B4sbZ24dIlsC6EMDs4WC4WztmeYYTYeR5Zu1wuF8Ow1jRx2/FVVxOT2OhGjnHODkEGkSViM56YdG4aAaLurYG6MZ4xxhpCNJgiZHHGGQHAsrBYDmxDCDbtUW6sbdE5WPQgko5jCygAXjhEkI+jHA0GKglNs5UxUB9rzEgUlovu3nbrvZBF5hBPACHxzDaupo9JDSI+eE8SjPNkhLgPMKxvwOOPn/nipx598smrH+zYRy7ju2/jYmHB0dqaGBsz5Vk4hOAmo8OXX4ebt0co9NjDl/76v+4euRL2F9YZ4eFo7+DSX/wZeeMN/3u/0zhLjz289ie/uH75sgVHowlSgBAGa85/6Sd2f+nL/tq1cXN+uPLQ+k//ia3Pft7+xJ8cf+RSePOdg3/6a3jjDpJb+zN/7uKf/gIsFn6xHF28dPYzP3rj5/6r/qu/u+7OLL1vCBGMNyggZBAMzK+/339wvcX18NjD9ic/F3uQCEWMNYarhA/17VMemq5dqdwRVeQo6Fz7B5C5hkqQKm+yNQAY97xadVSyuEk6+lt/zmsJstmvCs1QkGCpokDqgmqmQUm6hxJ+lRLVVLzAAjOKf6JBcpGg+7oz+BCa6bpdWzve22vRxPxBaxDGk+tdd4XDGTIzDgjEeeoIQJIhFuC4r0hOstDOC8xI0jTzYXj99bd37u5+5FOfeOqxR+784Lt7Dz9+/qMfRdfMl0tEMNYiM0jwiAjIi9ns9rVm2W1NNvB4NrSTi88+O3zta4d/7x+sURuXIRsiQQBLiDErSSCwIeiWw/d39r99eHw4Gp998LJbX0MgFFkez0IIrnED8AAYEIjwoF8GoqBDk6MUkCiYZgxod0cfLDCzwXYySTnbNoYhTdwUL2JHCkxaUrYIJBJIOO0+alnEskgIg7XGOjLeOGOd43i0HgKRJQGDhEiM8bxo7d6MyBrBKpQ4jrIBYN/v7fDQkxsFFmNED4glH9jG7e2EASEEHgJ3DI2RWSfh+Y9d/LM/tR2CPHjuzTdf/pe/+Tsf+fGf/MTRbGsx80RkbUyBBWARQkMkcPjdF9vbOx786M9+6dG/+3fsxiR0nghYxA++WZt88M1v4sERSxj9ub/40H/0v8XxCAGtIRRYdgNaHI53Zy++7GZzbEbuqY9Mv/jja8369KePJ+fO7P3ab937x//ChXv27NPn/vpfPfc3//Jsdx8Bx+fO3Pon/83ez/7sOrT8+c+O1tf63/htBA7cG2Y3GqMPR6+94Xf32tEIH324fe5jYRisMdn0p/hfMrpq69TiqepgxpHU/3pZLX7hDitTHQUL0g1Wip6vfGqHp0SQosureh3nHzJ/iYQ0AZjCRs4FScJc8uUzHGobodRFmUQW+kIsYnpm/OKZBSB4du14dOYMX78x9H1KYWJp29Fh077XLTfHUyfYCxOaNI+fPgwAycXPM4wpTBJjMCwE0BhPdH3vYPb1bz106/aDn/zoYHhvb7994umNxx8eQtcv+3QKCaHvlntX38HdwzOu4Z2dQ2ue/dd/iu7du/V//U8m+3Ncn3rvEQwQAFEKETIQcmPMzvHsd+7e+4PD4+Px5MylB0Zbm0DOILEPi+MFQtxhFAIAAA4i24czNCbOBVJOWskkD6J/kGYK4pQRgjBzIOtGozQpimlaVHcVRkpL4agwjhhsFiHEmCtlrHAQNj7OqyKgMdYYy7UgIYyca0SYIU6HRFugO6dGgdfdFqSkTkWXs9velXnHY0CREOKep3GtCCIwogCzAA5efGBBggALZx/5y3/mVjd/9Q+/vlz6o+P957/0p5/8xOf8z/8LOO4cWGNcdItAJIShacd+Z9t//9VRN0OYOuPnd27ytnGO3HgqaOjs2eX23f7bL7RdMOsbY5LljRvd0QEuB2sMkg2bk+kzz85feS+88m4LGCaT9U9+CrbOHN/ZwcZ23O18/6Xl9vYIx/TgFfvM48fMR91w9vKFo++/dOc//8fT5T4+8PDG/+x/0A54/dd/wwLA0MHg7XTsb946euFF67t2/ez4qaeaabs4OjJkUq9JXr6h/VhpK5bdkSoVzrGhnBVV8YgVmFgJgKS/7WmMqEcalCfmv7MHUfxLyQEIfUTNsgpEbdqiW5XnUIszAxkTS7hLFCIi7iiAsAQOQfSIcwGwtHburJ1Ohr3DxjgB8cKGwEzH1/runO8faZrBe0EgBp1ALPXmghSoVUhNgxCEwRBia+Zdf/X1Nw+2bz/07NMPPft8f/Xtve077RNPrD1wdrHsAKlfzLevvtPfuDWeL/vj/TPnH3jqz/95y/79//TvjW7tyNpaH3oABCtE4AwEQGaJG2m9vrv/qzdvf2vZDevraxfOtmc27Whkm8Y6G/rF0C9T1AAEAcnSwHC07AhNUJyNNY7mIm/NkTi67kUKAiziybq2NcYYKstGjY1IYdL2mYoUhBF8jIlnsoogicHABkOOZCASWbImjno6zDDgxnQyjoOW6pOS93I2QBz4FAJPVUYBAYJhb8/P5/ZcYMG0u3+AIEBxJz4UZBEiL+KB0drjvlt7+mmeNP/yn/+zRy9fOffIxaeeeOqpz33yxpd/G99826LxEoAsAiF4BBHmdjLuX3ype/dNBzw+c2Hvl79867d/xxjTjBrsh/YLn3n0P/4/+/euhRe/PxY/Hm8O/79/duNf/nK/8NhOl+IDw4P/7r+z9tFn5i++ZN6/B2DCw5dHH3+Gfejnh+PmbHft1vE3v4Vh1sPW+Lmn3VOPHO/sjiYtX7127f/yf5PvfRNgPHzus2t/4acO/tlvmHYsoecwiLB1zfHVd5cvvrZOROc3Nz77KQAAZjCUDGf2D1b9+xz3qZSrBORU1+LtGmLLcbpTSFCneeaI5ooXUj6SUV+HGxUsZCUOoTMjmYxgmbkFXe6t78jehFY4rnNUVNDfQXJYMzllMRQVs2pA50KilZhunpmcu7C7uy88CADGfVaM7drR27PFBpkpmWWcqYtcCDJrT43gDGiZlEXvmtNuQmAhAO7u7c+++71z12898SM/+vDTT+299erR3kW5cGFgvvf++7vvvsvb90bgn/ziF578wo8t3nj92s/9U3djm9amfRgMxLCIgABysIhkce6Hr9/a+Y17O68P7Cdr62c3RxtTOxo3o7FpHTnnFzPx3qWMJgQWQmRhz4AUt41KTchnZCmwAgIEQAAxMc7D0rMM1ri2NSbt60XGWGsRTVwzTmhMCWdiPJSbEBiAGQ0SI3I0R+qcICIaRBO3qUIEjFt1T1zT4IKZTTICuV+V+eT4SvFWE+kbDo+G2ZyGAICMGNM5DCKHALUHGQIB9xKcGRszfeEb3734+EOPPPVs0w/t9Q+u/d5X8c13zvdBDAUBRAdxdaoIAThnj196Pdy8Y9q12TAcX/vAQGcBBPAIZH19isJHL7zUvXd92o78bOZvvtsAE4CHEcIS1y6MN84FGQ6+823e3x+gsU89YZ98eDha4MBN0x69eW32ylsGeBivbX3i48N0ZA/maxCu/8P/svvVXxszLJ755IP/q/85nr8y9EvbQOiQlwsUsMhHL784vP+BsU4uXXSfeDqw2kVdKaMZeurVReubgxM5JpH8FIjjlQBB/ykmXiNHUPgJ1qkaVos9iSYZPopSK08pL0zEoWYBSi3irzl1TGc3ciGxxGRPirbmt7NGPKsE7zLJWsde0CASoLHN5sUHjm7e8AdHo8ahCLAw8mQyOur6a13/senE+WEQQSQWiBvHFaRTWc2hnbizXnld3OqckNANQe5cv3m0d3Tl2rXLz350C3l/mL+/s3/rtdfD0f7jTz/2/Bc+t25o91d/efcrX7N7R3Y8CqEjQYmbaHgPgq4xLPDu7uz37+3//mx2R4jWpxub6+361LXjdjx27QidM852LEZi0JGIwAg7RJtWuoNgWlwPcS/rGIwQkRgdAACRgIDIBCggvffSjmzb2uoTnQ9LxiCSwbgczhgDGuYUAcRARGIYA6IxiD4mXKS8C6Q0q4pAiJaMs+wQnEGKe2SI5BhKPi+nWI/E6+KwBxHws9kwO7YhCGAKxxIBCxFQjKHFFfYSJAwkNAZzz/vzzz07vnVj/utfbQ+Xpp9P9mdj29qRCxiQEC0CggGAwKYZw/zg+PsvuNlhP17nT35keu5H5MY+DUuBoW2azX/z3/AyHHzj29SFsDman9vET/8IuZZC74ydLHr82Ecnn312+c573atvNbIMdnP69Efw3Jl+/8C4hoBmL73m379ugOyjV9affzZ4bkfu6Dd+Z/dnf2EyIE/Onf+LP7P5E1/oD4+abrEUL4R+NocQwt7+4XdfaOdHrt1qHn7UPHS5n3cIaUtq0Jh/mb/QVR6r1j5HCNNDWP6TNt0pzkci2lkB5QQqWI2EncIKyKwk8QXR4jTWkPyO+jsUfa5nQFJL6uClZB8gVXQ1kFs8jexhpNABaDQWq48lS0DrZ89vXrq8c3gUvDcIgRmQDYAbTW4dHI54/sTa1PeD57TqI2atxcZmjyhujaWmDyQTjxgEYGAUMMY4nC1m7736+u4HN8499OaZT37syY985MznP03j9vLm1L/2yltf/m3/9rsWiabjwXsDgogeAgZx1jDKzdniu/vHf3hw9Ebvj13jJuPx+lqzPrWj8Wg8bUZj0zSmaQQAWRyAdS4AM7MlHCM1SIawlwBCiBgEAYRSkr/UQ43xZA0WQHEUhuDFONe0mr2tu//FnfutMekgw7htT0SB6OUagACAaAg85B0u45JTRDTWxsQsIrSGGjEUvLNW+pB8yRSv1kSxCqOz2DBKTFAcFvNhNmt8ECRLQRADM1LKFE9xVkQD6OyYpb8zXbv4b/7V3dkB//rvX7k3N2LBhnY0IorZF6gntQCRCczj6XR4763Fm69ZOVw8cPni/+ZvX/jxL/a3d8AHImIy42ceP3rrjfDW21NCP1kf/Vt/e+Mv/XnmIJ6BwQDKuDFXruz9818OH9xlEDl3ZvSxZ4EoLBaj6Vo4PJq//JoNBy2MJ089ZT76WNOO8NWXbv79f9Dc214784C3xN/8zrV/+98z7Jt33oZmFOZH/vAoLPvF/s78xdc2ge2oaZ5+hhvX3bnrrPEwcBR9MlXIXwM9iheJckGarSpmvsQOIOMHVI5q/E8MBa1QPUQrBVTK5YIsOSih7kyBhliTUpQ+oKpeLD+qL1oVXvyldGtyQFAjE8nXUEHCaHVq0mvQEKZd56211rq23bpy5fjuvW77TmstCSNDH8IayNp4vDvv5Gh2cTwCAM9cg2HdYBEJqFlhysBA/S9AZADmAEDWGhHY39+fHRzsXnt//cknzvzEj2199CN3fud37/zil5tl1xgL1g5hMEBCxCKtgCPc8/2Le8ffODh+aenvIcloPBq1bn3iJhNqx81k6kZj2zTtqCXXBA7AYc3Sup0uxB8vl05k3TbOmJiuVkYQMaTsbTCAklZqJi+QY8o6Qx8CWGudNYZ0K+4UrTDWGmPREBoyhgDRmLQvDhg0woFjkqbmXMQdLGJipkFjG0QiMpbIGdMyt2DaxnRDQGFECHoGh+SNlzALQfK7WWLuGw5938+Ox94DGTZEzGAMaGALEcESElrXDAdH7wT//N/9X3fAhz/38w/ePtha31z0XgiIwKCQCAkikCAIYsxAbSaj/Zffols3Bwjmkx8bf/4LcOWKPXvOIRkyfhjMdDR/5326u4/eyyOXzv35Pzt58vEeoAFAAALoAfrQH730A97e8WDN4w+5Z570wwDBm9F4eOvq/K23CXw7PjP6kedHDz0I27dv/L//0fLr39+YTI/27hoI4d67y68uAcDYtenWmcAeD/b73f359ZvDK9cQzOz8+a3PfdYZaqbr1lkGMGQ4hG650G2elAFg7tKs+oVP6HyCwgFmvau0MgeKIE9aFB/AJqSpXqqBSyFdz4G6tDwRnrQ7eKmmekuV159mSCpyv0JvMoOQIjcp8pBzQAXjaUs13IFkHkGoAThrrDWNc92SxpubW48+eufooJ/PRs6FEFxgJ3xmZDfWxn6+PFwunbXOGJ9O602NQMWrWLmSnpAvAghCECEBIuTAnsUass4y88H+/vF3v3/33ffaMxt8dxuOlnbSDMx911lLI8SGoUFYAH9vNv+jw9lL8/ktxs5a27rRqHWTsRuNqB3ZdtSMxrZN+1AhGRGGoV9vmvOjcR88eY/Bt4YcQQgBrVE/LoYzMR5NFkA5XFmVioHZAw4s4qyxhgzaeIiJBjKJDKZsboKYugkAgEQxtwUJiIkIuKRpkdHsLWMaSwZJxBE5xAagRc3sjqNcE+TiiqocADBIBGICDH3fHR+HMABCCGSMiQYkwXnciRcNk+w8uPXU3/0P2q2zN/7v/8+LN3c217e64EUCCRIDCjgHiCAWwRkghCDkXGB//PJLuHcgNB4986w7d65fdHg8J8LA7AVgRN1rb+K9vVEz7g+We7/6m/eefC3Mj5F9GGDY3l37/Geml84N3/qe6WYIrfvoU/jIZb/sxCC2dvbOu/N332uhMQ8/vP7F59uGrv5/f/7ez//q2I3mZzfbL/1YM10PRwvbWji7Lrs78699g4HleL549+3Z9ff77p7HM7S+4fvj7RdeIe7JWRgCdAtYW4NLVzhu1ptNdJRQDbHpZVEHXrted6OodvVV/gzJVCubyNmaCAC2TBmm1Jd8BLskp6FEPRIYZFYQ1bjQXZ2DicNZIpoZJlaXflTuBmed5MxIUhyfEAKW+gMgGMJAZIicMT6yCWuttY21S7LrFx9YHDy88+ab2A1jJAtCAEvvRwSTyagDmC2W4wYNYlwKTQUIJe/qHKtKBSh03lezSQOmJWpBxBKaUROC9Nu7i3v3xq51YzfzgwFEkJaZQPrGXO2G7xwfvTxf3A6ysA6tGTnr4gTHaGTbsW3Hbjw2zrWjthm1RBaIIHQY/Ni4KdkJEozGy37ZGoxZAbFWDLqCT0qcJS6tyqezxY5nkF4EYw6FgZg6ETetMcagTpEmox2nWjBxy/QHIhqEEPcUXVl+GjmFEbBIFmBEhoL3Q4jngKgrGeVZcvgJdYaMBThu0ikCSGHw/WIefEBjmQMDGPXNdW0kCuBi2f/o//Jv00uvvvWf/cNz1+9tnr/keTABjXUIQICW0DoiYO4GY4kaMyx6t7HB+3v8xhttx7h+ZvzII3Y6hmUHzjFiGHoznfi9PX79FdcdNmfP0J0bs7/3n84tDswcwCPz7Mj9rX/LPvex8ctvWrc22Gb60adxa3O4d8tNp+yHo1detwfzsduix66MP/Pcwe9/becf/Px6Bzxux3/jrz387/wtD4gehdCtjba//tW73/1OayajYBe/+IuHN28atxYma3Lv6tX/03/YW9s4I2JpMbh+sfln/9yZv/vv9xLPnUVVWFVNhJQ7nPfiTCIAKh6nPlIUToGjijyKQMnRrKC9cm9XNJs12id5k5ycPYE5t0Kdz7K5m5SiEtZIPvhwtbYJ3wQYIa8k1TSyxDljd2C0Yj5lCemRV+lYQLdx5cpivji6ehV9PyLqAx8Jz5ZDC93YUC+yf7w4MxlNG8OBg3BMa4C6wclQp4ggaJA+RohC3BqNkeMefCLRIaRRYxg75sEHgbiZFTHgnUX/Rzfu/EEYliMHjQWEFsg1zjQtNa0xzrYj07S2bV3bunbkmtYaS0iMKCGI9xbFApLghXY8E3GBITBZEySrXAlxZ6vN6jUp84cQ9whOWdsQl4HlfTcM6eKPeEBI6vIoGJE8YvqfLiwzZFKKprFx83GLaBGswMQZ6WXZdWgs6jxVdkUpu67qd2qUDgSBCTiwXyxCYMMiJByCJFrBIixCQsi+H22s9be3X/97/9nw0uvoNu/t3ibuAARBDIgFMgCIBoTcxoXNS5fEOg4zO2pv//Kv3fujb47m9+xTz48ef5IQwxAQkBEG4XYyuvXVr7/1e1/dnN8b5scCSwHpAHolQxbA9XD01gfHN95yEOiBj4+e/wSIcGC3tXl09da1r/4hdtcdNJufeGaYH7/2H/8n/Xsvelib/NhPXPxb/yP/4IPDfNE4x77n8aj3sLt9OA1zs7d//Eu/frS/PwdeHtxyB0O48S5CcYenAGd+6mfsdH25fw8bV9tQBYuc3J2FOU9C1DOjkkOhWD1c/JASIohIkV9R/UfBCetfUOuRcQqz8lcOZ2Y8KbqZ0kure5TnY7IzqEEQjkJOaRs1SQ4IS97gLy0iQiTCQIgm2jUyyiucc5acGY3XH3qo77rDG9eh6zcBhghwYXBBkGVgfzSbXeDRZuMQkZmRAyGCLrWKSJkgT8mRAFA8hiwtMAvx2EFUE4fsCQhFKO3TASjSDWLWpp959ILf2/3DD+7s9ry1uTYylpwT25Bztmld05qmacdt2zbtaOSci2cXAiAz8OCjhbeIY+tGoWl8h4AkaZMsydlvKSE69ZUGx8GkVcjIMfU0ro/PSGFQz0kkBDJoNCcsQXOKTsfMyBhKNEg+LhxJB47FbTidtZalARg5s2YQZjzv+tHImCokFIsI6q/GQHU11atCIhy6TlKiHTKXnfRE4v4ShIQG4aibTX/qx9uf+hkhoGEZfZ14HDMag5awddK004efaL/wudAFMi50Szoz3fqbf80sl5NnPj75+DM8BEn5IoLGDN1S1idn/8Zf3ZzPRs0aAKFtRhI4eAQk4wSs+ZmfbAPbf+9/Z/oD+7HPNB//KC8Wtp2wAE6bS//Dv2S++InWTCZf+teO795snnp8/cr/mM5fvvClP9M8cmW5t48heIAgQUI3vnTx0f/F3zIHh5NmCqFrhtADc5zNjYt2Ucg433fN5sbaX/lL7HuMW5IlA6aThFVcrcQDlCNk+Uj6qX+pwiLE3JmThpzwROZVph6q7oU1QNJntfJK0QskVDGI9BOUvSdygKVESAAyhCiZ0KIRQc+cqlIzIEfvCOMBC0CggTUiipviGoo5ymbUTh+8PPiwe+t21y1HgBgRpw8Y2BIeDeGoO7o4aR6Yjts4HaoHSRT8A86Z8bEGLAqiLOm8mnhP9vpI4vkWKIwSD6mB1g/Pjsd/6qOfff0Ts998852v3do5JFqbTA05Y9FaZ5xrR6O2bZq2jf+h6NwBsg/sg6Q95MkATG3jjA/M1hpMt+XhAtCpdd1sGAAgBLEGYyJ8EEn7UcQV3qR2Rv2WxO6z8CmXBEZJcx0kmZhQ3OPCGnbWOWeMk9AStkSttQKwDOxEDBEz5wBXyOKp7jFg3sEHCIBAUELo+7Szr2djhX0IRBgIgAmRUciYbtmd+cznzn/2i0IGQeI8LQIQIZKBuEuwNWCIXCM+wDBYY2Tg81/4sYuf/YIAoHWMJiw6QAkssduXs+XGR5869+//ByTIQILI8WzU6PyQFUcd+5ah/fynUYSN8SIS2DQNBxmfP//Ev/E3DJIg+dC5xfyZ/8P/kayFdkJN0y97iwacYRaDTgaefOSpp/7dv8M+5FWymmakSoeCSARC1opr+25O1lIen2yjBdIeeFkgK3cjBy245vgAmdBrWLAE51Ip1Y67WCtEAQ6lLYLp5FjQ8cUy24GFycRJC8UwBYUcPZG6dlz+EK1szLsExLTJSVr/GP8j6Ytk2cX6k51uSpvGtu3o4gM98O7tuzRbOPZGAjMAByvgAB0yL5fC4cKoWW+bxhpC7INXUhVVhiFlzgJiXJ8OhCD5h9g0js1MSyMIJCZrIQISdt3w8psf7N49+Mhjl//Opz/1pWX/m2+///X9uV9z01GDSE3bNG3bjsaT6bRtW9s4AMSQjj3l4ANISPgjk8ZNQtPP5y24jP4prx5XNkDW8FUkbEAgASCA5G0m0jhXiBDXiiTEjPwNUsCK0zUkIk4hZYybbhprXLDOWWOoYbaEjowj8gIDsAdoMIlNJQGxoqB0VZUDEGJ+mvAwdIGDhZiBp9uysyCyZwIEgyAebDMWcmgQkSROxCQ3VYkwAjCERfRK4g6ZCNQGQ4QQD1tNshq3CRVkYETbNyOOVxEAgMGCbp5AIoIUjCzRICLEXYjSjsyAjEIUYrPIurUtMhYAhcPQd6D8Lukno0eiUSsxfpNGT1PnBCDuEoJICEbAD71AXLlcZRYppOe5hWhZU8yCdBu61OORJ694LqAUIE4wYMUGED9kJxtRmEnxCExMAqvTBCQuyswxi1KJCm6yx6zUIl1cma2NlebUXpGYXoL5xjh6AJg2bkqRdKj24MKYfEXGUIzk28Y2vW3taGjPne05zO5tD4dHNgSIxpbZCowQehEzwMS6sQnzfoaAG+NpyBIbO0E5PCiflwQbotQPFE1SaDbvBhYXsJOlZeDdW9vX9vYffeD8M089/vEfff7z29tffv/21UCTjWk7apu2nUwm4/G4aRqkdJIzSlKQANCFMDZGQKZNM2YeDg5lnEMSKaCCjHGHqASouYsx7slBLDHNJJkWANDDHLPuAhlSoEcA0MogEFFgyYEiYkIiQ3Erb+eMtY6IXEzHQCEEQRk4+g1p4kJWxEMlUnKkM17HuNQ9+AEiESLhIGLiJmeMGA9KidhFvvcIg2agI5PEE8coQ11CvnxBWIR9SDvAY9ywJwFXTkkIIXA/1FZZtQaiP5zOXgdGASKkyGcESQBAOAxpk0xCZhzCMjYMibItzU0H5mG5TNpQ4oioipbeHQA8YpxtUkNd0AKLxhXBiOMqeU8+Vec84Ppo8f3qi0m2c5yiHr7V2wVSPFJ3Djwxp6oOgvp4mB0S5mT7MaFU2bGrTikEDYUCFMDjdNp1CXMSSsiOQEYIrUpytomMMa6xrnOucW3T+sEPTTfZ2mSCgXC2v8+DjwzAIPbGRPO/v78/Bf7IxQcun9no9w8MWolnY+gkVNzajYXjBq/MGmLCuGoLlaUlbIvh3ESvAJkZDbWb09kQfvDB7ffv7j77yJUff/rRpz793Fdu3vvBvPPj8WgynUwmbTNqGicCAQIDou7R4QU675eAU4OjxmHvl54FkCEe8qyDgQmboNgX0QMGAUACCIuQehpqWdL98VraEg9TGhcqtyQBISIQJiERJkKDyJhmUNilCdO4pY9wkDAwe5E4q6G2IO1sqJZAilgjkEqnoq96v6xwrXZYJ9ViiMMg2biWDQCJYvwFclBW35seTCYTEdBkORL9IWsIIlpnQCe81FcqTCueyUKGKpnGvBk6IoKBVF9CRKdnSELycCqnHREtGbWyml1Que55jJTMS9o6QSS9WFLIJ7U3hQbUuYv/6JZyWuQKqYiWgTT9P9cilledDFT5Mwk2k1eZ7aMoE9XghQ6klgwAnE8zg8IzILKBgmeJfCQrHLu1hjkkkhBiiUQkwpxfotAfERkBEgtGYwxZaxrrfOO8bwbn28Z7P+EhyBoSNjNjj3Z3/NC7pkGQ3W74wPvLAJ9/8OJPPP/xz3z6+d23333pt37ftk0mMsma5r7Twc0bQGpspXQ5Z56lICkCcbEKIbXr48Ol/8Yb71zd3nn+48/+9ccf/uh8+b3j2eGosRsbhGSNYY7LtIPnACAxqhcIumHomIJINwy9gI9h1hRoSHuXQs1BM2wLo6EoKqw+UfRJIc/Kl8lpICJAIBVLonhcCggQixgSEYkTH6tb4EBaTkYYmHtGD+AZUIBSrm06Hw00uTvGgbBaUpT7UZLYpDqhqgFi6WtJ0TpJ+7SjxB0EisKsOLggaTQAc2ytCpWkndIhokAuBzSQn3oj1VlTRbLOpJs1iJbyEZK3Iik9VblTjOJKPBRXRCSdaVjVN0aL8rxhQqsUxUzL9tJRAQISt4hIBiypSd5VuAQIYmeh4l7JnFRhrvusFnFb/4I1wtRcBk6gT7klW9yVUhRGMyNQmgRlrlGFooa4EumIzAIgSUKBQNA/o/1DhDjPh4aMM9ZbG6xr2yYE9kM6E12CIBhC0xJN2tHezvbe3q5nuTyZ/PlPPfevfeSJp9fX14zsvfvunTffGZsGJW7sDIhoDAWWdEweIuhWn2npdNqbE/P5EdE2RQqFkFZqJf9KQDAYD01joTW3jo53vvm9j+3tPf/Rpx49f/47S389CKxPhUPgYMQwI/mAiHERTBAZROY+7B3PTdcHBK+4jFD2qMRVLQKVH1BjrTaMRA9+1xFSA4ExHqirLZRXxOcIUXSnPDFkAumKUoryyQABoA+8NDTEPWyVJnDuHk5iIgq1mOa8JK5VYYR4yqza1MKLogBENz3ORyFiStAos7iJX2QGWjvOAMASGS8AJ0MrMYgSt/eGCowAAIWQskcahxkBMK7Y5YQgpZezDdTaJ69GI2+cfkOI6HRKrTJvz363khnI/YDVYMeRi6CWYz1ZTxJvi/ei5HnRlUBB2i4ESqWx8mFKRDOT58xSEOAELhelRebCdgERJHWM6PYIlIUuo76yzJqCnMCfFHhF5FB1oET6oj0fp+KJAkDcP5rIGgrGButcE0IILMwchL1uo8cBQBpnQ9P4ZTdC+sxjj33xuWc+8+Dli5a6g4Pbr7318vUb+9v7xpjxZBS3vTDGdiKdDxNjncEQQuKMEeeKACeJRy7EQnsyHUSbcSaR5uCJcDRuex9eeP2tvTs7P/Lcs1+8cOGl2fG7poHN9WHoPYNlsNaQhr5C4AFkAXLveH6GBUCYwRiSdNC2SFp5lWibVg3VAwKiNLiYZo4kbTdFAABxL01Mm1KALnKPBAUlnrYW97KKO/EIx7mTdHK5Nk+EhsAAsAgcBAYRFswEFCD5RyUPRAUyiKSzEQAEIJ63xIDAEHfhrNZaJxUiFVzU887ionzSNSsriYRKIXKwKaE+6tEgqLIft0dU4krKK6K0I4IIUZ6HpKKwEbWx0h1JBzQBJxyOyUJRQRixBMbjjEH2GTWoXvAiilvcCYmk6HOlwZngJzYev7BqG2aRTS86af01PJBVNhYNePq0wfy5D4E4OTuCOma1yuRaR4hGLJOhkFtX6ptcNkiX87mIkRoxYDxdqqoDIAEKocQkIWOMWJEQ2LJwAG6BhVhQIGZRigQD3Dg7OzgMi/lnLl/87Bc/8/SZzeb4eP/96z94593rt+4MXRg3zXhtg1C64A2iMfZA5K3j2W7fPTBqHx5P141BER9OhDGjsUvAmY47iWeA5qEsgR1RLIwTSTyyJtj2g53t2be//dxHnnzusScN7F31vWxusRUOkpx+YWIhZAAZBGYSNoyJg2oQWMAotuck9Ni90UOilDaGQQqrRhU2ACB1sSHyCMxuR9rFPOocIyFELiFAZJjirDKlHfgAOOVZDgKCMA8sAoMAYwlTxLFFQM77sKsUxT8TjAgMLGSsAAgLmCLWhfILIylAIMaIgQKdhJAUzxijQpiOdF612EmLAksIjADGGASIqwcRdK2dpNhyLFCjpQLK/xFQ8vEQEek4iM5gR46KuioXQDhG/aggQp4XQhBgGUKIr8vsO24PgHFqJlYx61GUsyxoqWqntLjMLmm/F1J/vwcUfqCcIVYdLaJv1jmT8nBM2Y5kIVtMgNXdzbB6WC0blIrXaAG6wUmOCKg3d586KzdWBgZEZI2J23uIsyhM3JAgiVhmC4DAJNIYWGDg46OnpqPnPvnFj22uw917b7/0ymsvv7p7d9daO52M1kZORJg9gFhAQ3R3GF6cza52y4Bwbx52en+laS+M2pFBFAgpKROTOyI5WgMIwnEKVUdDc5dT7AkT0QASkuAdYrPWHC27F15+5enZ/Jmnnhr3ixfnM7l8yTgLfW+IUBiADcapQxaEICG+MuIWq7mOoEWAoqc0QTqlKh3agcgcGTdBTFyIZwhSRIi0ERcAEaRNcnNcIHrX0doQS4g4bX3wMacFQVgY2GNMeBEDwsIegIGDxLypJEE6RY6FKSMCILPEJjCzF2gbKwRJtwkAIQIDpcncpMqGgAhIU0sJgawZN611LoTQdV3gTHkki1mm6LEebWMb2/jAXd+FmNefzZswszhnm2aMACHEZQDRwalCphBDjBDYI9LadOqcE4E48xOCny8Wy+UyBnaivMRJdwFIB7qDCEgIIiKjUTtu2hhHRkTvfdd33TBYYw1RCsSkZ6Ivl2qhMRrBGBOK80iSNTtN5hWKV5RMPR2pYSLa5hLRBN0Io7qwqqtZFVTlZfUlsnornriukePkSGWaobGJzA9zneMjhPH0vcQmgFIfkEVhEjEGRFA4iKUY4GR2KMagQZiS9TvzDT888syTTz/60ORg/7VvfPN73/r+3b3D0Wh04dx5BBH2IMFE84iIQO933Xdns/fDIM40CD3LrWE4HvzO0J9r23ONG5MRLnO38UNV8gJgCmzWNxQIjh3NAoQMgkGa1vXd8Nrbb3XzxVOfeI59/633O/PQQ5hZNTMJE0haQh1iuDF2KYnuaJXerGQHQcq4i+72BZDnoVF35EXEqG3xD108nkSMEGIYQWJsF5mAGIXi7hRFBpgFAkBsnEcYggQRkeR/VWYTAVIifKp1qrf6sgIeQFxbCeCKPGr1AOJasXRWU5q24SCHR0feD8417WiMJMwCSWnTMDDoXg8AAHh8PF8ud0btaLq2Nvjw/6frv4MtS4/7QDAzP3POdc/UK19d3dXd1dUOQBt0AyC8IQgShCNAUhRJjTTiaFysIjS7oQjFaLXa4XBlVivtzkzEaEKU6EUORRIkAYIACAIgbAPtqm217zJd/lU9f+895vsy94/PnPOqqRvVXbfeu/eY73yZ+ctfOmYmwtTID4iorpudnR1EGg4G1hiRUDOUIAoBAoWY3Xg4QkXXrq2trq5ub0+dd9aYpaWl/fv2Li0tbm9PW8dGqzijOxN2GHwu0UoPBoOtrc2zZ87OqzkzG22WlpYPHTo4GAx3pjuOvSYVGMrQMLEvplEA0z/e5Bzsil721zMRSn/9S8cD7trSuz2M1G8mBMOBBTF7MwE4xV77yemI6iC6kHkr9O8hQZAwHYowNeaG7iv5GggI0IdLIABGoJAlKAIioQcpghAKISOwUYWrgQRK5mJzbf9A3fKWt+8dDdYfO/n9L3/99BsXoBweWdkjntk5Fq8QNClk1lox4Kuz2SM722+IiDGhLbQIgKIZw4XGrTm+3rZ7jVkpbIkqVIghSpylyxwEJ0z9TqvJyXZGVU5RkzBGDxVYPBlyYF5642Lr5a7776mq6eNnHB08AqhCz50k9QLMGhSxaKIALbCD/5BRcRdQCE+4s6OIDAQkFDtLUKoZDTVxmNREkLp4a8n6R6eEiH1yaSHYtZDrwCwYUgudgBNmCAgljkcNulJSxlpKEE0XH4QTEAAcEtqCJXhqKnZe6QB2jPQQkcR9AoDQunZxsvTss89+6c+/snrt2v79+/7G3/jZY7fcMpvP056KUwg5eb0MPBqU3/3eI1/96l+MhsPPffYz977lLVVdc5JhZh6PRyeffOaPv/AlbdTPfu6zb33LPdV8BlHbUgxQMiPAaDxaX9/44aOPPXny6dOvn76+tsauLYti/4GDd9xx/J3vesddd92NzretUym8CqkenFmMNsbqJ5588utf//rZc+c2Njd960bD0cGDB+6++673vefdt91+23Q288ykqCvvjFcalbDk+DzGG8YwxQKiJsae5e5gPmQ3Mj7TDHiCpvjPqxHYdRToiW8ANZL1cz50eorBneiptHTtoRdKz8BK5w3GFyUHGzH4ftHZCdFxoLDniSRoLyEQJeRBabBGmXZeaV8PWzfaXNu/NLjpbQ+ozY3zn//Cy999ctP5A3v3Oudb37oQikSlAEmC1NDp+fyH29tnRbzVCLntVcqYJpyiVG275tw+7/YZu6SNJRTPEkYGJocxqoYsq8wSK1PjUgReiiMZHrUMKsRh8cqlS475znuPb+5ceQXEAjCgB+BoED0JDCiqBExqnqFT0dA94ZDqFDQ8iHC4BpUXOFOYSIShDXBSGwCQ2Lr+o/EA2XpjCNYlFBtjGclOc8gcB4K/ZpOF5QkR1VCUjETRkwp7syXEQREymyBIdAqKhUWUqHqSAgUUFmDQRI898fhffO1rIApJ7r7rzptvPoqIzvloYTpLLoF/MFpfuXzp5JNPzau5NfrwkcPLe1Zms6lWBhBYxGqzubHxve/9YDgofvJjP2a0mouotCgUHqXAaDw6ffrsH/3hHz/66GOrq6vamv379xVmsra2/tTJp557/vknn3zyk5/4yQ99+COilXdeKZVzJ5hFkTJGP/KDH/77X/21CxfPE9FkvGCNXb12/fz5C88+9+wzTz/18z//N9/+4IPb03kfucNuCY+QH7JPHHRzErg+CJFOOjP8l94hswh3taRJw77poQrnYGg6S7ZbPXaoe2YY2HgWIUhRvPShLpExMTBR46Q8tHCNiBiQImHc7oSYsqNFFIX8+0AKKADWTIioVDOb46weVrPB9rWVI/tWHnyrf+nFK//hd669csZOJvuQ61nVChtSjJRgI6NHo/FSXf9we/O0F1daCNWPgpV48QIAGkGQvQATOYR53Ww0br+1e41Z1KQBYh539OuDuohN70P5LANGeid4/IggCXAgR81CnobFa1cuM7u33HHMX35jg8gDtCCOWTMrBSRSAqBWwkxKeQSOUVzAoGUxJcEnSIFpxzBwqDyjyBfH1Ik4AajPi4v0ypnzoSF45z5ij+AeQdAykDQjhGgCADOHSQKRT8lqI9IokJxhzER98OA9syOlyhHmSFPQhn2RSHAmDDMGEM88KAeXrl5++ZVXlhYX9+7bf+nypWefe/7d73nv4tJS07bhKSTgm102YebxZLRv/z7n3NPPPvvd7z3yU5/+VGGtd6yVEkRmKIaD/Qf3jQfDwWAQOSfqRIeZJ+PRuXNv/Npv/NZjP3y8sPbtDz30nve867bbb9NGr1/fePLk0z/84Q/OnXvjd3/39xDpRz/2YzOeQ6rjF2YQGQwGp8+e/T9//w/Pnz9/z933PPzOh+6684RSamNj8/nnTj39zNPPvXDqP/zar+/fd+Cmm2/ank6NVmG1EaKkpcYqKUi0S1wj3AgX3VWBSQpTR6YjqQfMPhFCv0KsbzpudHyyjsIs3gkkYM4s6acKAkhq7pCxRBp4F/ZKgnYhBJfUWNgQfV2FiEKIDGEqNAkBgQiSZyAQIUGGlkgr5HpzU61v7annk2p7cuvNw4fu9ycf3fnV36guXR8eOEBtM5vNSGuD5Dh17BUBAIW46drHdrZPeXGDAq0OyVwA4l1bNa2wL5itYGgMHWR6E2BW1+tte7A0e7VZUEpJ5O4hzEJPyC0ra04IOj0dAQHO3QYjivEwKF5bvWqNettNhy9uXPdVI4TOcwtiAaHlQpPSitmjNpyiCgyAnFpUdoxqvE9CDOYZYzoTRP9otyPb82ExGaC4iaTzQKIrIx1jHu1E9FcyGhYOEJuT1uo7n3n0AMW06LC3SRHOfcO2sMNRtol5EZklVJL392uwM95LURTPP/7S2XPnh8Phgf17N7c2Tp164fTpMw88cD8gcvSTd+32oChZ0LvWKMUsX//6N++++8R9b33L5uYOEYaGgaiIgJi9oASXOC+Tc74si2k1/+M/+bPHH318Mhk/+PYHf+ZnPnPHHce9F89eK/3AA/cfOXLoi3/25fNnz37pz79807Fj995z9/bOVKtosZQhQHnhxRfPnT176PDhd7zrHb/wt37OKO2dL619x0MP/tHnx1/40y/M5vPt2bYxGrsIcPQvouAJhISuFCjoBLaL3N74itqTdz2ebhvAm6cNvulzSXyh7yXGuZ6JgO0ARl75LlAhnSd6g7cSPaUemgk6B/tQJXBoGHJfQhouMnryhOBRkRdG0Oi52b6urq8vt81CvTO47Vj50AP8w+/Xv/qbsr49WNkLdS0CqIwT5wRagjChg8UDqBrl2e3pk3VTl6UuLWotoe8TALGFwrumkbph7wyIBkRAJ+xQPJFDmdbNhvNHi2Kv1gMdaK3Oh8cUoYg6PiYQJNnoAGB6E5yW4fD05etLxfAdo+Hj4q82fqC0F3ZehFmJlFrNmRFy3V5Qe8QAGIkR6IsDs4S1JQCVEEjMsAifzKYFJKYwMITjpZyKxEAGaeNQoZPODwihIiOBEwQhAY05etLtMoTsOXSv8C0voIh87dRoZEej6N6k9FNmCS3y8l4NW41BkEEbVc3rZ55+7vq16yfuuP1dP/Ij03n17DPPPPvcs3fceYextqnqBI97j0cAkQIfiaQmk8nly5e+/OWvHj18aM/Kymw6JUJCUTHBK4Wuc0mCgACUhX3siZOPPfo4e7nr7rt/8Rd+/tZbDl++thaKy7znycLkU5/6RFXXf/AHf3Tx0pVHvvf9u07caa2J1CmANaZ1bnNjEwQXFxbuvfeuyaB85bWzZWmNNnuWl3/ixz+KIkePHb399tuns5nRuutakTy+JFMA0OPXIQZZIPqnfVoAOgOfFE0vvX6X45l3Ctz4XnrbLdIk3d5OYi/C3MXK04cBIO6rALGZOes26MOTcF1p90D+CKSc4+T6xO41gd6LxeYigISGyG9uyKVL++azPfV0cGB/8dDb/VOP1//+N2Gr0QvL5BojYgELhUahJrJEikgjKkBCPFtVj85m60bbQWGMNcYWhdXakNLaWjUY0GgsCwvtcDRXukJwIIzAAq1wJbwNcpn9S3X1al2vCwNhoVALqz6AF4mEB0duUgRYglCThAbbDMChRRAjoBh9+tKlRe9+7OABmE6d9967xnnHfuZaReSZfSyq4OiApBNIQi6SAUxSBRjCrpICpRIJ0+yXJrXPkH3CkA4RnngaKJ03h3SZM0wIoceeIrAoJeIgFIwl4BHELGVBhHhnTO4MOVwKQRE43+rFRTMcAqS4TLKIyS7G++OQ6i/SOjcaDM+8ce6ll152zh2//fb3v+89dxy/jYiee/75q6tXFVFK0ecbtrsAKq2qpl1YXj5+4vjK3pUnHn/yG3/1bREuCsveJRH0YWpS78vAzGVR7MzqZ5559sqVSwvLSx/4wAeO3XL4wpVrKGStVcbYotjc2haWj3z4A/e+5Z7ZbHbmzLkLF85PRkMU0Yq0UoqUNdpoZYz23p9/4zw7f9stN+3bszwalDvTnb179/6Xf/dvffQjHyFE8ZwIJQAIufld7CIAfd5lvvOicdyNAJ26TBhwtz7v/91XSumd7P70LpCGgNh1srzRSUkUHnT5VLvPdgNowbgPMaXAxR/kHioYI+f9tiqUu7cBAYJGbDc3qovnFmbTyXxTl8o+eL+cer79338Vrm9SWUozV461ZyOsRbSARiAABYgiBnGnaZ/a3j7tWBWFspasJWMoDM8zVpugL0o1GMjCgiwsNcPRXKsKxYWkY+FW/Ax4Dficb1+pqgtNU4EYrVTy0RDTXQJgskI3qONutRgRQIFXSubs37h8+W1Ly/eOR9uzqQdp2M08b3rnABjRh9lenCy97F7n4OFgetQIEmRVGIWzrIZnm65Odj32zl6F3CWOtadpYGycLC2Ruw8CrRRpQoMwJpyELhpRKUS3OaVcU96ggelQCArBEDbe66UlVQ5Ctn7ymrvge8qE4jhz0rPzXmtz6oVT5984v2fPnrc/9PChA3tPnDi+Z2XP66+dfv210947ouyAZH8XEVEhhmzYYqA/+cmPP3j/fXVVf+Mb3zz55MnhcEAKY3NjYERURN3CgHjvrbVXr109c+bsdGd2881Hjx+/bWdaMwsqco69Zwaw1syq+dKelfvvv68cDK5dv3bp0gVrlNakCEP/5EFRHr/91qXF8fra9W9/+7t/9MdfPH/ujWpeDQaDvSvLk9GQmefzmYTWJOlJB6QDu9RXJ70RjiWhi5skqO7sLkT5i5tUdtUhR0JKpzbUN+5XyEeOhgR6nmqnrAQglk9FIkNSQkHuTdltWn7TOcLRcmP3rn0+pIsWwND2QWKQMafNtey1wnZze/ONc+Od6QI3qp3Zex/E1cvNr/46nruKixM3m4JnYlGOtThhL6GfTTgromN5dT57el41xo6LkrRBo5UyEsOEKAA65JILsYhoI7aUtnL13FW1Ya8BUMB775lR6VWAVqQSOKj0slHauZZZMA4k6j/BSL9jIqgRUq4fYEwBRiG9OW0WNzY+cOTIc889v6WVFnYMl5p6ySgkFW5DxUi27I5M57PlTP8YikAXw5fpSUVHVYRRqG9r8m6Jh40AlUVC4mGIjYbp88xti4HpQwAgLTwgGikFIp5Rx/77MfYW5ynHiEzSTsliNJ6LpWVlNEAq7MC87yTqCUGJOVXKsTNWr29uPvPs85vrm+//4HtvvfVY27pjx44dPnz4iSdOPvP0sw/c/7bReFJXVQisdsZOQsIWFMY08/qmw4c+/YmPv/bKq6fPnPnKV7967NgtK8t72Pk0WjWU4ce7BwD2AgDXVq+trl4XwD17lkfjSVW3CMr7bnIFArJno/Whw0cWlxZn8/n29g4AKKVCrJo9s/f33/e2j33so1/8wp+fPX3ud87/x+98+zt3nLj9lmPHbj569NjNN00WFlG1TV0HSE4Aqa1yMEe5a2qWRcn0RFdSkCwKds9YEgnek3tMSFQEYuwjbeBd3kvczrthWs9xkW6HR8XWkSfQ0dpJ6vFGXgIAcu+ShIzzdzB/NrgmkkiypHpEmAi4aTbeeAOuXxsL0M51e88JpdX8139bnjlF4wU/n4eyDxAB8eS9Ym+CDUTwAErR9bZ5ejq9DFQOh7rQYIxSmrSimBSciybCyF7vWVgrKLSUJZdVO5u5ulLCGoABp86J1rYw1wAr5+fAe5VSLG0ehhP1QorcJLWbigyifQ9R27C2rPTq+tbB/XvuHI0fqWZDrSqR0sHKvN47HiILEHCiJyVu/B5HGh9kz0AAQtsC+xtibDewBunZhSvqclwwrmea7ybMzBAazTQtpeevFWrGCWGhQqlC8GEQMSS7B4OWtZV0UAZBEGaIy3uXUSEJh3k+fRQryTJBqCFl3zq3uLT07KnnXnrlVVvYB+6/fzQar61tHTpw8LZbb3v6meeeP/XChQuX7r57MVLwOWwTsrBD72CtB4Nya3Pjvre+5YMffO/6n66fPPn017/+jc999rOFNZ5jel6wi9nrYRHPsr0zm88rRNTWolKt9wwSh7FStNbATAhlWdiy3Nneds6JgCKEMItEU+ua4Wj40z/90+PJwve/98Pr16+9+trrL7z44mBQ7N+3/7bjtz380MPvfOfD2hjXOK0ouxAQGj+FaFrKgs3R6zc9TehvjvQA3vzwe0EKAA032p/4TrKCBxQQiuY9HiEx+FFzxQ2IMfUnQ+uEgjPp3eEFCeVADICxnCwRGSjJd4laAjD5zFEVMXvnvCbYuHxlev6Nvd7h5qZaHpuFSfX7v+++8V0yw6apmDlEIIQZgRGYQIhFESgATcqDnK3mL1UNDYZFWaLSWhvSmtKw7xgokLgjI9AVdt6L1mwtm4LnM1dNuam1gEHyiHPvC6ud1RebdsbukDEGuA0VWkFqb3wsCAF/xfacgkAUF9ELUMUy29y5f2XvD8+d2UGsBEp2a0wLIJpZKcM5US8VvMdapcwxZ74UGAnROfEtIuZmSpJSbgO/122t7u9gACQmgOZDCzB4EWbnfVsn/1MISLEMiRTRnCXMAcjKLJuqbEAERBGKAAG61s+1Pri8nGJ0MeMkIaa4h+J+F/DsFaEwnzz5zJWLV9761nvf8Y6H9ywvbW3t7Nuz/O53/8gPHn3i3BsXXnr55TvuuF1r7ZxXqUQEEYTjhBMAVEqzF+f8Rz7y4dNnzn7rr77zl1/7+u233fbe9/xIt/MDoZS3BAt7ES8YtKZz7F3wzmIk2CPE5jXCLN63rWuBIU45SuYCBRBpPpuXRfEzn/uphx584LlTL5w5febixYtXrlxZXb12/vwbJ5948vKlC5/97GcVEbPHTFUkqxokpwuVQgpTRgwFuQlHdBcypA1oL7BpnZOR1QDovkiHX1PWU8nNScAhRkMxpERgohXyN6PB6DVoiwfJIZzuArLbGd2WfBHZ/mXaLPzaB65dhH3rHCBNN9evnX5Nb22Bqyy78Z5D8y9+cfaVb+ty4sWx94iKPUOQuUTsE0homV0grrX+pdl0FXE8GhWFRW2U0UpprXXXcSGVG3PwNwWYxajQss6zUlwUvip4Z5urWiDWazrxjaiiKNbbpmmaw0YPlGqZQ6OGGxY80YmYnbn8W4+RZ9ium4Oj4TFrn3bNAGkbYItl2rrFskjcXkQl0lns7iWhM2UyJtg6br2OrAHs3gPYNx5/zat7tgAh3sIgIOxbbhpACJ68AiCWkSKv9bxxAcwm1ibtxP5FprwJpWhWN00xMMt7BPJ0qN7n8pcwcjDeucXFpXPnzz/zzDPeu8OHDm1vbb1e1dNZtbZ2zRh96OD+c+fOPfXss+9977v37zvAPI0ZZ7E1JapEgYGwtbpq2r0r+378Yx+7cPHii6de+NKXvnz/fW8bj0bOuWA+oteUwYVwURhjNXs/n0/rprZFEdJwkm0F8gAAzH5rY2u6Mx2W5XA4IALvWSkFsZmEENK8mjcN3nbrseO3H9uZVVcuXzl37tzjT5587rnnV69c/tM//cLBQ4c/+pEPr29sZMYkRixiPXc4b4cYu1kcnaWO4pz+3/2d9oTsApxh2uBfuxkiiMHo5+QqqLTPBVN8qTuXRBUQJnimHdVFa7LVwqyMBDCOYo1ESk6eQwxdBAQlxjMD9veenfNEfvXcuemlyyuukZ2t0eEDzclnLn3hm1aZQqOvayJFFI/YWzIkBQqABRTh9aZ+va5xMBiPBmiMspa0Dr2mFREplesUA3QWFu99MCWevfLes3PKo9Zgrezs8GzG7EGLF6jaFguwhdmu6XTTHrVmkCaM5AdDu5ZcogeXHDmM5eoigDP2Y+duH02eXr9eE2yLbDPPGp6UoWwLU9ZhRLySn2JA+0nvckg9b1txDkPuWdb+QWeHokcQEaHURyY/Xc6LKSmYHUh2AXatb1sCxKCpgBRIQVhBzJhLKj/coXTbJrFpEjcM7TQV7z9AkwVm9qEC1guYGCzrPBEUomgArSmePHnywvkLk4Xxc88//8orrwDEy3Bc72xPFxfGr77y8quvvnb44CGtNQGGMoBUNovpjgAEFNHm1tZDD9537tyHr1y58oPHH/36N765Z89erUmgd+Wx6SZ77ycLk9FoLMBXV6+tr6/ffPPN1WxulEo+JjjvrbV1U50+fXZjfevAiQMre/aAgBevUEUeUBiQxsNB3bTr65tIYK2+5eYjx2+75eGHH/qjz//JH/7h53dm9aOPPfaB979Xa+18qOxNdfxxOTNHER9VTmhInkrKoUwGu7fp3uScJKX+n606j/uMAXLLgEyDxAOlKwveUQrSBH6s5xJFHyLnV3W+ZupXBrG6LaAPSHPM48cinyjMzJ59XbcIsH39+vXXXzdbm+IaazVvbL32ncen03rlwKiZz7VSFMrHegpVIvxSKKAJW8QL8/k1LwvL4+Gg9NpoY5U2SpvQyUkplcqfctsqiL1xPHvvFXvvtfLe+dYpEmVQm3a+7bw4FiKce9+KGKunKGeb5qjWA0S3q09KfnX14pJKJDxHqxnWe960B4tyAWFVBAA2hSvgxrUDYyQkZkqsi4kaHgJxGCgRiI2YUAABm4brCjqd1bMzccvmyrGsxjrTnmhTyUAREX3Tcl2rfEwEEnDOseN+ERmmLgTZiQ4lmByKegQFYL2am5V9aAfsPCjIHUdC+k/Gh2FjMfNwOLp2/frJk081dV0MimvXrnnXshcBH6pFjFblaDzdmZ48efLB++8bj8d1VSWNE2E5xoY06AWMsW5np6rbD3/wA6++fvoLX/zSl7/ytePHb7fWBH+WBTiYIRZArKp6374Dhw8fskV5/vylF59/4c7jt8801W0Tat5ZBMUvTcbPv/TSD584yQwHD+4/evPRumqi3y0gEMOlbeuMUlDatmmauplNq7puDh7c//Ef/9HvP/LIM88879t2Z3tWDKxvHfaas3daIK5q9B5CP8TI+3WPIr1PVXDJL8zaoocAUP5zmkKylGLaI7sUT+IQuuYTwQwlJdIhjgCOEsYN254jYoo3JdlAQQK0AiktIBb0eBbvvXOuaRoiWD3/xvaF83vqWds0tLh44exrr1+4MFJKt60BNOANATEoIiV5MwALiQJg0aRm3l2o5o02k/HY2MLoQhlDWuvCxPA2UvIEKEYEmcP/vffes2fnnFfeK6/QO4dKAB3KbLoDnp2AAiDGQnllqGaStj1mCwPCwohprm4koYIdSCIgsTqGUi82B4ieS8RlrS60HgE3mGfiq9YVxgatELRDIExDbjWIeOixS/ExAXrnZ7NkTgQgpgnm4FlYseQWJuyK2NmljBkleD7o6gZaTyAq3AAwiXeNa70QUpit3Ol+iLntSTFJKNQXgNb7NQ/lgQNCyjmnCaOiCAltIip8XlhIi4jzfjAYPPbEybNnzgrCww8/dPTIUe+99x4ACHEwGFhjv/vd77348gunnn3u/BtvvO2+tzXRUdq94yNGEhYurNmZTvcsL33i4z/52mtnXnv99M503jbNeDRxzucAjIggqqqaLywsvf3tDz366BOr169/85vfuvXYzffd95bNnalnQSFDNBmXV1evffFLX3315VcWF8f33HPn/pWVzY1NVMo7BhBSigGfOPnMkyefede7HnrogbdVirxnKGAwHGitrm9sVVWlCAAVae0dB7nI1rp7UkmB53vbrUckPfio81OEHHvf6S0MImSeYveBk7SHfZOeJiaGJGuaaIWkp8niIVKdUrrEXggl0twZ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" />
        <div class="login-title">Gestão de Ativos</div>
        <div class="login-help">Insira suas credenciais para continuar.</div>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login"):
        u = st.text_input("Usuário", placeholder="Digite seu usuário")
        s = st.text_input("Senha", type="password", placeholder="Digite sua senha")
        entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

    st.markdown(
        '<div style="text-align:center;color:#7b8591;font-size:.80rem;'
        'margin-top:16px;padding-bottom:4px;">'
        'GRUPO FEITAL | Gestão dos Ativos</div>',
        unsafe_allow_html=True
    )

    if entrar:
        with conectar() as conn:
            r = conn.execute(
                "SELECT * FROM usuarios WHERE usuario=? AND ativo=1",
                (u.strip(),)
            ).fetchone()

        if r and r['senha_hash'] == hash_senha(s):
            st.success("✅ Login concluído com sucesso!")
            time.sleep(2)
            st.session_state.logado = True
            st.session_state.usuario = r['usuario']
            st.session_state.nome_usuario = r['nome']
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")

# ------------------------- CABEÇALHO -------------------------
def cabecalho(titulo="Gestão de Ativos", subtitulo="Controle de equipamentos e termos digitais"):
    # Área de usuário/logout fixa no canto superior direito em todas as telas internas.
    nome_seguro = html.escape(str(st.session_state.nome_usuario or "Usuário"))
    st.markdown(f"""
    <style>
    .user-top-right {{
        position: fixed;
        top: 12px;
        right: 18px;
        z-index: 999999;
        display: flex;
        align-items: center;
        gap: 8px;
        background: rgba(255,255,255,.96);
        border: 1px solid #e0e4e9;
        border-radius: 12px;
        padding: 7px 9px;
        box-shadow: 0 5px 18px rgba(25,35,45,.10);
        font-size: .82rem;
        white-space: nowrap;
    }}
    .user-top-right .user-name {{
        color: #66717d;
        font-weight: 650;
    }}
    .user-top-right .logout-link {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 58px;
        padding: 7px 11px;
        border-radius: 8px;
        background: #ffffff;
        border: 1px solid #d8dde3;
        color: #17212b !important;
        text-decoration: none !important;
        font-weight: 700;
    }}
    .user-top-right .logout-link:hover {{
        border-color: #e31b23;
        color: #e31b23 !important;
    }}
    @media(max-width:700px) {{
        .user-top-right {{
            top: 8px;
            right: 8px;
            padding: 5px 6px;
            gap: 5px;
            border-radius: 10px;
            font-size: .72rem;
        }}
        .user-top-right .user-name {{
            max-width: 115px;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .user-top-right .logout-link {{
            min-width: 48px;
            padding: 6px 8px;
        }}
    }}
    </style>
    <div class="user-top-right">
        <span class="user-name">👤 {nome_seguro}</span>
        <a class="logout-link" href="?logout=1" target="_self">Sair</a>
    </div>
    """, unsafe_allow_html=True)

    a,b=st.columns([1.1,4.8])
    with a:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=220)
    with b:
        st.markdown(
            f'<div class="app-header"><div class="app-title">{titulo}</div>'
            f'<div class="app-subtitle">{subtitulo}</div></div>',
            unsafe_allow_html=True
        )

def contagens():
    with conectar() as conn:
        total=conn.execute("SELECT COUNT(*) FROM equipamentos").fetchone()[0]
        uso=conn.execute("SELECT COUNT(*) FROM equipamentos WHERE status='Em uso'").fetchone()[0]
        defeito=conn.execute("SELECT COUNT(*) FROM equipamentos WHERE status='Com defeito'").fetchone()[0]
        pend=conn.execute("SELECT COUNT(*) FROM movimentacoes WHERE status_assinatura='PENDENTE'").fetchone()[0]
        ass=conn.execute("SELECT COUNT(*) FROM movimentacoes WHERE status_assinatura='ASSINADO'").fetchone()[0]
    return total,uso,defeito,pend,ass

# ----------------------- DASHBOARD ---------------------------
def tela_inicio():
    cabecalho(); nome=(st.session_state.nome_usuario or 'Usuário').split()[0]
    st.markdown(f'<div class="hero"><h2>Olá, {nome} 👋</h2><p>Envie termos para assinatura no celular, acompanhe pendências e gere o PDF automaticamente.</p></div>', unsafe_allow_html=True)
    total,uso,defeito,pend,ass=contagens()
    cols=st.columns(5)
    metricas=[
        ("Equipamentos",total),
        ("Em uso",uso),
        ("Com defeito",defeito),
        ("Aguardando assinatura",pend),
        ("Termos assinados",ass),
    ]
    for col,(rot,val) in zip(cols,metricas):
        with col:
            classe_extra = " metric-defeito" if rot == "Com defeito" else ""
            st.markdown(
                f'<div class="metric-card{classe_extra}"><div class="metric-label">{rot}</div>'
                f'<div class="metric-value">{val}</div></div>',
                unsafe_allow_html=True
            )
    if defeito or st.session_state.get("abrir_defeitos"):
        if st.button("🔧 Ver equipamentos com defeito", use_container_width=True):
            st.session_state.abrir_defeitos = True
            navegar('consulta')
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
    if st.button("✏️ Alterar dados do equipamento",use_container_width=True): navegar('alterar')
    st.caption("Gestão de Ativos · assinatura digital, PDF, QR Code e envio por link.")

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
    st.markdown("### Informações do sistema")
    st.info(f"Versão instalada: **{BUILD}**")
    st.warning("Ambiente de testes: no Streamlit Community Cloud, SQLite e arquivos locais não são armazenamento permanente.")

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

def tela_alterar_equipamento():
    cabecalho("Alterar equipamento", "Atualize os dados e registre peças trocadas")
    if st.button("← Voltar"): navegar('inicio')
    with conectar() as conn:
        equipamentos = conn.execute("SELECT * FROM equipamentos ORDER BY patrimonio").fetchall()
    if not equipamentos:
        st.info("Nenhum equipamento cadastrado.")
        return

    mapa = {f"{r['patrimonio']} · {r['tipo']} · {r['marca'] or ''} {r['modelo'] or ''}".strip(): r for r in equipamentos}
    escolha = st.selectbox("Equipamento", list(mapa), key="equipamento_alterar_selecao")
    equipamento = mapa[escolha]

    with st.form("alterar_equipamento"):
        patrimonio = st.text_input("Patrimônio / identificação *", value=equipamento['patrimonio'])
        tipo = st.selectbox("Tipo *", ["Notebook", "Smartphone", "Desktop", "Monitor", "Tablet", "Outro"], index=( ["Notebook", "Smartphone", "Desktop", "Monitor", "Tablet", "Outro"].index(equipamento['tipo']) if equipamento['tipo'] in ["Notebook", "Smartphone", "Desktop", "Monitor", "Tablet", "Outro"] else 5))
        marca = st.text_input("Marca", value=equipamento['marca'] or '')
        modelo = st.text_input("Modelo", value=equipamento['modelo'] or '')
        serie = st.text_input("Nº de série / IMEI", value=equipamento['serie_imei'] or '')
        pecas = st.text_area("Peças trocadas", placeholder="Ex.: tela, bateria, carregador", help="Registre as peças substituídas nesta alteração.")
        observacoes = st.text_area("Observações da alteração")
        salvar = st.form_submit_button("💾 Salvar alteração", type="primary", use_container_width=True)

    if salvar:
        patrimonio = patrimonio.strip().upper()
        if not patrimonio:
            st.error("Informe o patrimônio.")
            return
        campos = []
        valores = {
            "patrimonio": patrimonio,
            "tipo": tipo,
            "marca": marca.strip(),
            "modelo": modelo.strip(),
            "serie_imei": serie.strip(),
        }
        for campo, valor in valores.items():
            anterior = equipamento[campo] or ''
            if str(anterior) != str(valor):
                campos.append(f"{campo}: {anterior or '-'} -> {valor or '-'}")
        if not campos and not pecas.strip() and not observacoes.strip():
            st.warning("Nenhuma alteração foi informada.")
            return
        try:
            with conectar() as conn:
                conflito = conn.execute("SELECT id FROM equipamentos WHERE patrimonio=? AND id<>?", (patrimonio, equipamento['id'])).fetchone()
                if conflito:
                    st.error("Já existe outro equipamento com esse patrimônio.")
                    return
                conn.execute("UPDATE equipamentos SET patrimonio=?, tipo=?, marca=?, modelo=?, serie_imei=?, observacoes=? WHERE id=?", (patrimonio, tipo, valores['marca'], valores['modelo'], valores['serie_imei'], observacoes.strip() or equipamento['observacoes'], equipamento['id']))
                if equipamento['patrimonio'] != patrimonio:
                    conn.execute("UPDATE movimentacoes SET patrimonio=? WHERE patrimonio=?", (patrimonio, equipamento['patrimonio']))
                conn.execute("""INSERT INTO alteracoes_equipamentos
                    (equipamento_id, patrimonio_anterior, patrimonio_novo, campos_alterados,
                     pecas_trocadas, observacoes, responsavel, data_alteracao)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (equipamento['id'], equipamento['patrimonio'], patrimonio, "\n".join(campos), pecas.strip(), observacoes.strip(), st.session_state.nome_usuario, agora_iso()))
                conn.commit()
            st.success("Dados do equipamento atualizados e alteração registrada.")
        except sqlite3.IntegrityError:
            st.error("Não foi possível salvar: o patrimônio informado já existe.")

    with conectar() as conn:
        historico = conn.execute("SELECT * FROM alteracoes_equipamentos WHERE equipamento_id=? ORDER BY id DESC LIMIT 10", (equipamento['id'],)).fetchall()
    if historico:
        st.markdown("### Histórico de alterações")
        for alteracao in historico:
            st.markdown('<div class="mobile-card">', unsafe_allow_html=True)
            st.write(f"**Data:** {formatar_data_br(alteracao['data_alteracao'])} · **Responsável:** {alteracao['responsavel']}")
            if alteracao['campos_alterados']:
                st.text(alteracao['campos_alterados'])
            if alteracao['pecas_trocadas']:
                st.write(f"**Peças trocadas:** {alteracao['pecas_trocadas']}")
            if alteracao['observacoes']:
                st.write(f"**Observações:** {alteracao['observacoes']}")
            st.markdown('</div>', unsafe_allow_html=True)

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
        acess=st.multiselect("Acessórios",["Carregador","Mouse","Mochila","Teclado","Dock station","Cabo USB","Outro"])
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
    st.markdown("### Fotos do estado na devolução (até 3)")
    equipamento_key = eq['patrimonio'].replace(' ', '_')
    fotos_devolucao = st.session_state.setdefault(f"fotos_devolucao_{equipamento_key}", {})
    fotos_pendentes = st.session_state.setdefault(f"fotos_devolucao_pendentes_{equipamento_key}", {})
    fotos_reset = st.session_state.setdefault(f"fotos_devolucao_reset_{equipamento_key}", {})
    labels_fotos = ["Frente do equipamento", "Parte traseira do equipamento", "Detalhe do estado"]
    posicao_foto = st.selectbox("Qual foto deseja adicionar?", labels_fotos, key=f"devolucao_posicao_{equipamento_key}")
    indice_foto = labels_fotos.index(posicao_foto)
    fonte_foto = st.radio("Adicionar foto por", ["Câmera", "Galeria"], horizontal=True, key=f"devolucao_fonte_foto_{equipamento_key}")

    pendente = fotos_pendentes.get(indice_foto)
    recebido = None
    chave_foto = fotos_reset.get(indice_foto, 0)
    chave_upload = f"devolucao_upload_{equipamento_key}_{indice_foto}_{chave_foto}"
    if pendente is None:
        if fonte_foto == "Câmera":
            recebido = st.camera_input("📷 Tirar foto do equipamento", key=chave_upload)
        else:
            recebido = st.file_uploader("🖼️ Escolher foto do equipamento", type=["png", "jpg", "jpeg"], key=chave_upload)
    else:
        recebido = None

    if recebido is None:
        recebido = st.session_state.get(chave_upload)

    if recebido is not None and recebido.getvalue():
        fotos_pendentes[indice_foto] = {"bytes": recebido.getvalue(), "label": posicao_foto}
        st.session_state[f"devolucao_foto_bytes_{equipamento_key}_{indice_foto}"] = recebido.getvalue()
        st.rerun()

    pendente = fotos_pendentes.get(indice_foto)

    if pendente is not None:
        st.info(f"Confira a foto de **{pendente['label'].lower()}** antes de confirmar.")
        st.image(pendente["bytes"], caption=f"Pré-visualização — {pendente['label']}")
        foto_ok, foto_excluir = st.columns(2)
        with foto_ok:
            confirmar_foto = st.button("✅ Foto OK", type="primary", use_container_width=True, key=f"devolucao_foto_ok_{equipamento_key}_{indice_foto}")
        with foto_excluir:
            excluir_foto = st.button("🗑️ Excluir e refazer", use_container_width=True, key=f"devolucao_foto_excluir_{equipamento_key}_{indice_foto}")
        if confirmar_foto:
            fotos_devolucao[indice_foto] = pendente["bytes"]
            fotos_pendentes.pop(indice_foto, None)
            fotos_reset[indice_foto] = fotos_reset.get(indice_foto, 0) + 1
            st.session_state.pop(f"devolucao_foto_bytes_{equipamento_key}_{indice_foto}", None)
            st.rerun()
        elif excluir_foto:
            fotos_pendentes.pop(indice_foto, None)
            fotos_devolucao.pop(indice_foto, None)
            fotos_reset[indice_foto] = fotos_reset.get(indice_foto, 0) + 1
            st.session_state.pop(f"devolucao_foto_bytes_{equipamento_key}_{indice_foto}", None)
            st.rerun()

    if indice_foto in fotos_devolucao and indice_foto not in fotos_pendentes:
        st.success(f"✅ {posicao_foto}: foto OK.")
        if st.button("🗑️ Excluir foto confirmada e refazer", use_container_width=True, key=f"devolucao_foto_refazer_{equipamento_key}_{indice_foto}"):
            fotos_devolucao.pop(indice_foto, None)
            fotos_reset[indice_foto] = fotos_reset.get(indice_foto, 0) + 1
            st.rerun()

    lista_fotos = "".join(
        f"<div class='foto-status {'ok' if indice in fotos_devolucao else 'pendente'}'>"
        f"<span>{indice + 1}.</span> {label} "
        f"<strong>{'OK' if indice in fotos_devolucao else 'PENDENTE'}</strong></div>"
        for indice, label in enumerate(labels_fotos)
    )
    st.markdown(f"<div class='foto-status-list'>{lista_fotos}</div>", unsafe_allow_html=True)
    st.caption(f"Fotos confirmadas: {len(fotos_devolucao)} de 3")
    with st.form('devolucao'):
        cond=st.radio("Condição",["Em perfeito estado","Apresentando defeito","Quebrado"]); obs=st.text_area("Observações / descrição"); resp=st.text_input("Responsável pela devolução",value=colab); ok=st.checkbox("Confirmo o recebimento e a condição acima."); salvar=st.form_submit_button("📥 Registrar Devolução",type="primary",use_container_width=True)
    if salvar:
        if not resp.strip() or not ok: st.error("Informe o responsável e confirme."); return
        if not fotos_devolucao: st.error("Confirme pelo menos uma foto do estado do equipamento."); return
        status={"Em perfeito estado":"Disponível","Apresentando defeito":"Com defeito","Quebrado":"Quebrado"}[cond]
        foto_paths = []
        identificador_fotos = datetime.now().strftime('%Y%m%d%H%M%S')
        for indice, foto_bytes in sorted(fotos_devolucao.items()):
            foto_path = UPLOAD_DIR / f"devolucao_{eq['patrimonio'].replace(' ', '_')}_{identificador_fotos}_{indice}.jpg"
            imagem_devolucao = PILImage.open(BytesIO(foto_bytes)).convert('RGB')
            imagem_devolucao.save(foto_path, quality=88)
            foto_paths.append(str(foto_path))
        foto_path = json.dumps(foto_paths)
        with conectar() as conn:
            conn.execute("INSERT INTO movimentacoes(tipo_movimento,patrimonio,colaborador,condicao,observacoes,responsavel_ti,aceite_nome,aceite_confirmado,data_movimento,status_assinatura,foto_path) VALUES('DEVOLUÇÃO',?,?,?,?,?,?,1,?,'N/A',?)",(eq['patrimonio'],resp.strip(),cond,obs.strip(),st.session_state.nome_usuario,resp.strip(),agora_iso(),str(foto_path))); conn.execute("UPDATE equipamentos SET status=? WHERE patrimonio=?",(status,eq['patrimonio'])); conn.commit()
        st.success(f"Devolução registrada: {cond}.")
        st.session_state.pop(f"fotos_devolucao_{equipamento_key}", None)
        st.session_state.pop(f"fotos_devolucao_pendentes_{equipamento_key}", None)

def dados_uso_atual(patrimonio):
    """Retorna a última entrega assinada do equipamento."""
    with conectar() as conn:
        return conn.execute(
            """SELECT colaborador, empresa_setor, data_movimento, assinado_em
               FROM movimentacoes
               WHERE patrimonio=?
                 AND tipo_movimento='ENTREGA'
                 AND status_assinatura='ASSINADO'
               ORDER BY id DESC
               LIMIT 1""",
            (patrimonio,)
        ).fetchone()


def dados_ultima_devolucao(patrimonio):
    """Retorna quem devolveu o equipamento e os dados da última devolução."""
    with conectar() as conn:
        return conn.execute(
            """SELECT colaborador, data_movimento, condicao, observacoes, foto_path
               FROM movimentacoes
               WHERE patrimonio=?
                 AND tipo_movimento='DEVOLUÇÃO'
               ORDER BY id DESC
               LIMIT 1""",
            (patrimonio,)
        ).fetchone()


def formatar_data_br(valor):
    if not valor:
        return "-"
    try:
        dt = datetime.fromisoformat(str(valor))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(valor).replace("T", " ")


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
    if not rows:
        st.info("Nenhum equipamento encontrado.")
        return

    somente_defeitos = st.session_state.pop("abrir_defeitos", False)
    if somente_defeitos:
        rows = [r for r in rows if r['status'] in ('Com defeito', 'Quebrado')]
        st.info("Exibindo equipamentos com defeito ou quebrados.")
        if not rows:
            st.success("Nenhum equipamento com defeito ou quebrado foi encontrado.")
            return

    opcoes = {f"{r['patrimonio']} · {r['tipo']} · {r['status']}": r for r in rows}
    escolha = st.selectbox("Equipamento", list(opcoes), key="consulta_equipamento")
    selecionado = opcoes[escolha]
    st.markdown("### Detalhes do equipamento selecionado")
    rows = [selecionado]

    for r in rows:
        st.markdown('<div class="mobile-card">',unsafe_allow_html=True)
        a,b=st.columns([3,1])

        with a:
            st.markdown(f"### {r['patrimonio']} · {r['tipo']}")
            st.write(f"**Marca/Modelo:** {r['marca'] or '-'} {r['modelo'] or ''}")
            st.write(f"**Série/IMEI:** {r['serie_imei'] or '-'}")

        with b:
            st.markdown(badge(r['status']),unsafe_allow_html=True)

        # Informações adicionais conforme o status do equipamento
        if r['status'] == 'Em uso':
            uso = dados_uso_atual(r['patrimonio'])
            st.markdown("---")
            if uso:
                st.write(f"👤 **Colaborador:** {uso['colaborador'] or '-'}")
                st.write(f"🏢 **Setor:** {uso['empresa_setor'] or '-'}")
                data_retirada = uso['assinado_em'] or uso['data_movimento']
                st.write(f"📅 **Data de retirada:** {formatar_data_br(data_retirada)}")
            else:
                st.caption("Não foi localizada a movimentação de entrega deste equipamento.")

        elif r['status'] in ('Com defeito', 'Quebrado'):
            devolucao = dados_ultima_devolucao(r['patrimonio'])
            st.markdown("---")
            if devolucao:
                st.write(f"👤 **Devolvido por:** {devolucao['colaborador'] or '-'}")
                st.write(f"📅 **Data da devolução:** {formatar_data_br(devolucao['data_movimento'])}")
                st.write(f"🛠️ **Condição:** {devolucao['condicao'] or r['status']}")
                if devolucao['observacoes']:
                    st.write(f"📝 **Observação:** {devolucao['observacoes']}")
                fotos = parse_foto_paths(devolucao['foto_path'])
                for foto in fotos:
                    if Path(foto).exists():
                        st.image(foto, caption="Foto registrada na devolução")
            else:
                st.caption("Não foi localizada a devolução que gerou este status.")

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
# Logout pelo botão fixo do cabeçalho.
try:
    logout_publico = st.query_params.get('logout', '')
    if isinstance(logout_publico, list):
        logout_publico = logout_publico[0] if logout_publico else ''
except Exception:
    logout_publico = ''

if str(logout_publico) == '1':
    st.query_params.clear()
    st.session_state.logado = False
    st.session_state.usuario = ""
    st.session_state.nome_usuario = ""
    st.session_state.pagina = "inicio"
    st.rerun()

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
    paginas={'inicio':tela_inicio,'config':tela_config,'cadastro':tela_cadastro,'alterar':tela_alterar_equipamento,'entrega':tela_entrega,'devolucao':tela_devolucao,'consulta':tela_consulta,'historico':tela_historico}
    paginas.get(st.session_state.pagina,tela_inicio)()
