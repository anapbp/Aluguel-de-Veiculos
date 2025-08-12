import grpc
from concurrent import futures
import time
from datetime import datetime
import threading
import json
import os

import backup_pb2
import backup_pb2_grpc
import heartbeat_pb2
import heartbeat_pb2_grpc

BACKUP_FILE = "backup.txt"
PENDING_REQUESTS_FILE = "pending_requests.json"
pending_file_lock = threading.Lock()
HEARTBEAT_SERVER_ADDRESS = "localhost:50053"



def load_pending_requests():
    with pending_file_lock:
        if not os.path.exists(PENDING_REQUESTS_FILE):
            return {}
        try:
            with open(PENDING_REQUESTS_FILE, "r") as f:
                content = f.read()
                if not content:
                    return {}
                return json.loads(content)
        except json.JSONDecodeError:
            print(
                f"[WARNING] {PENDING_REQUESTS_FILE} corrompido. Iniciando com lista vazia."
            )
            return {}
        except Exception as e:
            print(
                f"[ERRO] Erro ao carregar {PENDING_REQUESTS_FILE}: {e}. Iniciando com lista vazia."
            )
            return {}


def save_pending_requests(pending_data):
    with pending_file_lock:
        try:
            with open(PENDING_REQUESTS_FILE, "w") as f:
                json.dump(pending_data, f, indent=2)
        except Exception as e:
            print(
                f"[ERRO] Falha ao salvar {PENDING_REQUESTS_FILE}: {e}"
            )


class BackupServiceServicer(backup_pb2_grpc.BackupServiceServicer):
    def RegistrarTransacao(self, request: backup_pb2.BackupRequest, context):
        log_line = (
            f"Requisição recebida do terminal {request.terminal_id} "
            f"para classe {request.classe_veiculo} "
            f"{request.nome_veiculo if request.nome_veiculo else 'N/A'} "
            f"{request.status} em {request.timestamp}\n"
        )
        try:
            with open(BACKUP_FILE, "a") as log_file:
                log_file.write(log_line)
        except Exception as e:
            print(f"[ERRO] Falha ao escrever em {BACKUP_FILE}: {e}")
            return backup_pb2.BackupResponse(
                status=f"Erro ao logar transacao: {e}"
            )

        pending_requests = load_pending_requests()
        if request.status == "PENDENTE" and request.request_id_pendencia:
            pending_requests[request.request_id_pendencia] = {
                "cliente_id": request.cliente_id,
                "classe_veiculo": request.classe_veiculo,
                "ip_cliente": request.ip_cliente_pendente,
                "porta_cliente": request.porta_cliente_pendente,
                "terminal_id_responsavel": request.terminal_id,
                "timestamp_entrada": request.timestamp,
                "status_pendencia": "ATIVA",
            }
        elif request.status == "CONCLUIDA" and request.request_id_pendencia:
            if request.request_id_pendencia in pending_requests:
                del pending_requests[request.request_id_pendencia]

        save_pending_requests(pending_requests)
        return backup_pb2.BackupResponse(status="OK")

    def ConsultarPendencias(
        self, request: backup_pb2.QueryPendingRequests, context
    ):
        response = backup_pb2.QueryPendingResponse()
        pending_requests_data = load_pending_requests()
        found_pendencias = []
        for req_id, data in pending_requests_data.items():
            if (
                data.get("status_pendencia") != "ATIVA"
                and request.apenas_ativas
            ):
                continue
            match_terminal = True
            if (
                request.terminal_id_responsavel
                and data.get("terminal_id_responsavel")
                != request.terminal_id_responsavel
            ):
                match_terminal = False
            match_classe = True
            if (
                request.classe_veiculo_desejada
                and data.get("classe_veiculo")
                != request.classe_veiculo_desejada
            ):
                match_classe = False
            if match_terminal and match_classe:
                found_pendencias.append(
                    backup_pb2.PendingRequestInfo(
                        request_id=req_id,
                        cliente_id=data.get("cliente_id", ""),
                        classe_veiculo=data.get("classe_veiculo", ""),
                        ip_cliente=data.get("ip_cliente", ""),
                        porta_cliente=data.get("porta_cliente", ""),
                        terminal_id_original_responsavel=data.get(
                            "terminal_id_responsavel", ""
                        ),
                        timestamp_entrada_pendencia=data.get(
                            "timestamp_entrada", ""
                        ),
                    )
                )
        if found_pendencias:
            response.pendencias.extend(found_pendencias)
        return response


def enviar_heartbeat_para_servidor():
    service_id_backup = "BackupService"

    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with grpc.insecure_channel(HEARTBEAT_SERVER_ADDRESS) as channel:
                stub = heartbeat_pb2_grpc.HeartbeatServiceStub(channel)
                heartbeat_request = heartbeat_pb2.HeartbeatRequest(
                    service_id=service_id_backup, timestamp=timestamp
                )
                stub.EnviarHeartbeat(
                    heartbeat_request, timeout=3
                ) 
        except grpc.RpcError:
            pass
        except Exception:
            pass
        time.sleep(5)


def serve():
    if not os.path.exists(PENDING_REQUESTS_FILE):
        save_pending_requests({})

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    backup_pb2_grpc.add_BackupServiceServicer_to_server(
        BackupServiceServicer(), server
    )

    porta_backup = "[::]:50052"
    try:
        server.add_insecure_port(porta_backup)
        server.start()
        print(
            f"Servidor de Backup iniciado."
        )
    except RuntimeError as e:
        print(f"ERRO ao iniciar Servidor de Backup")
        return

    heartbeat_thread = threading.Thread(
        target=enviar_heartbeat_para_servidor, daemon=True
    )
    heartbeat_thread.start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\nServidor de Backup desligando...")
    finally:
        server.stop(0)
        print("Servidor de Backup finalizado.")


if __name__ == "__main__":
    serve()