import pandas as pd
import glob
import os

# --- 1. CONFIGURAÇÕES GERAIS (BLINDADAS PARA CODESPACES/LINUX) ---
# Pega o caminho absoluto da pasta onde o data_engine.py está salvo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Junta com a pasta FUP
FUP_DIR = os.path.join(BASE_DIR, 'FUP') 

def get_latest_file(keyword, extension=".xlsx"):
    """Varre a pasta FUP e retorna o caminho do arquivo mais recente contendo a keyword."""
    # Monta o padrão (Ex: /workspaces/projeto/FUP/*Piloto_AS*.xlsx)
    search_pattern = os.path.join(FUP_DIR, f"*{keyword}*{extension}")
    
    print(f"🔎 Buscando na pasta: {search_pattern}") 
    
    files = glob.glob(search_pattern)
    if not files:
        raise FileNotFoundError(f"❌ Nenhum arquivo encontrado para a keyword: '{keyword}' em {FUP_DIR}")
    
    # Retorna o arquivo com a maior data de modificação
    latest_file = max(files, key=os.path.getmtime)
    print(f"✅ Arquivo encontrado: {os.path.basename(latest_file)}")
    return latest_file

# --- 2. FÁBRICA DE PILOTOS ---
def build_piloto_geral():
    """Equivale à união da Piloto_AS e Piloto_MDT."""
    print("Construindo Piloto Geral...")
    df_as = pd.read_excel(get_latest_file("Piloto_AS"))
    df_mdt = pd.read_excel(get_latest_file("Piloto_MDT"))
    return pd.concat([df_as, df_mdt], ignore_index=True)

# --- 3. PROCESSAMENTO DA F8 (INVOICE FINANCEIRA) ---
def process_bill2_f8(invoices_alvo: list):
    """Trata a F8 e filtra SOMENTE as invoices solicitadas pelo usuário/TAISA."""
    print(f"⚙️ Processando F8 e filtrando as Invoices: {invoices_alvo}...")
    
    file_bil2 = get_latest_file("ZKP_MP06_Q5001_Bil2")
    df = pd.read_excel(file_bil2, sheet_name="1. ZKP_MP06_Q5001_Bil2")
    
    # --- BLINDAGEM DE TIPOS DE DADOS ---
    df['Invoice Number'] = df['Invoice Number'].astype(str).str.strip()
    df['Invoice Type'] = df['Invoice Type'].astype(str).str.strip().str.upper()
    invoices_alvo_str = [str(inv).strip() for inv in invoices_alvo]
    
    # Filtros F8 e Invoice Alvo
    df_f8 = df[df['Invoice Type'] == 'F8'].copy()
    df_f8_filtrado = df_f8[df_f8['Invoice Number'].isin(invoices_alvo_str)]
    
    if df_f8_filtrado.empty:
        print("❌ Aviso: A invoice não foi encontrada no filtro F8.")
        return df_f8_filtrado, pd.DataFrame()
        
    df_f8 = df_f8_filtrado
    
    # Restante da lógica (Quebra de lote)
    df_f8[['Material_Number', 'Batch_1']] = df_f8['Batch'].astype(str).str.split('/', n=1, expand=True)
    
    # BLINDAGEM DA CHAVE PRIMÁRIA F8
    df_f8['Delivery Number'] = df_f8['Delivery Number'].astype(str).str.split('.').str[0].str.strip()
    df_f8['Material_Number'] = df_f8['Material_Number'].astype(str).str.strip()
    df_f8['PK_Delivery_UPN_F8'] = df_f8['Delivery Number'] + df_f8['Material_Number']
    
    # Agrupamento (Preservando a PK_Delivery_UPN_F8)
    agrupado = df_f8.groupby([
        'Invoice Number', 'Invoice Date', 'Delivery Number', 
        'Material_Number', 'Extended Amount Currency', 'PK_Delivery_UPN_F8'
    ]).agg(
        Total_Qty_F8=('Extended Qty at the Item Level', 'sum'),
        Total_Invoice_Amount_F8=('Extended Amount at the Item Level', 'sum')
    ).reset_index()
    
    return df_f8, agrupado

# --- 4. PROCESSAMENTO DA F2 (INVOICE FÍSICA) ---
def process_bill2_f2(df_f8_agrupada):
    """Filtra as Invoices IV e cruza com os valores financeiros da F8."""
    print("⚙️ Processando F2 (Invoices IV) e cruzando com F8...")
    
    file_bil2 = get_latest_file("ZKP_MP06_Q5001_Bil2")
    df = pd.read_excel(file_bil2, sheet_name="1. ZKP_MP06_Q5001_Bil2")
    
    # Blindagem de tipos F2
    df['Invoice Type'] = df['Invoice Type'].astype(str).str.strip().str.upper()
    df['Delivery Number'] = df['Delivery Number'].astype(str).str.split('.').str[0].str.strip()
    
    # Filtro: Apenas IV e Quantidade diferente de zero
    df_f2 = df[(df['Invoice Type'] == 'IV') & (df['Extended Qty at the Item Level'] != 0)].copy()
    
    if df_f2.empty:
        print("❌ Aviso: Nenhuma Invoice IV encontrada na base.")
        return df_f2
    
    # Quebra de Batch 
    df_f2[['Material_Number', 'Batch_F2']] = df_f2['Batch'].astype(str).str.split('/', n=1, expand=True)
    
    # BLINDAGEM DA CHAVE PRIMÁRIA F2
    df_f2['Material_Number'] = df_f2['Material_Number'].astype(str).str.strip()
    df_f2['PK_Delivery_UPN_F2'] = df_f2['Delivery Number'] + df_f2['Material_Number']
    
    # O PRIMEIRO GRANDE MERGE: F2 recebendo os dados da F8
    df_merged = pd.merge(
        df_f2, 
        df_f8_agrupada, 
        left_on='PK_Delivery_UPN_F2', 
        right_on='PK_Delivery_UPN_F8', 
        how='left'
    )
    
    return df_merged

# --- 5. O MOTOR DE COMPLIANCE (CHECK POINTS) ---
def aplicar_regras_green_light(df_f2_f8, df_piloto):
    """Cruza a base financeira/física com as regras regulatórias (Piloto)."""
    print("⚙️ Aplicando regras de compliance e gerando Check Points...")
    
    # Limpeza do CFN para cruzar com a Piloto (Arranca caracteres especiais)
    df_f2_f8['CFN_Tratada_GreenLight'] = df_f2_f8['CFN Number'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True)
    
    # O SEGUNDO GRANDE MERGE: Cruzando com a Piloto Geral (ANVISA)
    df_final = pd.merge(
        df_f2_f8,
        df_piloto,
        left_on='CFN_Tratada_GreenLight',
        right_on='Código Tratado',
        how='left'
    )
    
    # --- CONSTRUÇÃO DOS CHECK POINTS DINÂMICOS ---
    def gerar_alertas(row):
        alertas = []
        
        # Regra 1: Existe na Piloto?
        if pd.isna(row.get('Código Tratado')):
            alertas.append("Check Código tratado na Tabela Piloto")
        else:
            # Regra 2: Status de Comercialização é 'Liberado'?
            status = str(row.get('Status de Comercialização', ''))
            if not status.lower().startswith('lib'):
                alertas.append("Check status de comercialização")
            
            # Regra 3: Detentor do Registro (Auto Suture / Medtronic)
            detentor = str(row.get('Detentor do Registro', ''))
            if 'suture' not in detentor.lower() and not detentor.lower().startswith('medtronic'):
                alertas.append("Check Detentor do Registro")
                
        return "; ".join(alertas) if alertas else "Green Light Autorizado"

    # Aplica a função linha a linha
    df_final['Check Point'] = df_final.apply(gerar_alertas, axis=1)
    
    return df_final


# --- ORQUESTRADOR PRINCIPAL ---
def run_green_light_pipeline(lista_de_invoices: list):
    """Executa o fluxo completo do pipeline."""
    # 1. Constrói a base regulatória
    piloto = build_piloto_geral()
    
    # 2. Puxa e agrupa a F8 baseada no input da TAISA
    f8_raw, f8_agrupada = process_bill2_f8(lista_de_invoices)
    
    # 3. Puxa a F2 e cruza com a F8
    f2_f8_cruzada = process_bill2_f2(f8_agrupada)
    
    # 4. Passa no motor de Compliance!
    base_final = aplicar_regras_green_light(f2_f8_cruzada, piloto)
    
    print("✅ Pipeline executado com sucesso!")
    return base_final

if __name__ == "__main__":
    # Teste isolado no terminal
    invoices_para_testar = ["1090748838"] 
    df_final = run_green_light_pipeline(invoices_para_testar)
    
    if not df_final.empty:
        print("\n🏆 RESULTADO DO GREEN LIGHT:")
        print(df_final[['Invoice Number_x', 'CFN Number', 'Check Point']].head(10))