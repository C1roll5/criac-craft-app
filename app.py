import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# --- CONFIGURAÇÃO DA PÁGINA E TEMA ---
st.set_page_config(page_title="Cria.C Craft", page_icon="✂️", layout="wide")

# CSS personalizado com a paleta oficial da logo Cria.C Craft
st.markdown("""

""", unsafe_allow_html=True)

# --- CONEXÃO SUPABASE ---
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"].strip().rstrip("/")
    key = st.secrets["SUPABASE_KEY"].strip()
    return create_client(url, key)

supabase = init_supabase()

# --- SESSÃO ---
if "user" not in st.session_state:
    st.session_state.user = None

# --- TELA DE LOGIN ---
if st.session_state.user is None:
    st.title("🎨 Artesanato Cria.C")
    st.subheader("Arte, paixão e personalização — Sistema de Gestão")
    
    tab_login, tab_cad = st.tabs(["🔑 Entrar", "📝 Criar Conta"])
    
    with tab_login:
        email = st.text_input("E-mail", key="l_email")
        senha = st.text_input("Senha", type="password", key="l_senha")
        if st.button("Acessar Painel"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": senha})
                st.session_state.user = res.user
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao entrar: {e}")
                
    with tab_cad:
        c_email = st.text_input("E-mail para cadastro", key="c_email")
        c_senha = st.text_input("Senha", type="password", key="c_senha")
        if st.button("Cadastrar Nova Conta"):
            try:
                supabase.auth.sign_up({"email": c_email, "password": c_senha})
                st.success("Conta criada! Se necessário, confirme o e-mail ou faça login.")
            except Exception as e:
                st.error(f"Erro ao cadastrar: {e}")
    st.stop()

# --- PAINEL PRINCIPAL ---
user_id = st.session_state.user.id

st.sidebar.title("🎨 Cria.C Craft")
if st.sidebar.button("Sair / Logout"):
    st.session_state.user = None
    st.rerun()

aba = st.sidebar.radio("Navegação", [
    "📦 Cadastro de Insumos", 
    "🧮 Calculadora de Preços", 
    "📋 Fichas Técnicas", 
    "📖 Catálogo (PF vs PJ)",
    "💰 Fluxo de Caixa",
    "🛍️ Revenda"
])

# ---------------------------------------------------------
# ABA 1: CADASTRO DE INSUMOS
# ---------------------------------------------------------
if aba == "📦 Cadastro de Insumos":
    st.header("📦 Cadastro de Insumos e Materiais")
    
    # --- FORMULÁRIO DE CADASTRO ---
    with st.expander("➕ Cadastrar Novo Insumo", expanded=True):
        col_cad1, col_cad2 = st.columns(2)
        nome_insumo = col_cad1.text_input("Nome do Material / Insumo")
        unidades_opt = ["Unidade", "Folha", "ml", "L", "g", "kg", "Metro", "Pacote", "Caixa"]
        unidade_insumo = col_cad2.selectbox("Unidade de Medida", options=unidades_opt)
        
        col_cad3, col_cad4 = st.columns(2)
        preco_embalagem = col_cad3.number_input("Preço Pago (R$)", min_value=0.0, step=0.50, format="%.2f")
        qtd_embalagem = col_cad4.number_input("Quantidade na Embalagem", min_value=0.01, step=1.0, value=1.0)
        
        if st.button("💾 Cadastrar Insumo"):
            if nome_insumo and preco_embalagem > 0 and qtd_embalagem > 0:
                # Usa 'unidade' para bater exatamente com a coluna do Supabase
                supabase.table("insumos").insert({
                    "user_id": user_id,
                    "nome": nome_insumo,
                    "unidade": unidade_insumo,
                    "preco_embalagem": preco_embalagem,
                    "qtd_embalagem": qtd_embalagem
                }).execute()
                st.success(f"Insumo '{nome_insumo}' cadastrado com sucesso!")
                st.rerun()
            else:
                st.warning("Preencha todos os campos corretamente.")

    st.divider()
    st.subheader("⚙️ Alterar ou Eliminar Insumo")
    res = supabase.table("insumos").select("*").eq("user_id", user_id).execute()
    insumos = res.data

    if insumos:
        insumos_dict = {i["nome"]: i for i in insumos}
        insumo_selecionado_nome = st.selectbox(
            "Selecione o insumo para gerenciar:",
            options=list(insumos_dict.keys()),
            key="sb_gerenciar_insumo"
        )
        
        insumo_atual = insumos_dict[insumo_selecionado_nome]
        insumo_id = insumo_atual["id"]

        with st.expander(f"✏ Editar / 🗑️ Eliminar: {insumo_atual['nome']}", expanded=True):
            novo_nome = st.text_input("Nome", value=insumo_atual.get("nome", ""), key=f"nome_{insumo_id}")
            
            # Busca o valor da coluna 'unidade' (ou 'unidade_medida' como fallback)
            unid_salva = insumo_atual.get("unidade") or insumo_atual.get("unidade_medida", "Unidade")
            unid_index = unidades_opt.index(unid_salva) if unid_salva in unidades_opt else 0
            nova_unidade = st.selectbox("Unidade", options=unidades_opt, index=unid_index, key=f"unid_{insumo_id}")
            
            novo_preco = st.number_input("Preço (R$)", value=float(insumo_atual.get("preco_embalagem", 0.0)), min_value=0.0, step=0.50, key=f"preco_{insumo_id}")
            nova_qtd = st.number_input("Qtd", value=float(insumo_atual.get("qtd_embalagem", 1.0)), min_value=0.01, step=1.0, key=f"qtd_{insumo_id}")

            col_alt1, col_alt2 = st.columns(2)
            
            if col_alt1.button("💾 Guardar Alterações", key=f"btn_salvar_{insumo_id}"):
                supabase.table("insumos").update({
                    "nome": novo_nome,
                    "unidade": nova_unidade,
                    "preco_embalagem": novo_preco,
                    "qtd_embalagem": nova_qtd
                }).eq("id", insumo_id).execute()
                st.success("Insumo atualizado com sucesso!")
                st.rerun()

            if col_alt2.button("🗑 Eliminar Insumo", key=f"btn_del_{insumo_id}", type="primary"):
                supabase.table("insumos").delete().eq("id", insumo_id).execute()
                st.success("Insumo eliminado com sucesso!")
                st.rerun()
    else:
        st.info("Nenhum insumo cadastrado para alterar ou eliminar.")
# ---------------------------------------------------------
# ABA 2: CALCULADORA DE PREÇOS (COM CUSTOS FIXOS E CATEGORIAS)
# ---------------------------------------------------------
elif aba == "🧮 Calculadora de Preços":
    st.header("🧮 Calculadora de Preços por Categoria")

    # Dicionário de Categorias de Personalizados com margens ajustadas (Mínimo 30%)
    CATEGORIAS_PERSONALIZADOS = {
        "📖 Papelaria & Encadernação (Cadernos, Agendas, Planners)": {"lucro": 40.0, "risco": 5.0},
        "☕ Sublimação (Canecas, Azulejos, Squeezes)": {"lucro": 35.0, "risco": 8.0},
        "🪵 Gravação a Laser & Corte de Madeira/MDF": {"lucro": 45.0, "risco": 10.0},
        "🖼️️ Quadros & Placas Decorativas": {"lucro": 35.0, "risco": 5.0},
        "✨ Resina & Velas Artesanais": {"lucro": 45.0, "risco": 10.0},
        "🥤 Brindes & Acrílico (Copos, Vinil, Acessórios)": {"lucro": 30.0, "risco": 5.0},
        "🪡 Costura Criativa (Necessaires, Almofadas, Bolsas)": {"lucro": 35.0, "risco": 5.0},
        "🏷️ Impressões & Adesivos (Adesivos, Cartões, Rótulos)": {"lucro": 30.0, "risco": 3.0},
        "⚙️️ Outra Categoria / Personalizado": {"lucro": 30.0, "risco": 5.0}
    }

    # Busca insumos cadastrados
    res_ins = supabase.table("insumos").select("*").eq("user_id", user_id).execute()
    insumos = res_ins.data if res_ins.data else []

    if not insumos:
        st.warning("Cadastre primeiro os seus insumos na Aba 1 para poder precificar!")
    else:
        # --- ETAPA 1: O SEU SALÁRIO E TEMPO (COM PERSISTÊNCIA NO SUPABASE) ---
        # Busca configuração salva do usuário no banco
        res_config = supabase.table("configuracoes_usuario").select("*").eq("user_id", user_id).execute()
        config_dados = res_config.data[0] if res_config.data else {}

        salario_padrao = float(config_dados.get("salario_pretendido", 2000.0))
        horas_padrao = int(config_dados.get("horas_mes", 160))

        st.subheader("1. Seu Salário Pretendido")
        col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
        
        salario_mensal = col_s1.number_input("Quanto quer ganhar por mês? (R$)", min_value=0.0, value=salario_padrao, step=100.0)
        horas_mensais = col_s2.number_input("Horas trabalhadas por mês", min_value=1, value=horas_padrao, help="160h = 40h/semana (8h/dia de seg a sex)")

        valor_hora = salario_mensal / horas_mensais if horas_mensais > 0 else 0.0

        # Botão para Fixar/Guardar as configurações de salário
        with col_s3:
            st.write(" ")
            st.write(" ")
            if st.button("💾 Fixar Salário"):
                payload_config = {
                    "user_id": user_id,
                    "salario_pretendido": salario_mensal,
                    "horas_mes": horas_mensais
                }
                if config_dados.get("id"):
                    supabase.table("configuracoes_usuario").update(payload_config).eq("id", config_dados["id"]).execute()
                else:
                    supabase.table("configuracoes_usuario").insert(payload_config).execute()
                st.success("Salário fixado no perfil!")

        st.caption(f"💡 *O seu tempo vale **R$ {valor_hora:.2f}/hora**.*".replace(".", ","))

        st.divider()

        # --- ETAPA 2: PRODUTO & CATEGORIA ---
        st.subheader("2. Detalhes do Produto")
        col_p1, col_p2 = st.columns([2, 1])
        nome_produto = col_p1.text_input("Nome do Produto", placeholder="Ex: Quadro Mosaico em MDF Laser")
        tempo_minutos = col_p2.number_input("Tempo de Produção (minutos)", min_value=0, value=30, step=5)

        # SELEÇÃO DA CATEGORIA DO PERSONALIZADO
        cat_selecionada = st.selectbox("Selecione a Categoria do Produto:", options=list(CATEGORIAS_PERSONALIZADOS.keys()))
        config_cat = CATEGORIAS_PERSONALIZADOS[cat_selecionada]

        # SELEÇÃO DE MATERIAIS
        dict_insumos = {f"{i['nome']} ({i.get('unidade', 'un')})": i for i in insumos}
        insumos_selecionados = st.multiselect(
            "Selecione os materiais usados:",
            options=list(dict_insumos.keys())
        )

        composicao = []
        custo_materiais_total = 0.0

        if insumos_selecionados:
            st.markdown("**Quantidade gasta de cada material:**")
            for item_nome in insumos_selecionados:
                ins = dict_insumos[item_nome]
                p_emb = float(ins.get("preco_embalagem", 0))
                q_emb = float(ins.get("qtd_embalagem", 1))
                c_u = p_emb / q_emb if q_emb > 0 else 0.0

                col_i1, col_i2, col_i3 = st.columns([3, 2, 2])
                col_i1.write(f"• {ins['nome']}")
                qtd_usada = col_i2.number_input(
                    f"Qtd ({ins.get('unidade', 'un')})", 
                    min_value=0.001, value=1.0, step=0.5, key=f"calc_qtd_{ins['id']}"
                )
                
                custo_item = c_u * qtd_usada
                custo_materiais_total += custo_item
                col_i3.write(f"R$ {custo_item:.2f}".replace(".", ","))

                composicao.append({
                    "insumo_id": ins["id"],
                    "nome": ins["nome"],
                    "qtd": qtd_usada,
                    "custo_unitario": c_u,
                    "custo_total": custo_item
                })

        st.divider()

        # --- ETAPA 3: CUSTOS FIXOS, LUCRO & TAXAS DE VENDA ---
        st.subheader("3. Custos Fixos, Lucro e Taxas")
        
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        
        # Custos Fixos Gerais (Energia, Internet, Manutenção de Máquinas)
        pct_custos_fixos = col_c1.number_input(
            "Custos Fixos / Energia (%)", 
            min_value=0.0, max_value=30.0, value=10.0, step=1.0,
            help="Para cobrir luz, desgaste de máquinas (impressora, laser), internet e manutenção."
        ) / 100.0

        # Lucro da Empresa (Ajustável, mínimo pré-configurado em 30%)
        pct_lucro_loja = col_c2.number_input(
            "Lucro da Empresa (%)", 
            min_value=30.0, max_value=200.0, 
            value=float(config_cat["lucro"]), 
            step=5.0,
            help="Lucro livre para a empresa investir e crescer."
        ) / 100.0

        pct_taxa_venda = col_c3.number_input("Taxa % Canal (Shopee/Cartão)", min_value=0.0, max_value=50.0, value=18.0, step=1.0) / 100.0
        taxa_fixa_venda = col_c4.number_input("Taxa Fixa Venda (R$)", min_value=0.0, value=3.0, step=0.5)

        # --- CÁLCULOS ---
        # 1. Mão de obra (seu tempo)
        custo_tempo = (tempo_minutos / 60.0) * valor_hora
        
        # 2. Materiais + Risco de perda/teste da categoria
        custo_materiais_com_risco = custo_materiais_total * (1 + (config_cat["risco"] / 100.0))
        
        # 3. Custos Fixos (Energia + Manutenção aplicada sobre o custo direto)
        custo_direto = custo_materiais_com_risco + custo_tempo
        valor_custos_fixos = custo_direto * pct_custos_fixos
        custo_total_producao = custo_direto + valor_custos_fixos
        
        # 4. Adiciona o Lucro da Empresa
        valor_com_lucro = custo_total_producao * (1 + pct_lucro_loja)
        
        # 5. Preço final ajustado para cobrir taxas do marketplace
        preco_venda_sugerido = (valor_com_lucro + taxa_fixa_venda) / (1 - pct_taxa_venda) if pct_taxa_venda < 1 else valor_com_lucro
        
        # 6. Repartição das taxas do canal e lucro real
        total_taxas_canal = (preco_venda_sugerido * pct_taxa_venda) + taxa_fixa_venda
        lucro_empresa_real = preco_venda_sugerido - custo_total_producao - total_taxas_canal

        st.divider()

        # --- ETAPA 4: RESUMO DETALHADO DO PREÇO ---
        st.subheader("💡 O que está embutido no Preço Recomendado:")

        col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns(5)
        col_r1.metric("📦 Materiais (+Perdas)", f"R$ {custo_materiais_com_risco:.2f}".replace(".", ","))
        col_r2.metric("🙋‍♀️ Seu Tempo", f"R$ {custo_tempo:.2f}".replace(".", ","))
        col_r3.metric("💡 Luz & Manutenção", f"R$ {valor_custos_fixos:.2f}".replace(".", ","), help="Dinheiro para luz e manutenção de máquinas/ferramentas.")
        col_r4.metric("💳 Taxas da Venda", f"R$ {total_taxas_canal:.2f}".replace(".", ","))
        col_r5.metric("🏢 Lucro da Loja", f"R$ {lucro_empresa_real:.2f}".replace(".", ","))

        st.markdown(f"### 🏷️️ **Preço Sugerido para {nome_produto or 'o Produto'}: R$ {preco_venda_sugerido:.2f}**".replace(".", ","))

        st.info(f"""
        **Divisão de cada centavo cobrado no valor de R$ {preco_venda_sugerido:.2f}:**
        - **R$ {custo_materiais_com_risco:.2f}** para repor os materiais e cobrir eventuais perdas/testes.
        - **R$ {custo_tempo:.2f}** vai direto para o seu **salário**.
        - **R$ {valor_custos_fixos:.2f}** para pagar a conta de luz, internet e manutenção dos seus equipamentos.
        - **R$ {total_taxas_canal:.2f}** para a taxa do marketplace/cartão.
        - **R$ {lucro_empresa_real:.2f}** de lucro limpo guardado no caixa para fazer a sua empresa crescer.
        """.replace(".", ","))

        # --- GUARDAR FICHA TÉCNICA ---
        if st.button("💾 Guardar Ficha Técnica"):
            if nome_produto and composicao:
                supabase.table("fichas_tecnicas").insert({
                    "user_id": user_id,
                    "nome_produto": nome_produto,
                    "tempo_minutos": int(tempo_minutos),
                    "custo_materiais": custo_materiais_total,
                    "preco_sugerido": preco_venda_sugerido,
                    "taxa_marketplace_pct": pct_taxa_venda * 100,
                    "taxa_marketplace_fixa": taxa_fixa_venda,
                    "margem_lucro_pct": pct_lucro_loja * 100,
                    "materiais": composicao,
                    "categoria": cat_selecionada
                }).execute()
                st.success(f"Ficha do produto '{nome_produto}' guardada com sucesso!")
                st.rerun()
            else:
                st.warning("Preencha o nome do produto e selecione pelo menos um material.")
# ---------------------------------------------------------
# ABA 3: FICHAS TÉCNICAS
# ---------------------------------------------------------
elif aba == "📋 Fichas Técnicas":
    st.header("📋 Fichas Técnicas Guardadas")
    
    # Dicionário auxiliar de risco por categoria para o recálculo
    RISCO_CATEGORIAS = {
        "📖 Papelaria & Encadernação (Cadernos, Agendas, Planners)": 5.0,
        "☕ Sublimação (Canecas, Azulejos, Squeezes)": 8.0,
        "🪵 Gravação a Laser & Corte de Madeira/MDF": 10.0,
        "🖼 Quadros & Placas Decorativas": 5.0,
        "✨ Resina & Velas Artesanais": 10.0,
        "🥤 Brindes & Acrílico (Copos, Vinil, Acessórios)": 5.0,
        "🪡 Costura Criativa (Necessaires, Almofadas, Bolsas)": 5.0,
        "🏷️ Impressões & Adesivos (Adesivos, Cartões, Rótulos)": 3.0,
        "⚙ Outra Categoria / Personalizado": 5.0
    }

    # Busca fichas do utilizador
    res_ft = supabase.table("fichas_tecnicas").select("*").eq("user_id", user_id).execute()
    fichas = res_ft.data if res_ft.data else []

    # Busca insumos atuais para recalcular valores em tempo real
    res_ins = supabase.table("insumos").select("*").eq("user_id", user_id).execute()
    insumos_atuais = {i["id"]: i for i in res_ins.data} if res_ins.data else {}

    # Busca configurações do utilizador para valor da hora de trabalho
    res_config = supabase.table("configuracoes_usuario").select("*").eq("user_id", user_id).execute()
    config_dados = res_config.data[0] if res_config.data else {}
    salario_padrao = float(config_dados.get("salario_pretendido", 2000.0))
    horas_padrao = int(config_dados.get("horas_mes", 160))
    valor_hora = salario_padrao / horas_padrao if horas_padrao > 0 else 0.0

    if fichas:
        for f in fichas:
            nome_prod = f.get('nome_produto', 'Produto sem nome')
            ficha_id = f["id"]
            
            with st.expander(f"📦 {nome_prod}"):
                col_a, col_b = st.columns(2)
                
                # Suporte para ambos os nomes de coluna de tempo de produção
                tempo_prod = f.get('tempo_minutos', f.get('tempo_producao', 0))
                preco_sug = float(f.get('preco_sugerido', 0))
                
                col_a.write(f"**Tempo de Produção:** {tempo_prod} min")
                col_b.write(f"**Preço Guardado:** R$ {preco_sug:.2f}".replace(".", ","))
                
                # Parâmetros de precificação salvos na ficha
                pct_lucro_loja = float(f.get("margem_lucro_pct", 30.0)) / 100.0
                pct_taxa_venda = float(f.get("taxa_marketplace_pct", 18.0)) / 100.0
                taxa_fixa_venda = float(f.get("taxa_marketplace_fixa", 3.0))
                cat_prod = f.get("categoria", "⚙ Outra Categoria / Personalizado")
                pct_risco = RISCO_CATEGORIAS.get(cat_prod, 5.0) / 100.0

                custo_recalculado_materiais = 0.0
                composicao_atualizada = []
                
                # Suporte tanto para o campo 'composicao' quanto 'materiais'
                lista_materiais = f.get("composicao") or f.get("materiais") or []
                
                if lista_materiais:
                    st.write("**Composição de Materiais (Valores Atuais):**")
                    comp_lista = []
                    
                    for comp in lista_materiais:
                        i_id = comp.get("insumo_id")
                        qtd = float(comp.get("qtd", 1))
                        
                        # Se o insumo existe na Aba 1, recalcula com o preço atualizado
                        if i_id in insumos_atuais:
                            ins = insumos_atuais[i_id]
                            p_emb = float(ins.get("preco_embalagem", 0))
                            q_emb = float(ins.get("qtd_embalagem", 1))
                            c_u = p_emb / q_emb if q_emb > 0 else 0.0
                            nome_m = ins.get("nome", "Insumo")
                        else:
                            c_u = float(comp.get("custo_unitario", 0))
                            nome_m = comp.get("nome", "Insumo")
                            
                        c_tot = c_u * qtd
                        custo_recalculado_materiais += c_tot
                        
                        # Guarda a composição com custos unitários e totais atualizados
                        comp_atual = dict(comp)
                        comp_atual["custo_unitario"] = c_u
                        comp_atual["custo_total"] = c_tot
                        composicao_atualizada.append(comp_atual)
                        
                        comp_lista.append({
                            "Material": nome_m,
                            "Qtd": f"{qtd:.2f}".replace(".", ","),
                            "Custo Unit. Atual": f"R$ {c_u:.2f}".replace(".", ","),
                            "Custo Total": f"R$ {c_tot:.2f}".replace(".", ",")
                        })
                    
                    st.dataframe(pd.DataFrame(comp_lista), use_container_width=True)
                    st.markdown(f"**Custo Total dos Materiais Atualizado:** R$ {custo_recalculado_materiais:.2f}".replace(".", ","))

                st.divider()
                col_btn1, col_btn2 = st.columns(2)
                
                # BOTÃO DE ATUALIZAR E RECALCULAR O PRODUTO
                if col_btn1.button(f"🔄 Recalcular e Atualizar no Catálogo", key=f"upd_{ficha_id}"):
                    # 1. Recálculo completo usando a mesma fórmula da Aba 2
                    custo_tempo = (float(tempo_prod) / 60.0) * valor_hora
                    custo_materiais_com_risco = custo_recalculado_materiais * (1 + pct_risco)
                    custo_direto = custo_materiais_com_risco + custo_tempo
                    valor_custos_fixos = custo_direto * 0.10  # 10% de Custos Fixos Padrão
                    custo_total_producao = custo_direto + valor_custos_fixos
                    
                    valor_com_lucro = custo_total_producao * (1 + pct_lucro_loja)
                    novo_preco_sugerido = (valor_com_lucro + taxa_fixa_venda) / (1 - pct_taxa_venda) if pct_taxa_venda < 1 else valor_com_lucro

                    # 2. Atualiza na tabela 'fichas_tecnicas'
                    payload_update = {
                        "custo_materiais": custo_recalculado_materiais,
                        "preco_sugerido": novo_preco_sugerido,
                        "composicao": composicao_atualizada,
                        "materiais": composicao_atualizada
                    }
                    supabase.table("fichas_tecnicas").update(payload_update).eq("id", ficha_id).execute()
                    
                    # 3. Sincroniza com a tabela 'catalogo' se existir
                    try:
                        supabase.table("catalogo").update({
                            "preco": novo_preco_sugerido,
                            "custo": custo_total_producao
                        }).eq("ficha_tecnica_id", ficha_id).execute()
                    except Exception:
                        pass
                    
                    st.success(f"Ficha '{nome_prod}' e catálogo atualizados com sucesso!")
                    st.rerun()

                # BOTÃO DE ELIMINAR
                if col_btn2.button(f"🗑️ Eliminar Ficha", key=f"del_{ficha_id}", type="primary"):
                    supabase.table("fichas_tecnicas").delete().eq("id", ficha_id).execute()
                    st.warning("Ficha eliminada!")
                    st.rerun()
    else:
        st.info("Nenhuma ficha técnica guardada. Crie uma na Calculadora de Preços!")
# ---------------------------------------------------------
# ---------------------------------------------------------
# ABA 4: CATÁLOGO DE PRODUTOS (FOCO EM PIX + NOTA DE CARTÃO)
# ---------------------------------------------------------
elif aba == "📖 Catálogo (PF vs PJ)":
    st.header("📖 Catálogo Digital de Produtos")
    st.caption("Visão comparativa de preços para Varejo (PF) e Atacado/Corporativo (PJ).")

    # --- 1. BUSCA DE DADOS ---
    res_fichas = supabase.table("fichas_tecnicas").select("*").eq("user_id", user_id).order("nome_produto").execute()
    fichas = res_fichas.data if res_fichas.data else []

    # Configuração de horas
    res_config = supabase.table("configuracoes_usuario").select("*").eq("user_id", user_id).execute()
    config_dados = res_config.data[0] if res_config.data else {}
    salario_padrao = float(config_dados.get("salario_pretendido", 2000.0))
    horas_padrao = int(config_dados.get("horas_mes", 160))
    valor_hora = salario_padrao / horas_padrao if horas_padrao > 0 else 12.50

    if not fichas:
        st.info("💡 Nenhum produto cadastrado no catálogo ainda. Cadastre suas Fichas Técnicas na Aba 2!")
    else:
        # --- FILTROS ---
        st.subheader("🔍 Filtrar Produtos")
        col_f1, col_f2 = st.columns([2, 1])
        busca_nome = col_f1.text_input("Buscar produto por nome...", placeholder="Ex: Caderno, Caneca, Quadro...")
        categorias_disponiveis = sorted(list(set([f.get("categoria", "Geral") for f in fichas if f.get("categoria")])))
        categoria_filtro = col_f2.selectbox("Filtrar por Categoria:", options=["Todas"] + categorias_disponiveis)

        fichas_filtradas = fichas
        if busca_nome:
            fichas_filtradas = [f for f in fichas_filtradas if busca_nome.lower() in f.get("nome_produto", "").lower()]
        if categoria_filtro != "Todas":
            fichas_filtradas = [f for f in fichas_filtradas if f.get("categoria") == categoria_filtro]

        st.caption(f"Exibindo **{len(fichas_filtradas)}** de **{len(fichas)}** produtos cadastrados.")
        st.divider()

        # --- LISTAGEM DE PRODUTOS ---
        for f in fichas_filtradas:
            nome = f.get("nome_produto", "Produto sem nome")
            tempo_min = float(f.get("tempo_minutos", f.get("tempo_producao", 15)))
            categoria = f.get("categoria", "Geral")
            
            preco_pf = float(f.get("preco_sugerido", 0.0))
            custo_mat = float(f.get("custo_materiais", 0.0))
            taxa_pct = float(f.get("taxa_marketplace_pct", 0.0)) / 100.0
            taxa_fixa = float(f.get("taxa_marketplace_fixa", 0.0))
            margem_lucro_pct = float(f.get("margem_lucro_pct", 30.0)) / 100.0

            # Preço Base Atacado no PIX (Sem Marketplace)
            preco_base_b2b_pix = max(preco_pf * (1 - taxa_pct) - taxa_fixa, custo_mat * 1.2)

            # Proteção de Margem de Lucro
            custo_mao_obra_varejo = (tempo_min / 60.0) * valor_hora
            custo_direto = custo_mat + custo_mao_obra_varejo
            custo_total_unidade = custo_direto * 1.10
            lucro_protegido_rs = custo_total_unidade * margem_lucro_pct

            with st.expander(f"📦 **{nome}** | 🏷️ *{categoria}* — Varejo MP: R$ {preco_pf:.2f}".replace(".", ","), expanded=True):
                col_c1, col_c2 = st.columns(2)

                # VAREJO
                with col_c1:
                    st.markdown("### 🛍️ Varejo (PF / B2C)")
                    st.caption("Preço final com taxas de marketplace/cartão embutidas (1 a 29 un).")
                    st.metric("Preço Unitário Varejo", f"R$ {preco_pf:.2f}".replace(".", ","))
                    st.write(f"⏱️ **Tempo de Produção:** {int(tempo_min)} min")
                    st.write(f"💳 **Taxas Embutidas:** {taxa_pct*100:.0f}% + R$ {taxa_fixa:.2f}".replace(".", ","))

                # ATACADO / CORPORATIVO
                with col_c2:
                    st.markdown("### 🏢 Atacado / Corporativo (PJ / B2B)")
                    st.caption("Preços diretos via PIX / Boleto com desconto progressivo.")
                    
                    st.metric("Preço Base Atacado (1 a 29 un - PIX)", f"R$ {preco_base_b2b_pix:.2f}".replace(".", ","))

                    # TABELA LIMPA
                    st.markdown("**📊 Tabela de Preços Atacado (PIX / Boleto):**")
                    
                    faixas_atacado = [
                        {"rotulo": "30 a 49 un", "min": 30, "fator_tempo": 0.55},
                        {"rotulo": "50 a 99 un", "min": 50, "fator_tempo": 0.40},
                        {"rotulo": "100+ un", "min": 100, "fator_tempo": 0.33}
                    ]

                    linhas_tabela = []
                    for faixa in faixas_atacado:
                        qtd_m = faixa["min"]
                        tempo_lote_min = tempo_min * faixa["fator_tempo"]
                        custo_mo_lote = (tempo_lote_min / 60.0) * valor_hora
                        custo_total_lote_peca = (custo_mat + custo_mo_lote) * 1.10
                        
                        preco_peca_pix = custo_total_lote_peca + lucro_protegido_rs
                        lote_total_pix = preco_peca_pix * qtd_m

                        desc_efetivo = max(0.0, ((preco_base_b2b_pix - preco_peca_pix) / preco_base_b2b_pix) * 100)

                        p_pix_str = f"R$ {preco_peca_pix:.2f}".replace(".", ",")
                        lote_pix_str = f"R$ {lote_total_pix:.2f}".replace(".", ",")
                        
                        linhas_tabela.append(f"| **{faixa['rotulo']}** | {desc_efetivo:.1f}% | {p_pix_str} | {lote_pix_str} |")

                    tbl_atacado = """
| Quantidade Mínima | Economia | Preço/Peça (PIX) | Total Lote (PIX) |
| :--- | :--- | :--- | :--- |
""" + "\n".join(linhas_tabela)

                    st.markdown(tbl_atacado)
                    st.caption("💳 *Pagamentos via cartão de crédito/débito possuem acréscimo de 4,5% sobre o valor total do pedido.*")

                # MATERIAIS
                materiais_lista = f.get("materiais") or f.get("composicao") or []
                if isinstance(materiais_lista, str):
                    import json
                    try:
                        materiais_lista = json.loads(materiais_lista)
                    except Exception:
                        materiais_lista = []

                if materiais_lista:
                    st.divider()
                    st.markdown("**📋 Materiais Utilizados na Peça:**")
                    cols_m = st.columns(3)
                    for idx, mat in enumerate(materiais_lista):
                        col_target = cols_m[idx % 3]
                        if isinstance(mat, dict):
                            nome_m = mat.get("nome", "Insumo")
                            qtd_m = mat.get("qtd", 1)
                            col_target.caption(f"• **{nome_m}**: {qtd_m} un/medida")
                        else:
                            col_target.caption(f"• {mat}")
# ---------------------------------------------------------
# ABA 5: FLUXO DE CAIXA
# ---------------------------------------------------------
elif aba == "💰 Fluxo de Caixa":
    st.header("💰 Fluxo de Caixa & Divisão de Lucro")
    
    # Configuração de Reserva de Emergência / Capital de Giro
    with st.sidebar.expander("⚙️ Configurar Reserva de Giro"):
        pct_reserva = st.slider("Percentual para Reserva / Giro (%)", min_value=0, max_value=30, value=10, step=5) / 100.0
    # Busca lançamentos
    res_caixa = supabase.table("fluxo_caixa").select("*").eq("user_id", user_id).execute()
    movimentacoes = res_caixa.data if res_caixa.data else []

    # --- FORMULÁRIO DE NOVO LANÇAMENTO ---
    with st.expander("➕ Registar Nova Entrada / Saída", expanded=True):
        col_f1, col_f2 = st.columns(2)
        tipo_mov = col_f1.selectbox("Tipo de Movimentação", ["Venda (Entrada)", "Despesa / Compra (Saída)"])
        descricao = col_f2.text_input("Descrição (ex: Venda Caneca Arte, Compra de Resina)")
        
        col_f3, col_f4 = st.columns(2)
        valor_total = col_f3.number_input("Valor Total (R$)", min_value=0.01, step=1.0, format="%.2f")
        
        # Se for venda, permite informar o custo de material para calcular o lucro exato
        custo_materia_prima = 0.0
        if tipo_mov == "Venda (Entrada)":
            custo_materia_prima = col_f4.number_input(
                "Custo de Material/Insumos (R$)", 
                min_value=0.0, 
                step=1.0, 
                format="%.2f",
                help="Valor gasto em insumos para produzir esta peça."
            )

        if st.button("💾 Registar no Caixa"):
            if descricao and valor_total > 0:
                dados_mov = {
                    "user_id": user_id,
                    "tipo": "Entrada" if "Venda" in tipo_mov else "Saida",
                    "descricao": descricao,
                    "valor": valor_total,
                    "custo_material": custo_materia_prima if "Venda" in tipo_mov else 0.0
                }
                supabase.table("fluxo_caixa").insert(dados_mov).execute()
                st.success("Lançamento registado com sucesso!")
                st.rerun()
            else:
                st.warning("Preencha a descrição e um valor válido.")

    st.divider()

    # --- DASHBOARD & CÁLCULOS FINANCEIROS ---
    if movimentacoes:
        df_caixa = pd.DataFrame(movimentacoes)
        
        # Garantir colunas numéricas
        df_caixa["valor"] = df_caixa["valor"].astype(float)
        if "custo_material" not in df_caixa.columns:
            df_caixa["custo_material"] = 0.0
        else:
            df_caixa["custo_material"] = df_caixa["custo_material"].fillna(0.0).astype(float)

        # Totais Gerais
        total_entradas = df_caixa[df_caixa["tipo"] == "Entrada"]["valor"].sum()
        total_saidas = df_caixa[df_caixa["tipo"] == "Saida"]["valor"].sum()
        saldo_caixa = total_entradas - total_saidas

        # Cálculo detalhado das Vendas
        vendas = df_caixa[df_caixa["tipo"] == "Entrada"]
        total_custo_insumos = vendas["custo_material"].sum()
        total_reserva_giro = total_entradas * pct_reserva
        lucro_liquido_total = total_entradas - total_custo_insumos - total_reserva_giro

        st.subheader("📊 Resumo Financeiro e Divisão do Dinheiro")

        # Métrica em 4 Colunas Clara e Visual
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("💵 Faturamento Total", f"R$ {total_entradas:.2f}".replace(".", ","))
        col_m2.metric("📦 Deixar no Caixa (Insumos)", f"R$ {total_custo_insumos:.2f}".replace(".", ","), help="Dinheiro necessário para repor os materiais das peças vendidas.")
        col_m3.metric(f"🏦 Reserva / Giro ({int(pct_reserva*100)}%)", f"R$ {total_reserva_giro:.2f}".replace(".", ","), help="Guardar para emergências, ferramentas e custos fixos.")
        col_m4.metric("🟢 Lucro Limpo (Seu Ganho)", f"R$ {lucro_liquido_total:.2f}".replace(".", ","), help="Valor livre que pode retirar como seu ganho pessoal.")

        st.divider()
        st.subheader("📜 Histórico de Movimentações")

        # Tabela Detalhada com cálculo por linha
        df_exibicao = df_caixa.copy()
        
        # Cálculo do Lucro por venda na tabela
        df_exibicao["Reserva (Giro)"] = df_exibicao.apply(lambda r: r["valor"] * pct_reserva if r["tipo"] == "Entrada" else 0.0, axis=1)
        df_exibicao["Lucro Limpo por Venda"] = df_exibicao.apply(lambda r: (r["valor"] - r["custo_material"] - r["Reserva (Giro)"]) if r["tipo"] == "Entrada" else 0.0, axis=1)

        # Função auxiliar de formatação de moeda em BRL
        fmt_brl = lambda val: f"R$ {val:.2f}".replace(".", ",")

        # Formatação para o usuário
        df_tabela = pd.DataFrame({
            "Descrição": df_exibicao["descricao"],
            "Tipo": df_exibicao["tipo"],
            "Valor da Venda / Saída": df_exibicao["valor"].apply(fmt_brl),
            "Reposição Caixa (Custo Material)": df_exibicao["custo_material"].apply(fmt_brl),
            "Reserva Giro": df_exibicao["Reserva (Giro)"].apply(fmt_brl),
            "Lucro Limpo": df_exibicao["Lucro Limpo por Venda"].apply(fmt_brl)
        })

        st.dataframe(df_tabela, use_container_width=True)

        # Botão para Apagar Registro se necessário
        with st.expander("🗑️ Eliminar Lançamento"):
            mov_dict = {f"{m['id']} - {m['descricao']} (R$ {m['valor']})": m["id"] for m in movimentacoes}
            mov_sel = st.selectbox("Selecione o lançamento:", options=list(mov_dict.keys()))
            if st.button("Eliminar Lançamento Selecionado", type="primary"):
                supabase.table("fluxo_caixa").delete().eq("id", mov_dict[mov_sel]).execute()
                st.success("Lançamento eliminado!")
                st.rerun()

    else:
        st.info("Nenhuma movimentação financeira registrada ainda.")
        
# ---------------------------------------------------------
# ABA REVENDA: CATÁLOGO COM ESTOQUE, MONTAGEM DE KITS E GERADOR DE ORÇAMENTO
# ---------------------------------------------------------
elif aba == "🛍️ Revenda":
    st.header("🛍️ Gestão, Estoque e Precificação de Revenda")
    st.caption("Cadastre seus itens de revenda, controle o estoque, monte Kits e gere propostas para WhatsApp.")

    tab_cat, tab_kit = st.tabs(["📦 Catálogo & Estoque", "🎁 Montador de Kits & Orçamentos"])

    # ---------------------------------------------------------
    # TAB 1: CATÁLOGO DE PRODUTOS INDIVIDUAIS & ESTOQUE
    # ---------------------------------------------------------
    with tab_cat:
        st.subheader("➕ Cadastrar Produto Individual")
        
        with st.form("form_novo_prod_revenda", clear_on_submit=True):
            c_f1, c_f2 = st.columns(2)
            nome_p = c_f1.text_input("Nome do Produto:*", placeholder="Ex: Lápis Fofo")
            cat_p = c_f2.text_input("Categoria:", placeholder="Ex: Papelaria / Fofa")
            
            c_f3, c_f4 = st.columns(2)
            custo_p = c_f3.number_input("Preço de Custo Un. (R$):*", min_value=0.0, value=1.50, step=0.10, format="%.2f")
            frete_p = c_f4.number_input("Frete/Embalagem Un. (R$):", min_value=0.0, value=0.50, step=0.10, format="%.2f")
            
            c_f5, c_f6 = st.columns(2)
            qtd_est = c_f5.number_input("Estoque Atual (Unidades):", min_value=0, value=10, step=1)
            est_min = c_f6.number_input("Estoque Mínimo de Alerta:", min_value=0, value=5, step=1)
            
            btn_cadastrar = st.form_submit_button("💾 Salvar Produto no Catálogo")

        if btn_cadastrar:
            if not nome_p:
                st.error("⚠️ Informe o nome do produto.")
            else:
                dados_prod = {
                    "user_id": user_id,
                    "nome_produto": nome_p,
                    "categoria": cat_p or "Geral",
                    "preco_custo": custo_p,
                    "frete_embalagem": frete_p,
                    "qtd_estoque": qtd_est,
                    "estoque_minimo": est_min
                }
                supabase.table("produtos_revenda").insert(dados_prod).execute()
                st.toast(f"✅ Produto **{nome_p}** salvo no catálogo!", icon="🎉")
                st.rerun()

        st.divider()
        st.subheader("📋 Meus Produtos em Estoque")

        res_prods = supabase.table("produtos_revenda").select("*").eq("user_id", user_id).order("nome_produto").execute()
        lista_prods = res_prods.data if res_prods.data else []

        if not lista_prods:
            st.info("💡 Nenhum produto cadastrado ainda.")
        else:
            # ALERTAS DE ESTOQUE CRÍTICO NO TOPO
            itens_baixo_estoque = [p for p in lista_prods if int(p.get("qtd_estoque", 0)) <= int(p.get("estoque_minimo", 5))]
            if itens_baixo_estoque:
                st.warning(f"⚠️ **Atenção:** Você tem {len(itens_baixo_estoque)} produto(s) com estoque igual ou abaixo do mínimo!")

            for p in lista_prods:
                pid = p["id"]
                p_nome = p.get("nome_produto", "Sem Nome")
                p_cat = p.get("categoria", "Geral")
                p_custo = float(p.get("preco_custo", 0.0))
                p_frete = float(p.get("frete_embalagem", 0.0))
                p_qtd = int(p.get("qtd_estoque", 0))
                p_min = int(p.get("estoque_minimo", 5))
                custo_total_item = p_custo + p_frete

                # Status do estoque em Emoji
                if p_qtd == 0:
                    status_est = "🔴 **SEM ESTOQUE**"
                elif p_qtd <= p_min:
                    status_est = f"⚠️ **BAIXO ESTOQUE** ({p_qtd} un)"
                else:
                    status_est = f"🟢 **Em Estoque** ({p_qtd} un)"

                with st.expander(f"📦 **{p_nome}** | *{p_cat}* — {status_est} | Custo: R$ {custo_total_item:.2f}".replace(".", ",")):
                    
                    st_key_edit = f"edit_mode_{pid}"
                    if st_key_edit not in st.session_state:
                        st.session_state[st_key_edit] = False

                    if not st.session_state[st_key_edit]:
                        col_i1, col_i2, col_i3 = st.columns(3)
                        col_i1.write(f"• **Preço Custo:** R$ {p_custo:.2f}".replace(".", ","))
                        col_i2.write(f"• **Frete/Embalagem:** R$ {p_frete:.2f}".replace(".", ","))
                        col_i3.write(f"• **Estoque Mínimo:** {p_min} un")

                        st.divider()
                        col_b1, col_b2, _ = st.columns([1, 1, 2])
                        
                        if col_b1.button("✏️ Editar", key=f"btn_edit_{pid}"):
                            st.session_state[st_key_edit] = True
                            st.rerun()

                        if col_b2.button("🗑️ Excluir", key=f"btn_del_{pid}", type="secondary"):
                            supabase.table("produtos_revenda").delete().eq("id", pid).eq("user_id", user_id).execute()
                            st.toast(f"🗑️ Produto **{p_nome}** excluído!", icon="✅")
                            st.rerun()
                    else:
                        st.markdown("**✏️ Editar Produto e Ajustar Estoque:**")
                        with st.form(key=f"form_edit_{pid}"):
                            e_nome = st.text_input("Nome:", value=p_nome)
                            e_cat = st.text_input("Categoria:", value=p_cat)
                            
                            ce1, ce2 = st.columns(2)
                            e_custo = ce1.number_input("Custo Compra (R$):", value=p_custo, min_value=0.0, step=0.10, format="%.2f")
                            e_frete = ce2.number_input("Frete/Embalagem (R$):", value=p_frete, min_value=0.0, step=0.10, format="%.2f")
                            
                            ce3, ce4 = st.columns(2)
                            e_qtd = ce3.number_input("Estoque Atual (un):", value=p_qtd, min_value=0, step=1)
                            e_min = ce4.number_input("Estoque Mínimo (un):", value=p_min, min_value=0, step=1)

                            col_save, col_cancel = st.columns(2)
                            btn_salvar_edit = col_save.form_submit_button("💾 Salvar Alterações")
                            btn_cancelar = col_cancel.form_submit_button("❌ Cancelar")

                            if btn_salvar_edit:
                                update_dados = {
                                    "nome_produto": e_nome,
                                    "categoria": e_cat,
                                    "preco_custo": e_custo,
                                    "frete_embalagem": e_frete,
                                    "qtd_estoque": e_qtd,
                                    "estoque_minimo": e_min
                                }
                                supabase.table("produtos_revenda").update(update_dados).eq("id", pid).eq("user_id", user_id).execute()
                                st.session_state[st_key_edit] = False
                                st.toast("✅ Produto e Estoque atualizados!", icon="🎉")
                                st.rerun()

                            if btn_cancelar:
                                st.session_state[st_key_edit] = False
                                st.rerun()

    # ---------------------------------------------------------
    # TAB 2: CALCULADORA DE KITS & GERADOR DE ORÇAMENTO WHATSAPP
    # ---------------------------------------------------------
    with tab_kit:
        st.subheader("🎁 Montar Kit & Gerar Proposta Comercial")
        st.caption("Monte combinações de produtos e gere o texto formatado para enviar direto ao cliente via WhatsApp.")

        res_prods_kit = supabase.table("produtos_revenda").select("*").eq("user_id", user_id).order("nome_produto").execute()
        prods_para_kit = res_prods_kit.data if res_prods_kit.data else []

        if not prods_para_kit:
            st.warning("⚠️ Cadastre produtos no catálogo para montar seus kits!")
        else:
            col_k1, col_k2 = st.columns([1, 1])

            with col_k1:
                nome_kit = st.text_input("Nome do Kit / Proposta:*", placeholder="Ex: Kit Presente Fofo Especial")
                nome_cliente = st.text_input("Nome do Cliente (Opcional):", placeholder="Ex: Maria Clara")
                
                opcoes_produtos = {f"{p['nome_produto']} (Estoque: {p.get('qtd_estoque', 0)})": p for p in prods_para_kit}
                itens_selecionados = st.multiselect("Selecione os produtos que compõem o kit:", options=list(opcoes_produtos.keys()))

                qtds_itens = {}
                resumo_itens_texto = []
                custo_total_materiais_kit = 0.0

                if itens_selecionados:
                    st.markdown("**🔢 Quantidade de cada item no Kit:**")
                    for item_label in itens_selecionados:
                        prod_obj = opcoes_produtos[item_label]
                        qtd = st.number_input(f"Qtd de '{prod_obj['nome_produto']}':", min_value=1, value=1, step=1, key=f"qtd_kit_{prod_obj['id']}")
                        qtds_itens[prod_obj['id']] = qtd
                        
                        custo_unit_item = float(prod_obj.get("preco_custo", 0.0)) + float(prod_obj.get("frete_embalagem", 0.0))
                        custo_total_materiais_kit += custo_unit_item * qtd
                        resumo_itens_texto.append(f"• {qtd}x {prod_obj['nome_produto']}")

            with col_k2:
                st.markdown("**⚙️ Taxas e Condições:**")
                embalagem_extra_kit = st.number_input("Caixa / Embalagem Final do Kit (R$):", min_value=0.0, value=2.00, step=0.50, format="%.2f")
                taxa_mp_pct = st.number_input("Taxa Marketplace / Cartão (%):", min_value=0.0, value=4.5, step=0.5, format="%.1f")
                taxa_mp_fixa = st.number_input("Taxa Fixa (R$):", min_value=0.0, value=0.0, step=0.5, format="%.2f")
                margem_kit_pct = st.number_input("Margem de Lucro Desejada (%):", min_value=0.0, value=30.0, step=1.0, format="%.1f")

            st.divider()

            custo_base_kit = custo_total_materiais_kit + embalagem_extra_kit
            divisor_kit = 1.0 - ((taxa_mp_pct + margem_kit_pct) / 100.0)

            if itens_selecionados and divisor_kit > 0:
                preco_cartao = (custo_base_kit + taxa_mp_fixa) / divisor_kit
                
                # Preço PIX sem a taxa % do cartão/marketplace
                preco_pix = preco_cartao / (1 + (taxa_mp_pct / 100.0)) if taxa_mp_pct > 0 else preco_cartao
                
                qtd_total_pecas = sum(qtds_itens.values())

                st.markdown(f"### 📊 Resumo da Proposta: **{nome_kit or 'Kit sem nome'}**")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Preço no PIX", f"R$ {preco_pix:.2f}".replace(".", ","))
                m2.metric("Preço no Cartão", f"R$ {preco_cartao:.2f}".replace(".", ","))
                m3.metric("Total de Peças", f"{qtd_total_pecas} un")

                st.divider()

                # --- GERADOR DE TEXTO FORMATADO PARA WHATSAPP ---
                st.subheader("📱 Proposta Comercial Pronta para Enviar no WhatsApp")
                
                itens_str = "\n".join(resumo_itens_texto)
                saudacao = f"Olá, {nome_cliente}!" if nome_cliente else "Olá!"
                
                texto_whatsapp = f"""{saudacao} Conforme conversamos, segue a proposta especial para o seu pedido:

🎁 *{nome_kit or 'Kit Especial'}*

📋 *Itens inclusos:*
{itens_str}

💰 *Valores e Condições de Pagamento:*
• **Valor no PIX (Desconto Especial):** R$ {preco_pix:.2f}
• **Valor no Cartão (em até 3x):** R$ {preco_cartao:.2f}

📦 *Prazo de Produção/Envio:* 2 a 4 dias úteis.
🗓️ *Proposta válida por 5 dias.*

Qualquer dúvida estou à disposição para finalizar seu pedido! ✨""".replace(".", ",")

                st.code(texto_whatsapp, language="markdown")
                st.caption("💡 Clique no ícone de cópia no canto superior direito da caixa de código acima e cole direto na conversa do cliente!")
