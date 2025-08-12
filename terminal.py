import grpc
from concurrent import futures
import time
import threading
from datetime import datetime
import uuid

import terminal_pb2
import terminal_pb2_grpc
import backup_pb2
import backup_pb2_grpc
import heartbeat_pb2
import heartbeat_pb2_grpc

PORT_TO_TERMINAL_ID = {
    "50151": "1",
    "50152": "2",
    "50153": "3",
}

INITIAL_VEHICLES = {
    "Economicos": ["ECO01-Onix", "ECO02-Kwid", "ECO03-208"],
    "Intermediarios": ["INT01-City", "INT02-Cronos", "INT03-Virtus"],
    "SUV": ["SUV01-Commander", "SUV02-Q7", "SUV03-RX"],
    "Executivos": ["EXE01-BMW5", "EXE02-CorollaHybrid"],
    "Minivan": ["MIN01-Spin", "MIN02-Doblo", "MIN03-Livina"],
}

CLASS_MANAGEMENT_MAP = {
    "Economicos": "3",
    "Intermediarios": "2",
    "SUV": "2",
    "Executivos": "1",
    "Minivan": "1",
}

TERMINAL_ADDRESSES = {
    "1": "localhost:50151",
    "2": "localhost:50152",
    "3": "localhost:50153",
}

BACKUP_ADDRESS = "localhost:50052"
HEARTBEAT_SERVER_ADDRESS = "localhost:50053"
BACKUP_CALL_TIMEOUT = 7
FORWARD_CALL_TIMEOUT = 10


class TerminalServicer(terminal_pb2_grpc.TerminalServicer):
    def __init__(
        self, terminal_id_str, classes_gerenciadas_list, porta_terminal
    ):
        self.terminal_id_str = terminal_id_str
        self.terminal_numeric_id = PORT_TO_TERMINAL_ID[porta_terminal]

        self.log_file_name = f"terminal_{self.terminal_numeric_id}.txt"
        with open(self.log_file_name, "w") as f:
            f.write(
                f"--- Log do Terminal {self.terminal_numeric_id} ({self.terminal_id_str}) iniciado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            )

        self.classes_gerenciadas_internamente = set(classes_gerenciadas_list)

        self.veiculos_disponiveis = {}
        for classe_cfg, veiculos_cfg in INITIAL_VEHICLES.items():
            if classe_cfg in self.classes_gerenciadas_internamente:
                self.veiculos_disponiveis[classe_cfg] = list(veiculos_cfg)
            else:
                self.veiculos_disponiveis[classe_cfg] = []

        self.veiculos_locados = {}
        self.clientes_pendentes = {}
        self.encaminhamentos_pendentes = {}
        self.lock = threading.Lock()

    def _write_direct_log(self, formatted_message_with_timestamp_at_end):
        with open(self.log_file_name, "a") as f:
            f.write(f"{formatted_message_with_timestamp_at_end}\n")

    def _get_address_from_terminal_name(self, terminal_name_str):
        for num_id, addr in TERMINAL_ADDRESSES.items():
            if f"Terminal {num_id}" == terminal_name_str:
                return addr
        return None

    def _register_with_backup(
        self,
        cliente_id,
        classe_veiculo,
        nome_veiculo,
        status_backup,
        op_timestamp,
        request_id_pendencia_param=None,
        ip_cliente_pendente_param=None,
        porta_cliente_pendente_param=None,
    ):
        if status_backup == "PENDENTE":
            self._write_direct_log(
                f"Requisição enviada ao servidor de backup {cliente_id} para classe {classe_veiculo} PENDENTE em {op_timestamp}"
            )
        else:
            self._write_direct_log(
                f"Requisição enviada ao servidor de backup {cliente_id} para classe {classe_veiculo} {nome_veiculo if nome_veiculo else 'N/A'} CONCLUIDA em {op_timestamp}"
            )

        try:
            with grpc.insecure_channel(BACKUP_ADDRESS) as channel:
                stub = backup_pb2_grpc.BackupServiceStub(channel)
                backup_req_msg = backup_pb2.BackupRequest(
                    terminal_id=self.terminal_id_str,
                    cliente_id=cliente_id,
                    classe_veiculo=classe_veiculo,
                    nome_veiculo=nome_veiculo
                    if status_backup not in ["PENDENTE"]
                    else "",
                    status=status_backup,
                    timestamp=op_timestamp,
                    request_id_pendencia=request_id_pendencia_param
                    if request_id_pendencia_param
                    else "",
                    ip_cliente_pendente=ip_cliente_pendente_param
                    if ip_cliente_pendente_param
                    else "",
                    porta_cliente_pendente=porta_cliente_pendente_param
                    if porta_cliente_pendente_param
                    else "",
                )

                response = stub.RegistrarTransacao(
                    backup_req_msg, timeout=BACKUP_CALL_TIMEOUT
                )

                if response.status == "OK":
                    ts_backup_resp_str = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if status_backup == "PENDENTE":
                        self._write_direct_log(
                            f"Resposta recebida do servidor de backup {cliente_id} para classe {classe_veiculo} PENDENTE em {ts_backup_resp_str}"
                        )
                    else:
                        self._write_direct_log(
                            f"Resposta recebida do servidor de backup {cliente_id} para classe {classe_veiculo} {nome_veiculo if nome_veiculo else 'N/A'} CONCLUIDA em {ts_backup_resp_str}"
                        )
                    return True
                else:
                    return False
        except grpc.RpcError:
            return False
        except Exception:
            return False

    def RentACar(self, request: terminal_pb2.RentCarRequest, context):
        op_timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        classe_solicitada = request.Classe_veiculo
        cliente_id = request.ID_cliente
        ip_cliente = request.IP_cliente
        porta_cliente = request.Porta_cliente
        current_request_id = str(uuid.uuid4())

        self._write_direct_log(
            f"Requisição recebida do cliente {cliente_id} para classe {classe_solicitada} em {op_timestamp_str}"
        )

        if classe_solicitada not in self.classes_gerenciadas_internamente:
            target_terminal_numeric_id = CLASS_MANAGEMENT_MAP.get(
                classe_solicitada
            )
            if not target_terminal_numeric_id:
                return terminal_pb2.RentCarResponse(
                    message=f"CLASSE_NAO_ENCAMINHAVEL:{classe_solicitada}",
                    status="PENDENTE",
                    request_id="",
                    terminal_responsavel_id_str="",
                )

            target_terminal_address = TERMINAL_ADDRESSES.get(
                target_terminal_numeric_id
            )
            target_terminal_id_str_name = f"Terminal {target_terminal_numeric_id}"

            if not target_terminal_address:
                return terminal_pb2.RentCarResponse(
                    message=f"ERRO_INTERNO_ENCAMINHAMENTO:{classe_solicitada}",
                    status="PENDENTE",
                    request_id="",
                    terminal_responsavel_id_str="",
                )
            if self.terminal_numeric_id == target_terminal_numeric_id:
                return terminal_pb2.RentCarResponse(
                    message=f"ERRO_LOOP_ENCAMINHAMENTO:{classe_solicitada}",
                    status="PENDENTE",
                    request_id="",
                    terminal_responsavel_id_str="",
                )

            try:
                with grpc.insecure_channel(
                    target_terminal_address
                ) as forward_channel:
                    forward_stub = terminal_pb2_grpc.TerminalStub(
                        forward_channel
                    )
                    response_from_target = forward_stub.RentACar(
                        request, timeout=FORWARD_CALL_TIMEOUT
                    )

                    if (
                        response_from_target.status == "PENDENTE"
                        and response_from_target.request_id
                    ):
                        with self.lock:
                            self.encaminhamentos_pendentes[
                                current_request_id
                            ] = (
                                response_from_target.request_id,
                                response_from_target.terminal_responsavel_id_str,
                                classe_solicitada,
                                cliente_id,
                            )

                    return terminal_pb2.RentCarResponse(
                        message=response_from_target.message,
                        status=response_from_target.status,
                        request_id=current_request_id
                        if response_from_target.status == "PENDENTE"
                        and response_from_target.request_id
                        else "",
                        terminal_responsavel_id_str=response_from_target.terminal_responsavel_id_str
                        if response_from_target.status == "PENDENTE"
                        and response_from_target.request_id
                        else "",
                    )
            except grpc.RpcError:
                return terminal_pb2.RentCarResponse(
                    message=f"FALHA_ENCAMINHAMENTO:{classe_solicitada}",
                    status="PENDENTE",
                    request_id="",
                    terminal_responsavel_id_str="",
                )
            except Exception:
                return terminal_pb2.RentCarResponse(
                    message=f"ERRO_INESPERADO_ENCAMINHAMENTO:{classe_solicitada}",
                    status="PENDENTE",
                    request_id="",
                    terminal_responsavel_id_str="",
                )

        with self.lock:
            status_resp_cliente = "PENDENTE"
            msg_resp_cliente = classe_solicitada
            nome_veiculo_alocado = ""
            request_id_retorno_cliente = ""
            terminal_responsavel_retorno_cliente = ""
            lista_de_veiculos_da_classe = self.veiculos_disponiveis.get(
                classe_solicitada
            )

            if (
                lista_de_veiculos_da_classe is not None
                and len(lista_de_veiculos_da_classe) > 0
            ):
                veiculo = lista_de_veiculos_da_classe.pop(0)
                backup_confirmed = self._register_with_backup(
                    cliente_id,
                    classe_solicitada,
                    veiculo,
                    "CONCLUIDA",
                    op_timestamp_str,
                )
                if backup_confirmed:
                    self.veiculos_locados[cliente_id] = (
                        veiculo,
                        classe_solicitada,
                    )
                    status_resp_cliente = "CONCLUIDO"
                    msg_resp_cliente = veiculo
                    nome_veiculo_alocado = veiculo
                else:
                    lista_de_veiculos_da_classe.insert(0, veiculo)
                    msg_resp_cliente = f"FALHA_BACKUP:{classe_solicitada}"
                    status_resp_cliente = "PENDENTE"
            else:
                if lista_de_veiculos_da_classe is None:
                    msg_resp_cliente = (
                        f"ERRO_INTERNO_TERMINAL:{classe_solicitada}"
                    )
                    status_resp_cliente = "PENDENTE"
                else:
                    backup_confirmed = self._register_with_backup(
                        cliente_id,
                        classe_solicitada,
                        "",
                        "PENDENTE",
                        op_timestamp_str,
                        request_id_pendencia_param=current_request_id,
                        ip_cliente_pendente_param=ip_cliente,
                        porta_cliente_pendente_param=porta_cliente,
                    )
                    if backup_confirmed:
                        self.clientes_pendentes[current_request_id] = (
                            cliente_id,
                            classe_solicitada,
                            ip_cliente,
                            porta_cliente,
                            op_timestamp_str,
                        )
                        request_id_retorno_cliente = current_request_id
                        terminal_responsavel_retorno_cliente = (
                            self.terminal_id_str
                        )
                        status_resp_cliente = "PENDENTE"
                        msg_resp_cliente = classe_solicitada
                    else:
                        msg_resp_cliente = (
                            f"FALHA_BACKUP_PENDENCIA:{classe_solicitada}"
                        )
                        status_resp_cliente = "PENDENTE"

            if status_resp_cliente == "CONCLUIDO":
                self._write_direct_log(
                    f"Resposta enviada ao cliente {cliente_id}: {status_resp_cliente} {classe_solicitada}{nome_veiculo_alocado} em {op_timestamp_str}"
                )
            elif status_resp_cliente == "PENDENTE":
                if msg_resp_cliente == classe_solicitada:
                    self._write_direct_log(
                        f"Resposta enviada ao cliente {cliente_id}: {status_resp_cliente} {classe_solicitada} em {op_timestamp_str}"
                    )

            return terminal_pb2.RentCarResponse(
                message=msg_resp_cliente,
                status=status_resp_cliente,
                request_id=request_id_retorno_cliente,
                terminal_responsavel_id_str=terminal_responsavel_retorno_cliente,
            )

    def ReturnACar(self, request: terminal_pb2.ReturnCarRequest, context):
        op_timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cliente_id = request.ID_cliente
        veiculo_devolvido = request.Nome_veiculo
        classe_veiculo = request.Classe_veiculo

        self._write_direct_log(
            f"Requisição recebida do cliente {cliente_id} para classe {classe_veiculo} em {op_timestamp_str}"
        )

        devolucao_sucesso = False
        msg_erro_devolucao = ""
        with self.lock:
            backup_confirmed = self._register_with_backup(
                cliente_id,
                classe_veiculo,
                veiculo_devolvido,
                "DEVOLUCAO_CONCLUIDA",
                op_timestamp_str,
            )
            if backup_confirmed:
                if classe_veiculo not in self.veiculos_disponiveis:
                    self.veiculos_disponiveis[classe_veiculo] = []
                self.veiculos_disponiveis[classe_veiculo].append(
                    veiculo_devolvido
                )
                if (
                    cliente_id in self.veiculos_locados
                    and self.veiculos_locados[cliente_id][0]
                    == veiculo_devolvido
                ):
                    del self.veiculos_locados[cliente_id]
                devolucao_sucesso = True
                self._verificar_clientes_pendentes(classe_veiculo)
            else:
                devolucao_sucesso = False
                msg_erro_devolucao = "Falha ao registrar devolução no backup."

        if devolucao_sucesso:
            self._write_direct_log(
                f"Resposta enviada ao cliente {cliente_id}: CONCLUIDO {classe_veiculo}{veiculo_devolvido} em {op_timestamp_str}"
            )

        return terminal_pb2.ReturnCarResponse(
            success=devolucao_sucesso, error_message=msg_erro_devolucao
        )

    def _verificar_clientes_pendentes(self, classe_veiculo_liberado):
        clientes_atendidos_nesta_chamada = 0
        request_ids_pendentes = list(self.clientes_pendentes.keys())

        for req_id in request_ids_pendentes:
            if req_id not in self.clientes_pendentes:
                continue

            (
                cliente_id,
                classe_req,
                ip_cliente,
                porta_cliente,
                _,
            ) = self.clientes_pendentes[req_id]
            if classe_req == classe_veiculo_liberado:
                lista_veiculos_da_classe = self.veiculos_disponiveis.get(
                    classe_req
                )
                if (
                    lista_veiculos_da_classe is not None
                    and len(lista_veiculos_da_classe) > 0
                ):
                    veiculo_para_alocar = lista_veiculos_da_classe.pop(0)

                    ts_pendencia_concluida_str = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                    backup_confirmed = self._register_with_backup(
                        cliente_id,
                        classe_req,
                        veiculo_para_alocar,
                        "CONCLUIDA",
                        ts_pendencia_concluida_str,
                        request_id_pendencia_param=req_id,
                    )
                    if backup_confirmed:
                        self.veiculos_locados[cliente_id] = (
                            veiculo_para_alocar,
                            classe_req,
                        )
                        del self.clientes_pendentes[req_id]
                        clientes_atendidos_nesta_chamada += 1
                        try:
                            target_addr = f"{ip_cliente}:{porta_cliente}"
                            with grpc.insecure_channel(
                                target_addr
                            ) as client_channel:
                                client_stub = (
                                    terminal_pb2_grpc.CallbackServiceStub(
                                        client_channel
                                    )
                                )
                                callback_msg_content = f"CONCLUIDO: Veículo {veiculo_para_alocar} da classe {classe_req} está disponível. (ReqID: {req_id})"
                                callback_msg = (
                                    terminal_pb2.CallbackMessage(
                                        message_content=callback_msg_content
                                    )
                                )
                                client_stub.ReceiveCallback(
                                    callback_msg, timeout=5
                                )
                                self._write_direct_log(
                                    f"Resposta enviada ao cliente {cliente_id}: CONCLUIDO {classe_req}{veiculo_para_alocar} em {ts_pendencia_concluida_str}"
                                )
                        except grpc.RpcError:
                            pass
                        except Exception:
                            pass
                    else:
                        lista_veiculos_da_classe.insert(
                            0, veiculo_para_alocar
                        )
                else:
                    break

    def CheckPending(
        self, request: terminal_pb2.CheckPendingStatusRequest, context
    ):
        req_id_consulta = request.request_id
        cliente_id_consulta = request.ID_cliente
        with self.lock:
            if req_id_consulta in self.clientes_pendentes:
                (
                    pendente_cliente_id,
                    pendente_classe,
                    _,
                    _,
                    _,
                ) = self.clientes_pendentes[req_id_consulta]
                if pendente_cliente_id == cliente_id_consulta:
                    return terminal_pb2.CheckPendingStatusResponse(
                        query_status=terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.STILL_PENDING_HERE,
                        classe_veiculo=pendente_classe,
                        terminal_atual_responsavel_id_str=self.terminal_id_str,
                    )
                else:
                    return terminal_pb2.CheckPendingStatusResponse(
                        query_status=terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.REQUEST_UNKNOWN
                    )

            if req_id_consulta in self.encaminhamentos_pendentes:
                (
                    id_no_destino,
                    id_terminal_destino_str_name,
                    classe_enc,
                    cliente_original_enc,
                ) = self.encaminhamentos_pendentes[req_id_consulta]
                if cliente_original_enc == cliente_id_consulta:
                    target_address_destino = (
                        self._get_address_from_terminal_name(
                            id_terminal_destino_str_name
                        )
                    )

                    if target_address_destino:
                        try:
                            with grpc.insecure_channel(
                                target_address_destino
                            ) as dest_channel:
                                dest_stub = terminal_pb2_grpc.TerminalStub(
                                    dest_channel
                                )
                                status_req_destino = (
                                    terminal_pb2.CheckPendingStatusRequest(
                                        request_id=id_no_destino,
                                        ID_cliente=cliente_original_enc,
                                    )
                                )
                                resp_destino = dest_stub.CheckPending(
                                    status_req_destino,
                                    timeout=FORWARD_CALL_TIMEOUT,
                                )

                                final_query_status = terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.ERROR_CHECKING_STATUS
                                if (
                                    resp_destino.query_status
                                    == terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.STILL_PENDING_HERE
                                ):
                                    final_query_status = terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.FORWARDED_AND_PENDING_ELSEWHERE
                                elif (
                                    resp_destino.query_status
                                    == terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.FULFILLED_BY_THIS_TERMINAL
                                ):
                                    final_query_status = terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.FORWARDED_AND_FULFILLED_ELSEWHERE
                                elif (
                                    resp_destino.query_status
                                    == terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.REQUEST_UNKNOWN
                                ):
                                    final_query_status = terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.REQUEST_UNKNOWN
                                    if (
                                        req_id_consulta
                                        in self.encaminhamentos_pendentes
                                    ):
                                        del self.encaminhamentos_pendentes[
                                            req_id_consulta
                                        ]

                                return terminal_pb2.CheckPendingStatusResponse(
                                    query_status=final_query_status,
                                    veiculo_alocado=resp_destino.veiculo_alocado,
                                    classe_veiculo=resp_destino.classe_veiculo,
                                    terminal_atual_responsavel_id_str=resp_destino.terminal_atual_responsavel_id_str,
                                    original_request_status_no_destino=terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.Name(
                                        resp_destino.query_status
                                    ),
                                    original_request_message_no_destino=f"Veiculo: {resp_destino.veiculo_alocado}"
                                    if resp_destino.veiculo_alocado
                                    else "N/A",
                                )
                        except grpc.RpcError:
                            return terminal_pb2.CheckPendingStatusResponse(
                                query_status=terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.ERROR_CHECKING_STATUS,
                                terminal_atual_responsavel_id_str=id_terminal_destino_str_name,
                                original_request_message_no_destino=f"Falha ao contatar {id_terminal_destino_str_name}",
                            )
                        except Exception:
                            return terminal_pb2.CheckPendingStatusResponse(
                                query_status=terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.ERROR_CHECKING_STATUS,
                                terminal_atual_responsavel_id_str=id_terminal_destino_str_name,
                                original_request_message_no_destino=f"Erro ao consultar {id_terminal_destino_str_name}",
                            )
                    else:
                        return terminal_pb2.CheckPendingStatusResponse(
                            query_status=terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.ERROR_CHECKING_STATUS
                        )
                else:
                    return terminal_pb2.CheckPendingStatusResponse(
                        query_status=terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.REQUEST_UNKNOWN
                    )

        return terminal_pb2.CheckPendingStatusResponse(
            query_status=terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.REQUEST_UNKNOWN
        )

    def GetAvailableVehicles(
        self, request: terminal_pb2.GetAvailableVehiclesRequest, context
    ):
        response = terminal_pb2.GetAvailableVehiclesResponse(
            terminal_id_str=self.terminal_id_str
        )
        try:
            with self.lock:
                classes_a_consultar = []
                if request.classe_veiculo_desejada:
                    if (
                        request.classe_veiculo_desejada
                        in self.veiculos_disponiveis
                    ):
                        classes_a_consultar.append(
                            request.classe_veiculo_desejada
                        )
                else:
                    classes_a_consultar = list(
                        self.veiculos_disponiveis.keys()
                    )
                for nome_classe in classes_a_consultar:
                    veiculos_na_classe = self.veiculos_disponiveis.get(
                        nome_classe, []
                    )
                    class_avail = terminal_pb2.ClassAvailability(
                        nome_classe=nome_classe,
                        quantidade_disponivel=len(veiculos_na_classe),
                    )
                    response.disponibilidade_por_classe.append(class_avail)
        except Exception as e:
            response.error_message = f"Erro interno no terminal: {str(e)}"
        return response


def enviar_heartbeat(terminal_id_str, porta_terminal_str):
    service_name_for_heartbeat = terminal_id_str

    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with grpc.insecure_channel(HEARTBEAT_SERVER_ADDRESS) as channel:
                stub = heartbeat_pb2_grpc.HeartbeatServiceStub(channel)
                heartbeat_request = heartbeat_pb2.HeartbeatRequest(
                    service_id=service_name_for_heartbeat, timestamp=timestamp
                )
                stub.EnviarHeartbeat(heartbeat_request)
        except grpc.RpcError:
            pass
        time.sleep(5)


def serve(
    terminal_id_str_arg, classes_gerenciadas_arg_list, porta_terminal_arg_str
):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    terminal_servicer = TerminalServicer(
        terminal_id_str_arg,
        classes_gerenciadas_arg_list,
        porta_terminal_arg_str,
    )
    terminal_pb2_grpc.add_TerminalServicer_to_server(terminal_servicer, server)

    server.add_insecure_port(f"[::]:{porta_terminal_arg_str}")
    server.start()
    print(
        f"{terminal_id_str_arg} iniciado na porta {porta_terminal_arg_str}."
    )

    heartbeat_thread = threading.Thread(
        target=enviar_heartbeat,
        args=(terminal_id_str_arg, porta_terminal_arg_str),
        daemon=True,
    )
    heartbeat_thread.start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Coloque o id do terminal (Ex: python3 terminal.py <id_do_terminal (1, 2 ou 3))")
        sys.exit(1)

    terminal_numeric_id_arg = sys.argv[1]

    if terminal_numeric_id_arg == "1":
        terminal_id_str_main = "Terminal 1"
        classes_main_arg = ["Executivos", "Minivan"]
        porta_terminal_main = "50151"
    elif terminal_numeric_id_arg == "2":
        terminal_id_str_main = "Terminal 2"
        classes_main_arg = ["Intermediarios", "SUV"]
        porta_terminal_main = "50152"
    elif terminal_numeric_id_arg == "3":
        terminal_id_str_main = "Terminal 3"
        classes_main_arg = ["Economicos"]
        porta_terminal_main = "50153"
    else:
        print("Id do terminal inválido (use 1, 2 ou 3)")
        sys.exit(1)

    serve(terminal_id_str_main, classes_main_arg, porta_terminal_main)