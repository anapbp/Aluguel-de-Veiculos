import os
import glob 


arquivos_log_terminal = ["terminal_1.txt", "terminal_2.txt", "terminal_3.txt"]
pasta_logs_clientes = "logs_clientes"
outros_logs_gerais = ["backup.txt", "heartbeat.txt", "pending_requests.json"]

def limpar_arquivos_especificos(lista_arquivos):
    """Apaga arquivos de uma lista fornecida."""
    for nome_arquivo in lista_arquivos:
        if os.path.exists(nome_arquivo):
            try:
                os.remove(nome_arquivo)
                print(f"Arquivo '{nome_arquivo}' apagado com sucesso.")
            except OSError as e:
                print(f"Erro ao apagar o arquivo '{nome_arquivo}': {e}")
        else:
            print(f"Arquivo '{nome_arquivo}' não encontrado.")

def limpar_conteudo_pasta(nome_pasta):
    """Apaga todos os arquivos dentro de uma pasta especificada."""
    if os.path.exists(nome_pasta) and os.path.isdir(nome_pasta):
        arquivos_na_pasta = glob.glob(os.path.join(nome_pasta, '*'))
        
        if not arquivos_na_pasta:
            print(f"Pasta '{nome_pasta}' já está vazia.")
            return

        for arquivo_para_apagar in arquivos_na_pasta:
            try:
                if os.path.isfile(arquivo_para_apagar): 
                    os.remove(arquivo_para_apagar)
                    print(f"Arquivo '{arquivo_para_apagar}' dentro da pasta '{nome_pasta}' apagado com sucesso.")
            except OSError as e:
                print(f"Erro ao apagar o arquivo '{arquivo_para_apagar}' dentro da pasta '{nome_pasta}': {e}")
    elif not os.path.exists(nome_pasta):
        print(f"Pasta '{nome_pasta}' não encontrada.")
    else:
        print(f"'{nome_pasta}' não é um diretório válido.")


if __name__ == "__main__":

    limpar_arquivos_especificos(arquivos_log_terminal)
    limpar_conteudo_pasta(pasta_logs_clientes)
    limpar_arquivos_especificos(outros_logs_gerais)

    print("\nLimpeza de logs concluída.")
