import grpc
from concurrent import futures
import time
import random

import guiche_info_pb2
import guiche_info_pb2_grpc

HEARTBEAT_LOG = "heartbeat.txt"

TERMINAIS = {
    "Terminal 1": "localhost:50151",
    "Terminal 2": "localhost:50152",
    "Terminal 3": "localhost:50153"
}

def obter_terminais_ativos():

    ultimo_status = {} 

    try:
        with open(HEARTBEAT_LOG, "r") as file:
            linhas = file.readlines()
            for linha in reversed(linhas):
                if "backup" in linha.lower():
                    continue

                for terminal in TERMINAIS:
                    if terminal in linha and terminal not in ultimo_status:
                        if "inativo" in linha:
                            ultimo_status[terminal] = "inativo"
                        elif " ativo" in linha:
                            ultimo_status[terminal] = "ativo"

                if len(ultimo_status) == len(TERMINAIS):
                    break

    except FileNotFoundError:
        print(f"Arquivo {HEARTBEAT_LOG} não encontrado.")

    ativos = [t for t, status in ultimo_status.items() if status == "ativo"]
    return ativos



class InformationServicer(guiche_info_pb2_grpc.InformationServicer):
    def TerminalOnLine(self, request, context):

        ativos = obter_terminais_ativos()

        print(f">> Terminais ativos no momento: {ativos}")

        if not ativos:
            print("- Nenhum terminal ativo encontrado.")
            return guiche_info_pb2.InfoReply(message="")

        escolhido = random.choice(ativos)
        endereco = TERMINAIS[escolhido]

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Terminal ativo escolhido: {escolhido} ({endereco})")

        return guiche_info_pb2.InfoReply(message=endereco)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    guiche_info_pb2_grpc.add_InformationServicer_to_server(InformationServicer(), server)
    server.add_insecure_port('[::]:50051')  
    server.start()
    print("Servidor Guichê de Informações iniciado na porta 50051.")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
