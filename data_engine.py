import os
import glob
import pandas as pd

# --- CONFIGURAÇÕES DE DIRETÓRIO ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FUP_DIR = os.path.join(BASE_DIR, 'FUP')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')


def clean_string_key(series: pd.Series) -> pd.Series:
    """Padroniza chaves alfanuméricas removendo caracteres especiais e espaços."""
    return series.astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().str.strip()

def clean_number_col(series: pd.Series) -> pd.Series:
    """Remove decimais flutuantes do Excel e espaços em colunas numéricas."""
    return series.astype(str).str.split('.').str[0].str.strip()

def get_latest_file_safely(keyword: str, extension: str = ".xlsx"):
    """Busca o arquivo mais recente pela keyword. Retorna None se não encontrar."""
    search_pattern = os.path.join(FUP_DIR, f"*{keyword}*{extension}")
    files = glob.glob(search_pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


# --- CARREGADORES DE BASES ---
def build_piloto_geral() -> pd.DataFrame:
    print("\n📋 Carregando bases regulatórias (Piloto AS + Piloto MDT)...")
    file_as = get_latest_file_safely("Piloto_AS")
    file_mdt = get_latest_file_safely("Piloto_MDT")

    dfs = []
    if file_as:
        dfs.append(pd.read_excel(file_as))
        print(f"  ✅ Piloto AS carregada.")
    else:
        print("  ⚠️ Piloto_AS não encontrada em FUP.")

    if file_mdt:
        dfs.append(pd.read_excel(file_mdt))
        print(f"  ✅ Piloto MDT carregada.")
    else:
        print("  ⚠️ Piloto_MDT não encontrada em FUP.")

    if not dfs:
        print("  ⚠️ Nenhuma base Piloto encontrada. O Check Point usará dados limitados.")
        return pd.DataFrame()

    df_piloto = pd.concat(dfs, ignore_index=True)
    if 'Código Tratado' in df_piloto.columns:
        df_piloto['Código Tratado'] = clean_string_key(df_piloto['Código Tratado'])
    return df_piloto

def load_auxiliary_keys(keyword: str, possible_col_names: list) -> set:
    filepath = get_latest_file_safely(keyword)
    if not filepath:
        print(f"  ⚠️ Auxiliar '{keyword}' não encontrada. Checagem ignorada.")
        return set()
    
    df = pd.read_excel(filepath)
    for col in possible_col_names:
        if col in df.columns:
            print(f"  ✅ Auxiliar '{keyword}' carregada.")
            return set(clean_string_key(df[col]).dropna().unique())
    return set()


# --- PROCESSAMENTO DO NOVO ARQUIVO DE STO (POWER BI) ---
def process_sto_powerbi(invoices_alvo: list) -> pd.DataFrame:
    print(f"\n⚙️ Processando base STO Power BI para as invoices: {invoices_alvo}...")
    
    file_sto = get_latest_file_safely("STO_PowerBI")
    if not file_sto:
        file_sto = get_latest_file_safely("Data Explorer") # Tenta o nome alternativo
    
    if not file_sto:
        raise FileNotFoundError("❌ Arquivo de extração STO do Power BI não encontrado na pasta FUP.")

    df = pd.read_excel(file_sto, sheet_name="Export")

    # F8 = GTS Invoice Number | F2 = Invoice Number
    df['F8_GTS_Invoice'] = clean_number_col(df['GTS Invoice Number'])
    df['F2_Invoice'] = clean_number_col(df['Invoice Number'])

    invoices_alvo_str = [str(inv).strip() for inv in invoices_alvo]

    # Busca tanto na fatura GTS (F8) quanto na fatura fiscal física (F2)
    filtro = df['F8_GTS_Invoice'].isin(invoices_alvo_str) | df['F2_Invoice'].isin(invoices_alvo_str)
    df_filtrado = df[filtro].copy()

    if df_filtrado.empty:
        print("❌ Nenhuma linha localizada para as invoices informadas.")
        return pd.DataFrame()

    # Higienização de chaves para cruzamento
    df_filtrado['CFN_Tratada'] = clean_string_key(df_filtrado['CFN'])
    df_filtrado['Material_Tratado'] = clean_string_key(df_filtrado['Material'])
    df_filtrado['Delivery_Clean'] = clean_number_col(df_filtrado['Delivery Number'])

    return df_filtrado


# --- MOTOR DE COMPLIANCE (CHECK POINTS) ---
def aplicar_regras_green_light(df_sto, df_piloto, pricing_issues, refurbished, raw_materials, previous_il, masterdata):
    print("\n⚙️ Executando motor de regras e gerando Check Points...")

    if not df_piloto.empty:
        df_final = pd.merge(df_sto, df_piloto, left_on='CFN_Tratada', right_on='Código Tratado', how='left')
    else:
        df_final = df_sto.copy()

    def avaliar_linha(row):
        alertas = []

        # 1. ANVISA (Piloto)
        if not df_piloto.empty:
            if pd.isna(row.get('Código Tratado')):
                alertas.append("Check Código na Tabela Piloto")
            else:
                status = str(row.get('Status de Comercialização', ''))
                if not status.lower().startswith('lib'):
                    alertas.append("Check status de comercialização")

                detentor = str(row.get('Detentor do Registro', ''))
                if 'suture' not in detentor.lower() and not detentor.lower().startswith('medtronic'):
                    alertas.append("Check Detentor do Registro")

        # 2 a 6. Outras verificações
        cfn = str(row.get('CFN_Tratada', ''))
        mat = str(row.get('Material_Tratado', ''))
        
        if pricing_issues and (cfn in pricing_issues or mat in pricing_issues): alertas.append("Check Pricing Issue")
        if refurbished and (cfn in refurbished or mat in refurbished): alertas.append("Check Refurbished")
        if raw_materials and (cfn in raw_materials or mat in raw_materials): alertas.append("Check Raw Material")
        if previous_il and (cfn in previous_il or mat in previous_il): alertas.append("Check Previous IL")
        if masterdata and (cfn not in masterdata and mat not in masterdata): alertas.append("Check MasterData")

        return "; ".join(alertas) if alertas else "Green Light Autorizado"

    df_final['Check Point'] = df_final.apply(avaliar_linha, axis=1)
    return df_final


# --- EXPORTAÇÃO ---
def exportar_excel_green_light(df_final: pd.DataFrame, invoice_num: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    caminho_arquivo = os.path.join(OUTPUT_DIR, f"{invoice_num}_GL.xlsx")

    # Resumo F8 (Validacao_Preco_F8)
    if 'Extended Amount Currency' not in df_final.columns:
        df_final['Extended Amount Currency'] = 'USD' # fallback
        
    resumo_f8 = df_final.groupby(['F8_GTS_Invoice', 'Delivery_Clean']).agg(
        Count_Currency=('Extended Amount Currency', 'count'),
        Sum_Qty=('Delivery Quantity', 'sum'),
        Sum_Amount=('Delivery Value', 'sum')
    ).reset_index()

    with pd.ExcelWriter(caminho_arquivo, engine='openpyxl') as writer:
        df_final.to_excel(writer, sheet_name='Green_Light', index=False)
        resumo_f8.to_excel(writer, sheet_name='Validacao_Preco_F8', index=False)

    print(f"\n📄 ARQUIVO OFICIAL GERADO: {caminho_arquivo}")


# --- ORQUESTRADOR ---
def run_green_light_pipeline(lista_de_invoices: list):
    piloto = build_piloto_geral()
    pricing_issues = load_auxiliary_keys("Pricing", ['CFN', 'Material'])
    refurbished = load_auxiliary_keys("Refurbished", ['CFN', 'Material'])
    raw_materials = load_auxiliary_keys("Raw_Material", ['CFN', 'Material'])
    previous_il = load_auxiliary_keys("Previous_IL", ['CFN', 'Material'])
    masterdata = load_auxiliary_keys("MasterData", ['CFN', 'Material'])

    df_sto = process_sto_powerbi(lista_de_invoices)
    if df_sto.empty: return pd.DataFrame()

    df_resultado = aplicar_regras_green_light(df_sto, piloto, pricing_issues, refurbished, raw_materials, previous_il, masterdata)
    
    # Exporta para excel o resultado da primeira invoice da lista
    exportar_excel_green_light(df_resultado, lista_de_invoices[0])
    
    print("✅ Pipeline executado com sucesso!")
    return df_resultado

if __name__ == "__main__":
    # Teste com a fatura que sabemos que está no arquivo Data Explorer!
    invoices_teste = ["1090748838"]
    resultado = run_green_light_pipeline(invoices_teste)

    if not resultado.empty:
        colunas_exibicao = ['F8_GTS_Invoice', 'CFN', 'Delivery Quantity', 'Check Point']
        colunas_presentes = [c for c in colunas_exibicao if c in resultado.columns]
        print("\n🏆 PREVIEW DO CHAT DA TAISA:")
        print(resultado[colunas_presentes].head(10))