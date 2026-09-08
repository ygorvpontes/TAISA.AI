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


# --- MOTOR DE COMPLIANCE (CHECK POINTS E FORMATAÇÃO) ---
def aplicar_regras_green_light(df_sto, df_piloto, pricing_issues, refurbished, raw_materials, previous_il, masterdata):
    print("\n⚙️ Executando motor de regras e gerando Check Points...")

    if not df_piloto.empty:
        df_final = pd.merge(df_sto, df_piloto, left_on='CFN_Tratada', right_on='Código Tratado', how='left')
    else:
        df_final = df_sto.copy()

    # Criação das colunas de flag (Yes/No) para manter compatibilidade com o Excel antigo
    df_final['Pricing Issue'] = 'No'
    df_final['Require LI'] = 'No'
    df_final['Is RawMaterial'] = 'No'
    df_final['Is Refurbished'] = 'No'

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

        # 2 a 6. Outras verificações e Flags
        cfn = str(row.get('CFN_Tratada', ''))
        mat = str(row.get('Material_Tratado', ''))
        
        if pricing_issues and (cfn in pricing_issues or mat in pricing_issues): 
            alertas.append("Check Pricing Issue")
            row['Pricing Issue'] = 'Yes'
            
        if refurbished and (cfn in refurbished or mat in refurbished): 
            alertas.append("Check Refurbished")
            row['Is Refurbished'] = 'Yes'
            
        if raw_materials and (cfn in raw_materials or mat in raw_materials): 
            alertas.append("Check Raw Material")
            row['Is RawMaterial'] = 'Yes'
            
        if previous_il and (cfn in previous_il or mat in previous_il): 
            alertas.append("Check Previous IL")
            row['Require LI'] = 'Yes'
            
        if masterdata and (cfn not in masterdata and mat not in masterdata): 
            alertas.append("Check MasterData")

        row['Check Point'] = "; ".join(alertas) if alertas else "Green Light Autorizado"
        return row

    # Aplica a função linha a linha
    df_final = df_final.apply(avaliar_linha, axis=1)
    
    # --- FORMATAÇÃO IDÊNTICA AO EXCEL DO POWER QUERY ---
    
    # Calcular o Unit Price (Power BI só manda o Total e a Qtd)
    df_final['Unit Price'] = (df_final['Delivery Value'] / df_final['Delivery Quantity']).round(2)
    
    # Mapeamento exato das 39 colunas
    de_para_colunas = {
        'Check Point': 'Check Point',
        'Supply Plant': 'Vendor',
        'Receive Plant': 'Planta Destino',
        'PO Number': 'STO',
        'GTS Invoice Number': 'Invoice Number F8',
        'Invoice Date': 'Invoice Date F8',       # Fallback caso não tenha data exclusiva do GTS
        'Invoice Number': 'Invoice Number F2',
        'Invoice Date': 'Invoice Date F2',
        'Delivery Number': 'Delivery Number',
        'Material': 'UPN',
        'CFN': 'CFN Number',
        'Batch / Serial / Lot': 'Batch_F2',
        'Manufacturing Date': 'Manufacturing Date', # Tenta pegar se existir no PBI
        'Shelf-Life': 'Piloto_Geral.Shelf-Life',
        'Descrição do Código': 'Piloto_Geral.Descrição do Código',
        'Material Description': 'Material Number1',
        'Delivery Quantity': 'Qty',
        'PO UOM': 'Sales Unit',
        'Unit Price': 'Unit Price',
        'CFN_Tratada': 'CFN_Tratada_GreenLight',
        'Delivery Value': 'Extended Price',
        'Pricing Issue': 'Pricing Issue',
        'Currency': 'Extended Amount Currency', # Se não existir, preenchemos com BRL depois
        'NCM': 'MasterData_Tratada.NCM',
        'Require LI': 'Require LI',
        'Is RawMaterial': 'Is RawMaterial',
        'Is Refurbished': 'Is Refurbished',
        'Registro ANVISA': 'Piloto_Geral.Registro ANVISA',
        'Data de Aprovação Inicial': 'Piloto_Geral.Data de Aprovação Inicial',
        'Data de Vencimento do Registro ': 'Piloto_Geral.Data de Vencimento do Registro ',
        'Detentor do Registro': 'Piloto_Geral.Detentor do Registro',
        'Status de Comercialização': 'Piloto_Geral.Status de Comercialização',
        'Método de Esterilização': 'Piloto_Geral.Método de Esterilização',
        'FID Legal': 'Piloto_Geral.FID Legal',
        'Fabricante Legal': 'Piloto_Geral.Fabricante Legal',
        'FID Físico (Real)': 'Piloto_Geral.FID Físico (Real)',
        'Fabricante Físico (Real)': 'Piloto_Geral.Fabricante Físico (Real)',
        'País de Origem': 'Piloto_Geral.País de Origem',
        'Planner': 'MasterData_Tratada.Planner'
    }

    # Criar DataFrame final com as colunas na ordem exata
    df_export = pd.DataFrame()
    for col_orig, col_dest in de_para_colunas.items():
        if col_orig in df_final.columns:
            df_export[col_dest] = df_final[col_orig]
        else:
            df_export[col_dest] = None # Cria a coluna vazia se a base fonte não possuir
            
    # Garantir moeda e preencher nulls de campos calculados
    if 'Extended Amount Currency' in df_export.columns:
        df_export['Extended Amount Currency'] = df_export['Extended Amount Currency'].fillna('USD')

    return df_export


# --- EXPORTAÇÃO ---
def exportar_excel_green_light(df_final: pd.DataFrame, invoice_num: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    caminho_arquivo = os.path.join(OUTPUT_DIR, f"{invoice_num}_GL.xlsx")
    
    # Aba Validacao_Preco_F8
    resumo_f8 = df_final.groupby(['Invoice Number F8', 'Delivery Number']).agg(
        Count_Currency=('Extended Amount Currency', 'count'),
        Sum_Qty=('Qty', 'sum'),
        Sum_Amount=('Extended Price', 'sum')
    ).reset_index()

    # Renomear para ficar igual a aba de Preco
    resumo_f8.rename(columns={
        'Count_Currency': 'Count of Extended Amount Currency',
        'Sum_Qty': 'Sum of Total Qty F8',
        'Sum_Amount': 'Sum of Total Invoice Amount F8'
    }, inplace=True)

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
    
    # Exporta para excel o resultado
    exportar_excel_green_light(df_resultado, lista_de_invoices[0])
    
    print("✅ Pipeline executado com sucesso!")
    return df_resultado

if __name__ == "__main__":
    invoices_teste = ["1090748838"]
    resultado = run_green_light_pipeline(invoices_teste)

    if not resultado.empty:
        colunas_exibicao = ['F8_GTS_Invoice', 'CFN', 'Delivery Quantity', 'Check Point']
        colunas_presentes = [c for c in colunas_exibicao if c in resultado.columns]
        print("\n🏆 PREVIEW DO CHAT DA TAISA:")
        print(resultado[colunas_presentes].head(10))