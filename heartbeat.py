import grpc
from concurrent import futures
import time
from datetime import datetime
import threading

import heartbeat_pb2
import heartbeat_pb2_grpc


servicos_ativos = {}
servicos_lock = threading.Lock()

HEARTBEAT_LOG_FILE = "heartbeat.txt"
HEARTBEAT_TIMEOUT_SECONDS = 10 
MONITOR_INTERVAL_SECONDS = 5 

class HeartbeatServiceServicer(heartbeat_pb2_grpc.HeartbeatServiceServicer):
    def EnviarHeartbeat(self, request: heartbeat_pb2.HeartbeatRequest, context):
        service_id = request.service_id
        timestamp_str = request.timestamp
        try:
            timestamp_dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            with servicos_lock:
                servicos_ativos[service_id] = timestamp_dt
            return heartbeat_pb2.HeartbeatResponse(status="OK")
        except ValueError:
            print(f"[HEARTBEAT_SERVER_ERROR] Timestamp inválido de {service_id}: {timestamp_str}")
            return heartbeat_pb2.HeartbeatResponse(status="ERRO_TIMESTAMP_INVALIDO")
        except Exception as e:
            print(f"[HEARTBEAT_SERVER_ERROR] Erro ao processar heartbeat de {service_id}: {e}")
            return heartbeat_pb2.HeartbeatResponse(status="ERRO_INTERNO")


def monitorar_servicos():

    with open(HEARTBEAT_LOG_FILE, "w") as log_file:
        log_file.write(f"--- Log do Servidor de Heartbeat iniciado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")

    while True:
        time.sleep(MONITOR_INTERVAL_SECONDS)
        now = datetime.now()
        log_entries = [] 

        with servicos_lock: 
            if not servicos_ativos:
                log_entries.append(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Nenhum serviço enviando heartbeats\n")

            for service_id, last_seen in list(servicos_ativos.items()): 
                delta = (now - last_seen).total_seconds()
                status = "ativo" if delta <= HEARTBEAT_TIMEOUT_SECONDS else "inativo"
                log_line = (
                    f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"{service_id} está {status}, ultima mensagem recebida em {last_seen.strftime('%Y-%m-%d %H:%M:%S')}, delta: {delta:.2f}s\n"
                )
                log_entries.append(log_line)
        
        try:
            with open(HEARTBEAT_LOG_FILE, "a") as log_file:
                for entry in log_entries:
                    log_file.write(entry)
        except Exception as e:
            print(f"[HEARTBEAT_MONITOR_ERROR] Falha ao escrever em {HEARTBEAT_LOG_FILE}: {e}")


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    heartbeat_pb2_grpc.add_HeartbeatServiceServicer_to_server(HeartbeatServiceServicer(), server)
    
    porta_heartbeat = '[::]:50053' 
    try:
        server.add_insecure_port(porta_heartbeat)
        server.start()
        print(f"Servidor de Heartbeat iniciado.")
    except RuntimeError as e:
        print(f"ERRO ao iniciar Servidor de Heartbeat.")
        return 

    monitor_thread = threading.Thread(target=monitorar_servicos, daemon=True)
    monitor_thread.start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Servidor de Heartbeat desligando...")
    finally:
        server.stop(0)
        print("Servidor de Heartbeat finalizado.")

if __name__ == '__main__':
    serve()