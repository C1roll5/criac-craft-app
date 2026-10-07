import datetime
import json
import unicodedata
from io import BytesIO

import extra_streamlit_components as stx
import pandas as pd
import streamlit as st
from supabase import Client, create_client

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA E TEMA
# =============================================================================
st.set_page_config(page_title="Cria.C Craft", page_icon="✂️", layout="wide")

CSS_PERSONALIZADO = """
<style>
/* Cole aqui o seu CSS original com a paleta da logo Cria.C Craft */
</style>
"""
st.markdown(CSS_PERSONALIZADO, unsafe_allow_html=True)

# =============================================================================
# CONSTANTES
# =============================================================================
COOKIE = "criac_craft_rt"  # guarda o refresh_token (nunca a senha)

UNIDADES = ["Unidade", "Folha", "ml", "L", "g", "kg", "Metro", "Pacote", "Caixa"]

CATEGORIAS = {
    "📖 Papelaria & Encadernação (Cadernos, Agendas, Planners)": {"lucro": 40.0, "risco": 5.0},
    "☕ Sublimação (Canecas, Azulejos, Squeezes)": {"lucro": 35.0, "risco": 8.0},
    "🪵 Gravação a Laser & Corte de Madeira/MDF": {"lucro": 45.0, "risco": 10.0},
    "🖼️ Quadros & Placas Decorativas": {"lucro": 35.0, "risco": 5.0},
    "✨ Resina & Velas Artesanais": {"lucro": 45.0, "risco": 10.0},
    "🥤 Brindes & Acrílico (Copos, Vinil, Acessórios)": {"lucro": 30.0, "risco": 5.0},
    "🪡 Costura Criativa (Necessaires, Almofadas, Bolsas)": {"lucro": 35.0, "risco": 5.0},
    "🏷️ Impressões & Adesivos (Adesivos, Cartões, Rótulos)": {"lucro": 30.0, "risco": 3.0},
    "⚙️ Outra Categoria / Personalizado": {"lucro": 30.0, "risco": 5.0},
}

CFG_PADRAO = {
    "salario_pretendido": 2000.0,
    "horas_mes": 160.0,
    "custos_fixos_pct": 10.0,
    "taxa_cartao_pct": 4.5,
    "reserva_giro_pct": 10.0,
}

# (rótulo, quantidade mínima, fator de tempo por peça em lote)
FAIXAS_ATACADO = [
    ("30 a 49 un", 30, 0.55),
    ("50 a 99 un", 50, 0.40),
    ("100+ un", 100, 0.33),
]


# =============================================================================
# FUNÇÕES AUXILIARES (formatação e conversão)
# =============================================================================
def to_f(v, padrao=0.0):
    """Converte para float; usa o padrão se vier None/inválido."""
    try:
        return padrao if v is None else float(v)
    except (TypeError, ValueError):
        return padrao


def brl(v):
    """1234.5 -> 'R$ 1.234,50'."""
    s = f"{to_f(v):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_num(v, casas=2):
    s = f"{to_f(v):,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def normalizar(txt):
    """Remove acentos/espaços e passa para minúsculas."""
    txt = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode()
    return txt.strip().lower()


def chave_cat(cat):
    """Ignora o emoji do início para comparar categorias."""
    return str(cat or "").split(" ", 1)[-1].strip()


_CAT_POR_NOME = {chave_cat(k): v for k, v in CATEGORIAS.items()}


def risco_da_categoria(cat):
    return _CAT_POR_NOME.get(chave_cat(cat), {"risco": 5.0})["risco"]


def tabela(df):
    """st.dataframe compatível com versões novas e antigas do Streamlit."""
    try:
        st.dataframe(df, width="stretch")
    except Exception:
        st.dataframe(df, use_container_width=True)


def para_excel(df, aba="Dados"):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=aba)
    return buf.getvalue()


def botoes_exportar(df, nome_base):
    c1, c2, _ = st.columns([1, 1, 3])
    c1.download_button(
        "⬇️ Baixar CSV",
        df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
        file_name=f"{nome_base}.csv",
        mime="text/csv",
        key=f"csv_{nome_base}",
    )
    try:
        c2.download_button(
            "⬇️ Baixar Excel",
            para_excel(df),
            file_name=f"{nome_base}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"xlsx_{nome_base}",
        )
    except ImportError:
        c2.caption("Instale `openpyxl` para exportar em Excel.")


def flash(msg, icone="✅"):
    """Guarda uma mensagem para aparecer após o st.rerun()."""
    st.session_state["_flash"] = (msg, icone)


def mostrar_flash():
    f = st.session_state.pop("_flash", None)
    if f:
        st.toast(f[0], icon=f[1])


# =============================================================================
# CÁLCULO DE PREÇO (fórmula única, usada na Calculadora e nas Fichas)
# =============================================================================
def calcular_preco(custo_materiais, tempo_min, valor_hora, risco, custos_fixos,
                   lucro, taxa, taxa_fixa):
    """Todos os percentuais entram como fração (0.10 = 10%)."""
    materiais_risco = custo_materiais * (1 + risco)
    mao_obra = (tempo_min / 60.0) * valor_hora
    direto = materiais_risco + mao_obra
    fixos = direto * custos_fixos
    custo_producao = direto + fixos
    com_lucro = custo_producao * (1 + lucro)
    if taxa < 1:
        preco = (com_lucro + taxa_fixa) / (1 - taxa)
    else:
        preco = com_lucro
    taxas = preco * taxa + taxa_fixa
    return {
        "materiais_risco": materiais_risco,
        "mao_obra": mao_obra,
        "fixos": fixos,
        "custo_producao": custo_producao,
        "preco": preco,
        "taxas": taxas,
        "lucro_real": preco - custo_producao - taxas,
    }


def lista_materiais(ficha):
    mats = ficha.get("materiais") or ficha.get("composicao") or []
    if isinstance(mats, str):
        try:
            mats = json.loads(mats)
        except Exception:
            mats = []
    return [m for m in mats if isinstance(m, dict)]


def tempo_ficha(f, padrao=0.0):
    v = f.get("tempo_minutos")
    if v is None:
        v = f.get("tempo_producao")
    return to_f(v, padrao)


def parametros_ficha(f):
    """Parâmetros de precificação salvos na ficha (com fallback p/ fichas antigas)."""
    risco = f.get("risco_pct")
    if risco is None:
        risco = risco_da_categoria(f.get("categoria"))
    return {
        "risco": to_f(risco, 5.0) / 100.0,
        "custos_fixos": to_f(f.get("custos_fixos_pct"), 10.0) / 100.0,
        "lucro": to_f(f.get("margem_lucro_pct"), 30.0) / 100.0,
        "taxa": to_f(f.get("taxa_marketplace_pct"), 18.0) / 100.0,
        "taxa_fixa": to_f(f.get("taxa_marketplace_fixa"), 3.0),
    }


def custo_unitario_insumo(ins):
    q = to_f(ins.get("qtd_embalagem"), 0.0)
    return to_f(ins.get("preco_embalagem")) / q if q > 0 else 0.0


def recalcular_ficha(f, insumos_por_id, valor_hora, qtds=None, params=None, tempo=None):
    """Recalcula a ficha com os preços ATUAIS dos insumos."""
    comp, custo_mat = [], 0.0
    for idx, m in enumerate(lista_materiais(f)):
        qtd = to_f(qtds[idx], 1.0) if qtds else to_f(m.get("qtd"), 1.0)
        ins = insumos_por_id.get(m.get("insumo_id"))
        if ins:
            cu = custo_unitario_insumo(ins)
            nome = ins.get("nome", m.get("nome", "Insumo"))
        else:
            cu = to_f(m.get("custo_unitario"))
            nome = m.get("nome", "Insumo")
        ct = cu * qtd
        custo_mat += ct
        novo = dict(m)
        novo.update({"nome": nome, "qtd": qtd, "custo_unitario": cu, "custo_total": ct})
        comp.append(novo)
    p = params or parametros_ficha(f)
    t = tempo_ficha(f) if tempo is None else tempo
    calc = calcular_preco(custo_mat, t, valor_hora, **p)
    return custo_mat, comp, calc


def tabela_atacado(f, valor_hora):
    """Preço base PIX e faixas de atacado de uma ficha."""
    p = parametros_ficha(f)
    tempo = tempo_ficha(f, 15.0)
    preco_pf = to_f(f.get("preco_sugerido"))
    custo_mat = to_f(f.get("custo_materiais"))
    base = max(preco_pf * (1 - p["taxa"]) - p["taxa_fixa"], custo_mat * 1.2)
    fator = 1 + p["custos_fixos"]
    lucro_rs = (custo_mat + (tempo / 60.0) * valor_hora) * fator * p["lucro"]

    linhas = []
    for rotulo, qtd, ft in FAIXAS_ATACADO:
        mo = (tempo * ft / 60.0) * valor_hora
        preco_peca = (custo_mat + mo) * fator + lucro_rs
        economia = max(0.0, (base - preco_peca) / base * 100) if base > 0 else 0.0
        linhas.append({
            "faixa": rotulo, "qtd": qtd, "economia": economia,
            "preco_peca": preco_peca, "total_lote": preco_peca * qtd,
        })
    return base, linhas


def gerar_pdf_catalogo(itens, taxa_cartao):
    from fpdf import FPDF

    def t(s):
        return str(s).encode("latin-1", "ignore").decode("latin-1").strip()

    def linha(pdf, texto, h=5):
        pdf.cell(0, h, t(texto), new_x="LMARGIN", new_y="NEXT")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    linha(pdf, "Catálogo Cria.C Craft", 10)
    pdf.set_font("Helvetica", "", 10)
    linha(pdf, f"Gerado em {datetime.date.today():%d/%m/%Y}", 6)
    pdf.ln(4)

    for it in itens:
        pdf.set_font("Helvetica", "B", 12)
        linha(pdf, f"{it['nome']} - {it['categoria']}", 7)
        pdf.set_font("Helvetica", "", 10)
        linha(pdf, f"Varejo (1 a 29 un): {brl(it['varejo'])}")
        linha(pdf, f"Atacado PIX (1 a 29 un): {brl(it['base'])}")
        for l in it["faixas"]:
            linha(pdf, f"   {l['faixa']}: {brl(l['preco_peca'])} por peça (lote: {brl(l['total_lote'])})")
        pdf.ln(3)

    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(
        0, 5,
        t(f"Pagamentos via cartão de crédito/débito possuem acréscimo de {fmt_num(taxa_cartao, 1)}% sobre o valor total."),
        new_x="LMARGIN", new_y="NEXT",
    )
    return bytes(pdf.output())


# =============================================================================
# BANCO DE DADOS (cliente POR SESSÃO + cache por usuária)
# =============================================================================
def get_db() -> Client:
    """Um cliente Supabase por sessão do navegador (nunca compartilhado)."""
    if "sb" not in st.session_state:
        url = st.secrets["SUPABASE_URL"].strip().rstrip("/")
        key = st.secrets["SUPABASE_KEY"].strip()  # use a chave ANON, nunca a service_role
        st.session_state["sb"] = create_client(url, key)
    return st.session_state["sb"]


@st.cache_data(ttl=60, show_spinner=False)
def carregar(_db, tabela, user_id, ordem=None):
    q = _db.table(tabela).select("*").eq("user_id", user_id)
    if ordem:
        q = q.order(ordem)
    return q.execute().data or []


@st.cache_data(ttl=60, show_spinner=False)
def carregar_config(_db, user_id):
    rows = (
        _db.table("configuracoes_usuario").select("*").eq("user_id", user_id).limit(1).execute().data
    )
    row = rows[0] if rows else {}
    cfg = dict(CFG_PADRAO)
    for k in CFG_PADRAO:
        cfg[k] = to_f(row.get(k), CFG_PADRAO[k])
    cfg["id"] = row.get("id")
    return cfg


def valor_hora_de(cfg):
    h = cfg["horas_mes"]
    return cfg["salario_pretendido"] / h if h > 0 else 0.0


def executar(consulta):
    """Executa uma escrita no banco, mostra erro amigável e limpa o cache."""
    try:
        res = consulta.execute()
    except Exception as e:
        st.error(f"Erro no banco de dados: {e}")
        return None
    st.cache_data.clear()
    return res


def botao_excluir(label, chave, ao_confirmar, aviso=None):
    """Exclusão em duas etapas (pede confirmação)."""
    flag = f"conf_{chave}"
    if not st.session_state.get(flag):
        if st.button(label, key=f"btn_{chave}", type="primary"):
            st.session_state[flag] = True
            st.rerun()
    else:
        st.warning(aviso or "Tem certeza? Essa ação não pode ser desfeita.")
        c1, c2 = st.columns(2)
        if c1.button("✅ Sim, excluir", key=f"sim_{chave}", type="primary"):
            st.session_state[flag] = False
            ao_confirmar()
        if c2.button("Cancelar", key=f"nao_{chave}"):
            st.session_state[flag] = False
            st.rerun()


# =============================================================================
# AUTENTICAÇÃO (sessão real + cookie com refresh_token)
# =============================================================================
def cookie_existe(cm):
    return bool(cm.get(cookie=COOKIE))


def tentar_restaurar(cm):
    """Restaura a sessão a partir do refresh_token guardado no navegador."""
    if st.session_state.get("logout_flag"):
        return
    rt = cm.get(cookie=COOKIE)
    if not rt:
        return
    try:
        res = get_db().auth.refresh_session(rt)
        if res and res.user and res.session:
            st.session_state.user = res.user
            st.session_state.manter = True
            st.rerun()
    except Exception:
        if cookie_existe(cm):
            cm.delete(COOKIE, key="del_cookie_invalido")


def encerrar_sessao():
    try:
        get_db().auth.sign_out()
    except Exception:
        pass
    st.session_state.clear()
    st.session_state["logout_flag"] = True


def tela_login(cm):
    st.title("🎨 Artesanato Cria.C")
    st.subheader("Arte, paixão e personalização — Sistema de Gestão")

    if st.session_state.get("logout_flag") and cookie_existe(cm):
        cm.delete(COOKIE, key="del_cookie_logout")

    tab_login, tab_cad = st.tabs(["🔑 Entrar", "📝 Criar Conta"])

    with tab_login:
        with st.form("form_login"):
            email = st.text_input("E-mail")
            senha = st.text_input("Senha", type="password")
            manter = st.checkbox("Manter-me conectado neste dispositivo", value=True)
            entrar = st.form_submit_button("Acessar Painel")
        if entrar:
            try:
                res = get_db().auth.sign_in_with_password({"email": email, "password": senha})
                st.session_state.user = res.user
                st.session_state.manter = manter
                st.session_state["logout_flag"] = False
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao entrar: {e}")

    with tab_cad:
        with st.form("form_cadastro"):
            c_email = st.text_input("E-mail para cadastro")
            c_senha = st.text_input("Senha", type="password")
            cadastrar = st.form_submit_button("Cadastrar Nova Conta")
        if cadastrar:
            try:
                get_db().auth.sign_up({"email": c_email, "password": c_senha})
                st.success("Conta criada! Se necessário, confirme o e-mail ou faça login.")
            except Exception as e:
                st.error(f"Erro ao cadastrar: {e}")


# =============================================================================
# ABA: CONFIGURAÇÕES
# =============================================================================
def aba_configuracoes(db, uid, cfg):
    st.header("⚙️ Configurações")
    st.write("Valores usados em todo o sistema (calculadora, fichas, catálogo e caixa).")

    with st.form("form_config"):
        c1, c2 = st.columns(2)
        salario = c1.number_input("Salário pretendido por mês (R$)", min_value=0.0,
                                  value=cfg["salario_pretendido"], step=100.0)
        horas = c2.number_input("Horas trabalhadas por mês", min_value=1.0,
                                value=cfg["horas_mes"], step=1.0,
                                help="160h = 40h/semana (8h/dia de seg a sex)")
        c3, c4, c5 = st.columns(3)
        cf = c3.number_input("Custos fixos / energia padrão (%)", min_value=0.0, max_value=30.0,
                             value=cfg["custos_fixos_pct"], step=1.0)
        cartao = c4.number_input("Acréscimo no cartão - atacado/kits (%)", min_value=0.0, max_value=30.0,
                                 value=cfg["taxa_cartao_pct"], step=0.5)
        reserva = c5.number_input("Reserva / giro do caixa (%)", min_value=0.0, max_value=50.0,
                                  value=cfg["reserva_giro_pct"], step=1.0)
        salvar = st.form_submit_button("💾 Salvar configurações")

    st.caption(f"💡 Com esses valores, o seu tempo vale **{brl(salario / horas)}/hora**.")

    if salvar:
        payload = {
            "user_id": uid,
            "salario_pretendido": salario,
            "horas_mes": int(horas),
            "custos_fixos_pct": cf,
            "taxa_cartao_pct": cartao,
            "reserva_giro_pct": reserva,
        }
        if cfg.get("id"):
            res = executar(db.table("configuracoes_usuario").update(payload).eq("id", cfg["id"]))
        else:
            res = executar(db.table("configuracoes_usuario").insert(payload))
        if res is not None:
            flash("Configurações salvas!")
            st.rerun()


# =============================================================================
# ABA 1: CADASTRO DE INSUMOS
# =============================================================================
def aba_insumos(db, uid, cfg):
    st.header("📦 Cadastro de Insumos e Materiais")
    st.write("Gerencie seus materiais, fitas, papéis e insumos aqui.")

    with st.expander("➕ Cadastrar Novo Insumo", expanded=True):
        with st.form("form_novo_insumo", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome do Material / Insumo")
            unidade = c2.selectbox("Unidade de Medida", options=UNIDADES)
            c3, c4 = st.columns(2)
            preco = c3.number_input("Preço Pago (R$)", min_value=0.0, step=0.50, format="%.2f")
            qtd = c4.number_input("Quantidade na Embalagem", min_value=0.01, step=1.0, value=1.0)
            enviar = st.form_submit_button("💾 Cadastrar Insumo")
        if enviar:
            if nome and preco > 0 and qtd > 0:
                res = executar(db.table("insumos").insert({
                    "user_id": uid, "nome": nome, "unidade": unidade,
                    "preco_embalagem": preco, "qtd_embalagem": qtd,
                }))
                if res is not None:
                    flash(f"Insumo '{nome}' cadastrado com sucesso!")
                    st.rerun()
            else:
                st.warning("Preencha todos os campos corretamente.")

    insumos = carregar(db, "insumos", uid, "nome")

    st.divider()
    st.subheader("📋 Meus Insumos")
    if not insumos:
        st.info("Nenhum insumo cadastrado ainda.")
        return

    df = pd.DataFrame([{
        "Insumo": i.get("nome"),
        "Unidade": i.get("unidade") or i.get("unidade_medida", ""),
        "Preço pago": to_f(i.get("preco_embalagem")),
        "Qtd na embalagem": to_f(i.get("qtd_embalagem")),
        "Custo por unidade": custo_unitario_insumo(i),
    } for i in insumos])
    tabela(df)
    botoes_exportar(df, "insumos")

    st.divider()
    st.subheader("⚙️ Alterar ou Eliminar Insumo")
    por_id = {i["id"]: i for i in insumos}
    sel = st.selectbox(
        "Selecione o insumo para gerenciar:", options=list(por_id.keys()),
        format_func=lambda k: por_id[k].get("nome", "Sem nome"), key="sb_gerenciar_insumo",
    )
    atual = por_id[sel]

    with st.form(f"form_edit_insumo_{sel}"):
        novo_nome = st.text_input("Nome", value=atual.get("nome", ""))
        unid_salva = atual.get("unidade") or atual.get("unidade_medida", "Unidade")
        nova_unidade = st.selectbox("Unidade", options=UNIDADES,
                                    index=UNIDADES.index(unid_salva) if unid_salva in UNIDADES else 0)
        novo_preco = st.number_input("Preço (R$)", value=to_f(atual.get("preco_embalagem")),
                                     min_value=0.0, step=0.50)
        nova_qtd = st.number_input("Qtd", value=to_f(atual.get("qtd_embalagem"), 1.0),
                                   min_value=0.01, step=1.0)
        salvar = st.form_submit_button("💾 Guardar Alterações")
    if salvar:
        res = executar(db.table("insumos").update({
            "nome": novo_nome, "unidade": nova_unidade,
            "preco_embalagem": novo_preco, "qtd_embalagem": nova_qtd,
        }).eq("id", sel).eq("user_id", uid))
        if res is not None:
            flash("Insumo atualizado! Use 'Recalcular' nas Fichas Técnicas para atualizar os preços.")
            st.rerun()

    # Avisa se o insumo é usado em alguma ficha
    fichas = carregar(db, "fichas_tecnicas", uid)
    usado_em = [f.get("nome_produto", "?") for f in fichas
                if any(m.get("insumo_id") == sel for m in lista_materiais(f))]
    aviso = None
    if usado_em:
        aviso = ("⚠️ Este insumo é usado nas fichas: **" + ", ".join(usado_em) +
                 "**. Se eliminar, elas passam a usar o último custo salvo. Tem certeza?")
        st.info("Este insumo é usado em: " + ", ".join(usado_em))

    def _excluir():
        if executar(db.table("insumos").delete().eq("id", sel).eq("user_id", uid)) is not None:
            flash("Insumo eliminado.", "🗑️")
            st.rerun()

    botao_excluir("🗑 Eliminar Insumo", f"insumo_{sel}", _excluir, aviso)


# =============================================================================
# ABA 2: CALCULADORA DE PREÇOS
# =============================================================================
def aba_calculadora(db, uid, cfg):
    st.header("🧮 Calculadora de Preços por Categoria")
    st.write("Calcule o preço ideal de venda dos seus produtos artesanais.")

    insumos = carregar(db, "insumos", uid, "nome")
    if not insumos:
        st.warning("Cadastre primeiro os seus insumos para poder precificar!")
        return

    valor_hora = valor_hora_de(cfg)
    st.caption(f"💡 O seu tempo vale **{brl(valor_hora)}/hora** "
               f"({brl(cfg['salario_pretendido'])} ÷ {int(cfg['horas_mes'])}h). "
               "Ajuste em ⚙️ Configurações.")

    st.subheader("1. Produto e Materiais")
    c1, c2 = st.columns([2, 1])
    nome_produto = c1.text_input("Nome do Produto", placeholder="Ex: Quadro Mosaico em MDF Laser")
    tempo = c2.number_input("Tempo de Produção (minutos)", min_value=0, value=30, step=5)

    cat = st.selectbox("Categoria do Produto:", options=list(CATEGORIAS.keys()))
    cfg_cat = CATEGORIAS[cat]

    por_id = {i["id"]: i for i in insumos}
    selecionados = st.multiselect(
        "Selecione os materiais usados:", options=list(por_id.keys()),
        format_func=lambda k: f"{por_id[k]['nome']} ({por_id[k].get('unidade') or 'un'})",
    )

    composicao, custo_materiais = [], 0.0
    if selecionados:
        st.markdown("**Quantidade gasta de cada material:**")
        for iid in selecionados:
            ins = por_id[iid]
            cu = custo_unitario_insumo(ins)
            a, b, c = st.columns([3, 2, 2])
            a.write(f"• {ins['nome']}")
            q = b.number_input(f"Qtd ({ins.get('unidade') or 'un'})", min_value=0.001,
                               value=1.0, step=0.5, key=f"calc_qtd_{iid}")
            custo_item = cu * q
            custo_materiais += custo_item
            c.write(brl(custo_item))
            composicao.append({"insumo_id": iid, "nome": ins["nome"], "qtd": q,
                               "custo_unitario": cu, "custo_total": custo_item})

    st.divider()
    st.subheader("2. Custos Fixos, Perdas, Lucro e Taxas")
    d1, d2, d3 = st.columns(3)
    pct_fixos = d1.number_input("Custos Fixos / Energia (%)", min_value=0.0, max_value=30.0,
                                value=cfg["custos_fixos_pct"], step=1.0,
                                help="Luz, desgaste de máquinas, internet e manutenção.")
    pct_risco = d2.number_input("Perdas / Testes (%)", min_value=0.0, max_value=50.0,
                                value=float(cfg_cat["risco"]), step=1.0,
                                help="Sugerido pela categoria; ajuste se precisar.")
    pct_lucro = d3.number_input("Lucro da Empresa (%)", min_value=30.0, max_value=200.0,
                                value=float(cfg_cat["lucro"]), step=5.0,
                                help="Mínimo de 30%.")
    e1, e2 = st.columns(2)
    pct_taxa = e1.number_input("Taxa % Canal (Shopee/Cartão)", min_value=0.0, max_value=50.0,
                               value=18.0, step=1.0)
    taxa_fixa = e2.number_input("Taxa Fixa Venda (R$)", min_value=0.0, value=3.0, step=0.5)

    calc = calcular_preco(custo_materiais, tempo, valor_hora, pct_risco / 100, pct_fixos / 100,
                          pct_lucro / 100, pct_taxa / 100, taxa_fixa)

    st.divider()
    st.subheader("💡 O que está embutido no Preço Recomendado:")
    m = st.columns(5)
    m[0].metric("📦 Materiais (+Perdas)", brl(calc["materiais_risco"]))
    m[1].metric("🙋‍♀️ Seu Tempo", brl(calc["mao_obra"]))
    m[2].metric("💡 Luz & Manutenção", brl(calc["fixos"]))
    m[3].metric("💳 Taxas da Venda", brl(calc["taxas"]))
    m[4].metric("🏢 Lucro da Loja", brl(calc["lucro_real"]))

    st.markdown(f"### 🏷️ **Preço Sugerido para {nome_produto or 'o Produto'}: {brl(calc['preco'])}**")
    st.info(
        f"**Divisão de cada centavo cobrado no valor de {brl(calc['preco'])}:**\n"
        f"- **{brl(calc['materiais_risco'])}** para repor os materiais e cobrir perdas/testes.\n"
        f"- **{brl(calc['mao_obra'])}** vai direto para o seu **salário**.\n"
        f"- **{brl(calc['fixos'])}** para luz, internet e manutenção dos equipamentos.\n"
        f"- **{brl(calc['taxas'])}** para a taxa do marketplace/cartão.\n"
        f"- **{brl(calc['lucro_real'])}** de lucro limpo para a empresa crescer."
    )

    if st.button("💾 Guardar Ficha Técnica"):
        if nome_produto and composicao:
            res = executar(db.table("fichas_tecnicas").insert({
                "user_id": uid,
                "nome_produto": nome_produto,
                "tempo_minutos": int(tempo),
                "custo_materiais": custo_materiais,
                "preco_sugerido": calc["preco"],
                "taxa_marketplace_pct": pct_taxa,
                "taxa_marketplace_fixa": taxa_fixa,
                "margem_lucro_pct": pct_lucro,
                "custos_fixos_pct": pct_fixos,
                "risco_pct": pct_risco,
                "materiais": composicao,
                "categoria": cat,
            }))
            if res is not None:
                flash(f"Ficha do produto '{nome_produto}' guardada com sucesso!")
                st.rerun()
        else:
            st.warning("Preencha o nome do produto e selecione pelo menos um material.")


# =============================================================================
# ABA 3: FICHAS TÉCNICAS
# =============================================================================
def aba_fichas(db, uid, cfg):
    st.header("📋 Fichas Técnicas Guardadas")
    st.write("Crie e consulte as fichas técnicas das suas peças.")

    fichas = carregar(db, "fichas_tecnicas", uid, "nome_produto")
    insumos = carregar(db, "insumos", uid)
    ins_map = {i["id"]: i for i in insumos}
    valor_hora = valor_hora_de(cfg)

    if not fichas:
        st.info("Nenhuma ficha técnica guardada. Crie uma na Calculadora de Preços!")
        return

    if st.button("🔄 Recalcular TODAS as fichas com os preços atuais dos insumos"):
        erros = 0
        for f in fichas:
            custo_mat, comp, calc = recalcular_ficha(f, ins_map, valor_hora)
            p = parametros_ficha(f)
            res = executar(db.table("fichas_tecnicas").update({
                "custo_materiais": custo_mat, "preco_sugerido": calc["preco"],
                "materiais": comp,
                "custos_fixos_pct": p["custos_fixos"] * 100, "risco_pct": p["risco"] * 100,
            }).eq("id", f["id"]).eq("user_id", uid))
            erros += res is None
        if not erros:
            flash("Todas as fichas foram recalculadas!")
            st.rerun()

    for f in fichas:
        fid = f["id"]
        nome = f.get("nome_produto", "Produto sem nome")
        custo_mat, comp, calc = recalcular_ficha(f, ins_map, valor_hora)
        preco_guardado = to_f(f.get("preco_sugerido"))

        with st.expander(f"📦 {nome}"):
            a, b, c = st.columns(3)
            a.metric("Tempo de produção", f"{int(tempo_ficha(f))} min")
            b.metric("Preço guardado", brl(preco_guardado))
            dif = calc["preco"] - preco_guardado
            c.metric("Preço com custos atuais", brl(calc["preco"]),
                     delta=brl(dif) if abs(dif) > 0.004 else None)

            if comp:
                st.write("**Composição de Materiais (valores atuais):**")
                tabela(pd.DataFrame([{
                    "Material": x["nome"], "Qtd": x["qtd"],
                    "Custo Unit. Atual": brl(x["custo_unitario"]), "Custo Total": brl(x["custo_total"]),
                } for x in comp]))
                st.markdown(f"**Custo total dos materiais:** {brl(custo_mat)}")

            st.divider()
            st.markdown("**✏️ Editar ficha e recalcular:**")
            p = parametros_ficha(f)
            with st.form(f"form_ficha_{fid}"):
                cat_atual = f.get("categoria") or list(CATEGORIAS.keys())[-1]
                opcoes_cat = list(CATEGORIAS.keys())
                if cat_atual not in opcoes_cat:
                    opcoes_cat = [cat_atual] + opcoes_cat
                n_cat = st.selectbox("Categoria", opcoes_cat, index=opcoes_cat.index(cat_atual))
                f1, f2, f3 = st.columns(3)
                n_tempo = f1.number_input("Tempo (min)", min_value=0, value=int(tempo_ficha(f)), step=5)
                n_lucro = f2.number_input("Lucro (%)", min_value=0.0, max_value=200.0,
                                          value=p["lucro"] * 100, step=5.0)
                n_fixos = f3.number_input("Custos fixos (%)", min_value=0.0, max_value=30.0,
                                          value=p["custos_fixos"] * 100, step=1.0)
                f4, f5, f6 = st.columns(3)
                n_risco = f4.number_input("Perdas (%)", min_value=0.0, max_value=50.0,
                                          value=p["risco"] * 100, step=1.0)
                n_taxa = f5.number_input("Taxa canal (%)", min_value=0.0, max_value=50.0,
                                         value=p["taxa"] * 100, step=1.0)
                n_taxa_fixa = f6.number_input("Taxa fixa (R$)", min_value=0.0,
                                              value=p["taxa_fixa"], step=0.5)
                novas_qtds = []
                for idx, x in enumerate(comp):
                    novas_qtds.append(st.number_input(
                        f"Qtd de {x['nome']}", min_value=0.001, value=float(x["qtd"]),
                        step=0.5, key=f"fq_{fid}_{idx}"))
                salvar = st.form_submit_button("💾 Salvar e recalcular")

            if salvar:
                novos = {"risco": n_risco / 100, "custos_fixos": n_fixos / 100, "lucro": n_lucro / 100,
                         "taxa": n_taxa / 100, "taxa_fixa": n_taxa_fixa}
                cm, comp_novo, calc_novo = recalcular_ficha(f, ins_map, valor_hora, novas_qtds, novos, n_tempo)
                res = executar(db.table("fichas_tecnicas").update({
                    "categoria": n_cat, "tempo_minutos": int(n_tempo),
                    "margem_lucro_pct": n_lucro, "custos_fixos_pct": n_fixos, "risco_pct": n_risco,
                    "taxa_marketplace_pct": n_taxa, "taxa_marketplace_fixa": n_taxa_fixa,
                    "custo_materiais": cm, "preco_sugerido": calc_novo["preco"], "materiais": comp_novo,
                }).eq("id", fid).eq("user_id", uid))
                if res is not None:
                    flash(f"Ficha '{nome}' atualizada!")
                    st.rerun()

            def _excluir(fid=fid):
                if executar(db.table("fichas_tecnicas").delete().eq("id", fid).eq("user_id", uid)) is not None:
                    flash("Ficha eliminada.", "🗑️")
                    st.rerun()

            botao_excluir("🗑️ Eliminar Ficha", f"ficha_{fid}", _excluir)


# =============================================================================
# ABA 4: CATÁLOGO (PF vs PJ)
# =============================================================================
def aba_catalogo(db, uid, cfg):
    st.header("📖 Catálogo Digital de Produtos")
    st.caption("Visão comparativa de preços para Varejo (PF) e Atacado/Corporativo (PJ).")

    fichas = carregar(db, "fichas_tecnicas", uid, "nome_produto")
    valor_hora = valor_hora_de(cfg) or 12.50
    taxa_cartao = cfg["taxa_cartao_pct"]

    if not fichas:
        st.info("💡 Nenhum produto no catálogo ainda. Cadastre suas Fichas Técnicas na Calculadora!")
        return

    st.subheader("🔍 Filtrar Produtos")
    c1, c2 = st.columns([2, 1])
    busca = c1.text_input("Buscar produto por nome...", placeholder="Ex: Caderno, Caneca, Quadro...")
    categorias = sorted({f.get("categoria") for f in fichas if f.get("categoria")})
    cat_filtro = c2.selectbox("Filtrar por Categoria:", options=["Todas"] + categorias)

    filtradas = fichas
    if busca:
        filtradas = [f for f in filtradas if busca.lower() in f.get("nome_produto", "").lower()]
    if cat_filtro != "Todas":
        filtradas = [f for f in filtradas if f.get("categoria") == cat_filtro]

    st.caption(f"Exibindo **{len(filtradas)}** de **{len(fichas)}** produtos cadastrados.")
    st.divider()

    itens = []
    for f in filtradas:
        nome = f.get("nome_produto", "Produto sem nome")
        categoria = f.get("categoria", "Geral")
        preco_pf = to_f(f.get("preco_sugerido"))
        taxa_pct = to_f(f.get("taxa_marketplace_pct"))
        taxa_fixa = to_f(f.get("taxa_marketplace_fixa"))
        tempo = tempo_ficha(f, 15.0)
        base, faixas = tabela_atacado(f, valor_hora)
        itens.append({"nome": nome, "categoria": categoria, "varejo": preco_pf,
                      "base": base, "faixas": faixas})

        with st.expander(f"📦 **{nome}** | 🏷️ *{categoria}* — Varejo MP: {brl(preco_pf)}", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### 🛍️ Varejo (PF / B2C)")
                st.caption("Preço final com taxas de marketplace/cartão embutidas (1 a 29 un).")
                st.metric("Preço Unitário Varejo", brl(preco_pf))
                st.write(f"⏱️ **Tempo de Produção:** {int(tempo)} min")
                st.write(f"💳 **Taxas Embutidas:** {fmt_num(taxa_pct, 0)}% + {brl(taxa_fixa)}")
            with col2:
                st.markdown("### 🏢 Atacado / Corporativo (PJ / B2B)")
                st.caption("Preços diretos via PIX / Boleto com desconto progressivo.")
                st.metric("Preço Base Atacado (1 a 29 un - PIX)", brl(base))
                st.markdown("**📊 Tabela de Preços Atacado (PIX / Boleto):**")
                linhas = [f"| **{l['faixa']}** | {fmt_num(l['economia'], 1)}% | {brl(l['preco_peca'])} | {brl(l['total_lote'])} |"
                          for l in faixas]
                st.markdown("| Quantidade Mínima | Economia | Preço/Peça (PIX) | Total Lote (PIX) |\n"
                            "| :--- | :--- | :--- | :--- |\n" + "\n".join(linhas))
                st.caption(f"💳 *Pagamentos via cartão possuem acréscimo de {fmt_num(taxa_cartao, 1)}% sobre o valor total do pedido.*")

            mats = lista_materiais(f)
            if mats:
                st.divider()
                st.markdown("**📋 Materiais Utilizados na Peça:**")
                cols = st.columns(3)
                for idx, mat in enumerate(mats):
                    cols[idx % 3].caption(f"• **{mat.get('nome', 'Insumo')}**: {fmt_num(mat.get('qtd', 1), 2)} un/medida")

    # --- Exportação ---
    st.divider()
    st.subheader("📤 Exportar Catálogo")
    df_exp = pd.DataFrame([{
        "Produto": i["nome"], "Categoria": i["categoria"], "Varejo": i["varejo"],
        "Atacado PIX (1 a 29 un)": i["base"],
        **{f"{l['faixa']} (preço/peça)": l["preco_peca"] for l in i["faixas"]},
    } for i in itens])
    botoes_exportar(df_exp, "catalogo")
    try:
        st.download_button("📄 Baixar Catálogo em PDF", gerar_pdf_catalogo(itens, taxa_cartao),
                           file_name="catalogo_criac_craft.pdf", mime="application/pdf",
                           key="pdf_catalogo")
    except ImportError:
        st.caption("Instale `fpdf2` para gerar o PDF do catálogo.")


# =============================================================================
# ABA 5: FLUXO DE CAIXA
# =============================================================================
def natureza(tipo):
    t = normalizar(tipo)
    if t.startswith("ent"):
        return "Entrada"
    if t.startswith("sa"):
        return "Saída"
    return "Outro"


def aba_caixa(db, uid, cfg):
    st.header("💰 Fluxo de Caixa & Divisão de Lucro")
    st.write("Acompanhe suas entradas, saídas e lucro mensal.")

    pct_reserva = cfg["reserva_giro_pct"] / 100.0
    movs = carregar(db, "fluxo_caixa", uid)

    # --- Novo lançamento ---
    with st.expander("➕ Registar Nova Entrada / Saída", expanded=not movs):
        tipo_mov = st.selectbox("Tipo de Movimentação", ["Venda (Entrada)", "Despesa / Compra (Saída)"])
        eh_venda = "Venda" in tipo_mov
        with st.form("form_novo_lanc", clear_on_submit=True):
            a, b = st.columns(2)
            descricao = a.text_input("Descrição (ex: Venda Caneca Arte, Compra de Resina)")
            data_l = b.date_input("Data", value=datetime.date.today(), format="DD/MM/YYYY")
            c, d = st.columns(2)
            valor = c.number_input("Valor Total (R$)", min_value=0.01, step=1.0, format="%.2f")
            custo_mat = 0.0
            if eh_venda:
                custo_mat = d.number_input("Custo de Material/Insumos (R$)", min_value=0.0, step=1.0,
                                           format="%.2f", help="Valor gasto em insumos para produzir esta peça.")
            enviar = st.form_submit_button("💾 Registar no Caixa")
        if enviar:
            if descricao and valor > 0:
                res = executar(db.table("fluxo_caixa").insert({
                    "user_id": uid, "data": str(data_l),
                    "tipo": "Entrada" if eh_venda else "Saída",
                    "categoria": tipo_mov, "descricao": descricao,
                    "valor": float(valor), "custo_material": float(custo_mat) if eh_venda else 0.0,
                }))
                if res is not None:
                    flash("Lançamento registado com sucesso!")
                    st.rerun()
            else:
                st.warning("Preencha a descrição e um valor válido.")

    st.divider()
    if not movs:
        st.info("Nenhuma movimentação financeira registrada ainda.")
        return

    # --- Preparação dos dados ---
    df = pd.DataFrame(movs)
    if "data" not in df.columns:
        df["data"] = None
    if "custo_material" not in df.columns:
        df["custo_material"] = 0.0
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df["custo_material"] = pd.to_numeric(df["custo_material"], errors="coerce").fillna(0.0)
    df["natureza"] = df["tipo"].apply(natureza)
    df["data_dt"] = pd.to_datetime(df["data"], errors="coerce")
    df["mes"] = df["data_dt"].dt.strftime("%Y-%m").fillna("sem data")

    # --- Filtro de período ---
    meses = sorted(df["mes"].unique(), reverse=True)
    periodo = st.selectbox("📅 Período", ["Todo o período"] + meses)
    dfp = df if periodo == "Todo o período" else df[df["mes"] == periodo]

    # --- Resumo ---
    entradas = dfp[dfp["natureza"] == "Entrada"]
    saidas = dfp[dfp["natureza"] == "Saída"]
    faturamento = float(entradas["valor"].sum())
    total_saidas = float(saidas["valor"].sum())
    custo_insumos = float(entradas["custo_material"].sum())
    caixa_insumos_restante = max(0.0, custo_insumos - total_saidas)
    reserva = faturamento * pct_reserva
    excedente = max(0.0, total_saidas - custo_insumos)
    lucro_limpo = faturamento - custo_insumos - reserva - excedente

    st.subheader("📊 Resumo Financeiro e Divisão do Dinheiro")
    m = st.columns(4)
    m[0].metric("💵 Faturamento Total", brl(faturamento))
    m[1].metric("📦 Deixar no Caixa (Insumos)", brl(caixa_insumos_restante),
                help="Dinheiro que ainda precisa ser reservado/comprado em insumos")
    m[2].metric(f"🏛️ Reserva / Giro ({fmt_num(cfg['reserva_giro_pct'], 0)}%)", brl(reserva))
    m[3].metric("🟢 Lucro Limpo (Seu Ganho)", brl(lucro_limpo))

    # --- Gráfico mensal (sempre sobre o histórico todo) ---
    st.subheader("📈 Entradas x Saídas por mês")
    base = df[df["natureza"].isin(["Entrada", "Saída"]) & (df["mes"] != "sem data")]
    if not base.empty:
        piv = base.groupby(["mes", "natureza"])["valor"].sum().unstack(fill_value=0.0)
        for col in ("Entrada", "Saída"):
            if col not in piv.columns:
                piv[col] = 0.0
        piv = piv[["Entrada", "Saída"]].rename(columns={"Entrada": "Entradas", "Saída": "Saídas"}).sort_index()
        st.bar_chart(piv)
    else:
        st.caption("Registre lançamentos com data para ver o gráfico.")

    # --- Histórico ---
    st.divider()
    st.subheader("📜 Histórico de Movimentações")
    dfp = dfp.copy()
    ent = dfp["natureza"] == "Entrada"
    dfp["reserva"] = (dfp["valor"] * pct_reserva).where(ent, 0.0)
    dfp["lucro_limpo"] = (dfp["valor"] - dfp["custo_material"] - dfp["reserva"]).where(ent, 0.0)
    dfp = dfp.sort_values("data_dt", ascending=False)

    df_num = pd.DataFrame({
        "Data": dfp["data_dt"].dt.strftime("%d/%m/%Y").fillna("-"),
        "Descrição": dfp["descricao"], "Tipo": dfp["tipo"],
        "Valor da Venda / Saída": dfp["valor"],
        "Reposição Caixa (Custo Material)": dfp["custo_material"],
        "Reserva Giro": dfp["reserva"], "Lucro Limpo": dfp["lucro_limpo"],
    })
    df_view = df_num.copy()
    for col in df_view.columns[3:]:
        df_view[col] = df_view[col].apply(brl)
    tabela(df_view.reset_index(drop=True))
    botoes_exportar(df_num, f"fluxo_caixa_{periodo.replace(' ', '_')}")

    # --- Editar / Eliminar ---
    with st.expander("✏️ Editar / 🗑️ Eliminar Lançamento"):
        ids_periodo = set(dfp["id"])
        por_id = {mv["id"]: mv for mv in movs if mv["id"] in ids_periodo}
        if not por_id:
            st.caption("Nenhum lançamento neste período.")
            return
        sel = st.selectbox(
            "Selecione o lançamento:", list(por_id.keys()),
            format_func=lambda k: f"{por_id[k].get('data', '')} - {por_id[k].get('descricao', '')} ({brl(por_id[k].get('valor'))})",
        )
        mv = por_id[sel]
        eh_ent = natureza(mv.get("tipo")) == "Entrada"
        dt_atual = pd.to_datetime(mv.get("data"), errors="coerce")
        dt_atual = dt_atual.date() if pd.notna(dt_atual) else datetime.date.today()

        with st.form(f"form_edit_lanc_{sel}"):
            a, b = st.columns(2)
            e_desc = a.text_input("Descrição", value=mv.get("descricao", ""))
            e_data = b.date_input("Data", value=dt_atual, format="DD/MM/YYYY")
            c, d = st.columns(2)
            e_valor = c.number_input("Valor (R$)", min_value=0.01, value=max(0.01, to_f(mv.get("valor"))),
                                     step=1.0, format="%.2f")
            e_custo = 0.0
            if eh_ent:
                e_custo = d.number_input("Custo de material (R$)", min_value=0.0,
                                         value=to_f(mv.get("custo_material")), step=1.0, format="%.2f")
            salvar = st.form_submit_button("💾 Salvar alterações")
        if salvar:
            payload = {"descricao": e_desc, "data": str(e_data), "valor": float(e_valor)}
            if eh_ent:
                payload["custo_material"] = float(e_custo)
            if executar(db.table("fluxo_caixa").update(payload).eq("id", sel).eq("user_id", uid)) is not None:
                flash("Lançamento atualizado!")
                st.rerun()

        def _excluir():
            if executar(db.table("fluxo_caixa").delete().eq("id", sel).eq("user_id", uid)) is not None:
                flash("Lançamento eliminado.", "🗑️")
                st.rerun()

        botao_excluir("🗑️ Eliminar Lançamento Selecionado", f"lanc_{sel}", _excluir)


# =============================================================================
# ABA 6: REVENDA (ESTOQUE + KITS + ORÇAMENTO WHATSAPP)
# =============================================================================
def aba_revenda(db, uid, cfg):
    st.header("🛍️ Gestão, Estoque e Precificação de Revenda")
    st.caption("Cadastre seus itens de revenda, controle o estoque, monte Kits e gere propostas para WhatsApp.")

    tab_cat, tab_kit = st.tabs(["📦 Catálogo & Estoque", "🎁 Montador de Kits & Orçamentos"])
    produtos = carregar(db, "produtos_revenda", uid, "nome_produto")

    # ---------------- TAB 1: CATÁLOGO & ESTOQUE ----------------
    with tab_cat:
        st.subheader("➕ Cadastrar Produto Individual")
        with st.form("form_novo_prod_revenda", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome_p = c1.text_input("Nome do Produto:*", placeholder="Ex: Lápis Fofo")
            cat_p = c2.text_input("Categoria:", placeholder="Ex: Papelaria / Fofa")
            c3, c4 = st.columns(2)
            custo_p = c3.number_input("Preço de Custo Un. (R$):*", min_value=0.0, value=1.50, step=0.10, format="%.2f")
            frete_p = c4.number_input("Frete/Embalagem Un. (R$):", min_value=0.0, value=0.50, step=0.10, format="%.2f")
            c5, c6 = st.columns(2)
            qtd_est = c5.number_input("Estoque Atual (Unidades):", min_value=0, value=10, step=1)
            est_min = c6.number_input("Estoque Mínimo de Alerta:", min_value=0, value=5, step=1)
            cadastrar = st.form_submit_button("💾 Salvar Produto no Catálogo")
        if cadastrar:
            if not nome_p:
                st.error("⚠️ Informe o nome do produto.")
            else:
                res = executar(db.table("produtos_revenda").insert({
                    "user_id": uid, "nome_produto": nome_p, "categoria": cat_p or "Geral",
                    "preco_custo": custo_p, "frete_embalagem": frete_p,
                    "qtd_estoque": qtd_est, "estoque_minimo": est_min,
                }))
                if res is not None:
                    flash(f"Produto {nome_p} salvo no catálogo!", "🎉")
                    st.rerun()

        st.divider()
        st.subheader("📋 Meus Produtos em Estoque")
        if not produtos:
            st.info("💡 Nenhum produto cadastrado ainda.")
        else:
            baixo = [p for p in produtos if int(p.get("qtd_estoque", 0)) <= int(p.get("estoque_minimo", 5))]
            if baixo:
                st.warning(f"⚠️ **Atenção:** {len(baixo)} produto(s) com estoque igual ou abaixo do mínimo!")

            for p in produtos:
                pid = p["id"]
                p_nome = p.get("nome_produto", "Sem Nome")
                p_cat = p.get("categoria", "Geral")
                p_custo = to_f(p.get("preco_custo"))
                p_frete = to_f(p.get("frete_embalagem"))
                p_qtd = int(p.get("qtd_estoque", 0))
                p_min = int(p.get("estoque_minimo", 5))

                if p_qtd == 0:
                    status = "🔴 **SEM ESTOQUE**"
                elif p_qtd <= p_min:
                    status = f"⚠️ **BAIXO ESTOQUE** ({p_qtd} un)"
                else:
                    status = f"🟢 **Em Estoque** ({p_qtd} un)"

                with st.expander(f"📦 **{p_nome}** | *{p_cat}* — {status} | Custo: {brl(p_custo + p_frete)}"):
                    chave_edit = f"edit_mode_{pid}"
                    if not st.session_state.get(chave_edit):
                        i1, i2, i3 = st.columns(3)
                        i1.write(f"• **Preço Custo:** {brl(p_custo)}")
                        i2.write(f"• **Frete/Embalagem:** {brl(p_frete)}")
                        i3.write(f"• **Estoque Mínimo:** {p_min} un")
                        st.divider()
                        b1, b2, _ = st.columns([1, 2, 1])
                        if b1.button("✏️ Editar", key=f"btn_edit_{pid}"):
                            st.session_state[chave_edit] = True
                            st.rerun()

                        def _excluir(pid=pid):
                            if executar(db.table("produtos_revenda").delete().eq("id", pid).eq("user_id", uid)) is not None:
                                flash("Produto excluído.", "🗑️")
                                st.rerun()

                        with b2:
                            botao_excluir("🗑️ Excluir", f"prod_{pid}", _excluir)
                    else:
                        st.markdown("**✏️ Editar Produto e Ajustar Estoque:**")
                        with st.form(f"form_edit_{pid}"):
                            e_nome = st.text_input("Nome:", value=p_nome)
                            e_cat = st.text_input("Categoria:", value=p_cat)
                            ce1, ce2 = st.columns(2)
                            e_custo = ce1.number_input("Custo Compra (R$):", value=p_custo, min_value=0.0, step=0.10, format="%.2f")
                            e_frete = ce2.number_input("Frete/Embalagem (R$):", value=p_frete, min_value=0.0, step=0.10, format="%.2f")
                            ce3, ce4 = st.columns(2)
                            e_qtd = ce3.number_input("Estoque Atual (un):", value=p_qtd, min_value=0, step=1)
                            e_min = ce4.number_input("Estoque Mínimo (un):", value=p_min, min_value=0, step=1)
                            cs, cc = st.columns(2)
                            salvar = cs.form_submit_button("💾 Salvar Alterações")
                            cancelar = cc.form_submit_button("❌ Cancelar")
                        if salvar:
                            res = executar(db.table("produtos_revenda").update({
                                "nome_produto": e_nome, "categoria": e_cat, "preco_custo": e_custo,
                                "frete_embalagem": e_frete, "qtd_estoque": e_qtd, "estoque_minimo": e_min,
                            }).eq("id", pid).eq("user_id", uid))
                            if res is not None:
                                st.session_state[chave_edit] = False
                                flash("Produto e estoque atualizados!", "🎉")
                                st.rerun()
                        if cancelar:
                            st.session_state[chave_edit] = False
                            st.rerun()

    # ---------------- TAB 2: KITS & ORÇAMENTO ----------------
    with tab_kit:
        st.subheader("🎁 Montar Kit & Gerar Proposta Comercial")
        st.caption("Monte combinações de produtos e gere o texto formatado para enviar ao cliente via WhatsApp.")

        if not produtos:
            st.warning("⚠️ Cadastre produtos no catálogo para montar seus kits!")
            return

        prod_map = {p["id"]: p for p in produtos}
        k1, k2 = st.columns(2)

        with k1:
            nome_kit = st.text_input("Nome do Kit / Proposta:*", placeholder="Ex: Kit Presente Fofo Especial")
            nome_cliente = st.text_input("Nome do Cliente (Opcional):", placeholder="Ex: Maria Clara")
            sel_ids = st.multiselect(
                "Selecione os produtos que compõem o kit:", options=list(prod_map.keys()),
                format_func=lambda k: f"{prod_map[k]['nome_produto']} (Estoque: {prod_map[k].get('qtd_estoque', 0)})",
            )
            itens_kit, resumo, custo_itens = [], [], 0.0
            if sel_ids:
                st.markdown("**🔢 Quantidade de cada item no Kit:**")
                for pid in sel_ids:
                    po = prod_map[pid]
                    q = st.number_input(f"Qtd de '{po['nome_produto']}':", min_value=1, value=1, step=1, key=f"qtd_kit_{pid}")
                    itens_kit.append((po, q))
                    custo_itens += (to_f(po.get("preco_custo")) + to_f(po.get("frete_embalagem"))) * q
                    resumo.append(f"• {q}x {po['nome_produto']}")

        with k2:
            st.markdown("**⚙️ Taxas e Condições:**")
            embalagem = st.number_input("Caixa / Embalagem Final do Kit (R$):", min_value=0.0, value=2.00, step=0.50, format="%.2f")
            taxa_pct = st.number_input("Taxa Marketplace / Cartão (%):", min_value=0.0, value=cfg["taxa_cartao_pct"], step=0.5, format="%.1f")
            taxa_fixa = st.number_input("Taxa Fixa no Cartão (R$):", min_value=0.0, value=0.0, step=0.5, format="%.2f")
            margem = st.number_input("Margem de Lucro Desejada (%):", min_value=0.0, value=30.0, step=1.0, format="%.1f")

        st.divider()
        custo_base = custo_itens + embalagem
        div_cartao = 1.0 - (taxa_pct + margem) / 100.0
        div_pix = 1.0 - margem / 100.0

        if not sel_ids:
            st.info("Selecione ao menos um produto para calcular o kit.")
            return
        if div_cartao <= 0 or div_pix <= 0:
            st.error("A soma de taxa + margem não pode chegar a 100%.")
            return

        # Cartão cobre taxa % + fixa + margem; PIX só a margem (sem taxas de cartão).
        preco_cartao = (custo_base + taxa_fixa) / div_cartao
        preco_pix = custo_base / div_pix
        qtd_pecas = sum(q for _, q in itens_kit)

        st.markdown(f"### 📊 Resumo da Proposta: **{nome_kit or 'Kit sem nome'}**")
        m1, m2, m3 = st.columns(3)
        m1.metric("Preço no PIX", brl(preco_pix))
        m2.metric("Preço no Cartão", brl(preco_cartao))
        m3.metric("Total de Peças", f"{qtd_pecas} un")

        # --- Registrar venda (baixa estoque + lança no caixa) ---
        st.divider()
        st.subheader("✅ Registrar venda deste kit")
        v1, v2, v3 = st.columns(3)
        n_kits = v1.number_input("Quantidade de kits vendidos", min_value=1, value=1, step=1, key="n_kits_venda")
        forma = v2.selectbox("Forma de pagamento", ["PIX", "Cartão"], key="forma_venda")
        baixar = v3.checkbox("Dar baixa no estoque", value=True, key="baixa_estoque")
        valor_unit = preco_pix if forma == "PIX" else preco_cartao
        st.caption(f"Total da venda: **{brl(valor_unit * n_kits)}** — custo de material: {brl(custo_base * n_kits)}")

        if st.button("💰 Registrar venda no Caixa", key="btn_reg_venda"):
            faltando = []
            if baixar:
                for po, q in itens_kit:
                    precisa = q * n_kits
                    if int(po.get("qtd_estoque", 0)) < precisa:
                        faltando.append(f"{po['nome_produto']} (precisa {precisa}, tem {po.get('qtd_estoque', 0)})")
            if faltando:
                st.error("Estoque insuficiente: " + "; ".join(faltando))
            else:
                desc = f"{n_kits}x {nome_kit or 'Kit'}" + (f" - {nome_cliente}" if nome_cliente else "")
                res = executar(db.table("fluxo_caixa").insert({
                    "user_id": uid, "data": str(datetime.date.today()), "tipo": "Entrada",
                    "categoria": "Venda (Entrada)", "descricao": f"{desc} ({forma})",
                    "valor": float(valor_unit * n_kits), "custo_material": float(custo_base * n_kits),
                }))
                if res is not None:
                    if baixar:
                        for po, q in itens_kit:
                            novo = int(po.get("qtd_estoque", 0)) - q * n_kits
                            executar(db.table("produtos_revenda").update({"qtd_estoque": novo})
                                     .eq("id", po["id"]).eq("user_id", uid))
                    flash("Venda registrada no caixa" + (" e estoque atualizado!" if baixar else "!"), "💰")
                    st.rerun()

        # --- Texto do WhatsApp (negrito = 1 asterisco) ---
        st.divider()
        st.subheader("📱 Proposta Comercial Pronta para Enviar no WhatsApp")
        saudacao = f"Olá, {nome_cliente}!" if nome_cliente else "Olá!"
        texto = (
            f"{saudacao} Conforme conversamos, segue a proposta especial para o seu pedido:\n\n"
            f"🎁 *{nome_kit or 'Kit Especial'}*\n\n"
            f"📋 *Itens inclusos:*\n" + "\n".join(resumo) + "\n\n"
            f"💰 *Valores e Condições de Pagamento:*\n"
            f"• *Valor no PIX (Desconto Especial):* {brl(preco_pix)}\n"
            f"• *Valor no Cartão (em até 3x):* {brl(preco_cartao)}\n\n"
            f"📦 *Prazo de Produção/Envio:* 2 a 4 dias úteis.\n"
            f"🗓️ *Proposta válida por 5 dias.*\n\n"
            f"Qualquer dúvida estou à disposição para finalizar seu pedido! ✨"
        )
        st.code(texto, language="markdown")
        st.caption("💡 Clique no ícone de cópia no canto superior direito da caixa acima e cole na conversa do cliente!")


# =============================================================================
# APP PRINCIPAL
# =============================================================================
ABAS = {
    "📦 Cadastro de Insumos": aba_insumos,
    "🧮 Calculadora de Preços": aba_calculadora,
    "📋 Fichas Técnicas": aba_fichas,
    "📖 Catálogo (PF vs PJ)": aba_catalogo,
    "💰 Fluxo de Caixa": aba_caixa,
    "🛍️ Revenda": aba_revenda,
    "⚙️ Configurações": aba_configuracoes,
}


def main():
    cookie_manager = stx.CookieManager(key="cookie_mgr")

    if st.session_state.get("user") is None:
        tentar_restaurar(cookie_manager)
        tela_login(cookie_manager)
        st.stop()

    # Garante que a sessão do Supabase ainda é válida (renova o token se preciso)
    db = get_db()
    try:
        sessao = db.auth.get_session()
    except Exception:
        sessao = None
    if sessao is None:
        encerrar_sessao()
        st.rerun()

    # Mantém o cookie sincronizado com o refresh_token atual (ele é rotacionado)
    if st.session_state.get("manter", True) and st.session_state.get("cookie_rt") != sessao.refresh_token:
        cookie_manager.set(
            COOKIE, sessao.refresh_token,
            expires_at=datetime.datetime.now() + datetime.timedelta(days=30),
            key="set_cookie_rt",
        )
        st.session_state["cookie_rt"] = sessao.refresh_token

    user = st.session_state.user
    uid = user.id
    mostrar_flash()

    st.sidebar.title("🎨 Cria.C Craft")
    st.sidebar.caption(f"Conectado como: **{getattr(user, 'email', 'Usuária')}**")
    if st.sidebar.button("🚪 Sair / Logout"):
        encerrar_sessao()
        st.rerun()

    escolha = st.sidebar.radio("Navegação", list(ABAS.keys()))
    cfg = carregar_config(db, uid)
    ABAS[escolha](db, uid, cfg)


main()
