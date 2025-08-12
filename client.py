import grpc
import guiche_info_pb2
import guiche_info_pb2_grpc
import terminal_pb2
import terminal_pb2_grpc
import threading
from multiprocessing.pool import ThreadPool
import time
from datetime import datetime
import random
from concurrent import futures
import os

INFO_ADDRESS = "localhost:50051"
nomes_clientes = ["Alice", "Bob", "Charlie", "David", "Eve", "Nick", "Ema", "Maria"]

TERMINAL_ADDRESS_TO_ID = {
    "localhost:50151": "Terminal 1",
    "localhost:50152": "Terminal 2",
    "localhost:50153": "Terminal 3",
}
ID_TO_TERMINAL_ADDRESS = {v: k for k, v in TERMINAL_ADDRESS_TO_ID.items()}

ALL_TERMINAL_ADDRESSES = list(TERMINAL_ADDRESS_TO_ID.keys())
LOGS_DIR_CLIENTES = "logs_clientes"

client_rent_status = {}
client_rent_status_lock = threading.Lock()


def _get_terminal_id_from_address(address):
    return TERMINAL_ADDRESS_TO_ID.get(address, address if address else "N/A")


def _get_address_from_terminal_id_str(terminal_id_str):
    return ID_TO_TERMINAL_ADDRESS.get(terminal_id_str, None)


def consultar_disponibilidade_terminais(origem_da_chamada="SCRIPT_MAIN"):
    print(
        f"\n--- [INFO] CONSULTANDO DISPONIBILIDADE (Chamado por: {origem_da_chamada}) ---"
    )

    known_terminal_addresses_for_query = {
        "Terminal 1": "localhost:50151",
        "Terminal 2": "localhost:50152",
        "Terminal 3": "localhost:50153",
    }

    for terminal_nome, terminal_addr in known_terminal_addresses_for_query.items():
        try:
            with grpc.insecure_channel(terminal_addr) as channel:
                stub = terminal_pb2_grpc.TerminalStub(channel)
                get_vehicles_req = terminal_pb2.GetAvailableVehiclesRequest()
                response = stub.GetAvailableVehicles(get_vehicles_req, timeout=3)

                if response.error_message:
                    print(
                        f"  [ERRO] Erro ao consultar {response.terminal_id_str}: {response.error_message}"
                    )
                    continue

                print(f"  [INFO] Disponibilidade no {response.terminal_id_str}:")
                if not response.disponibilidade_por_classe:
                    print(f"    Nenhuma informação de classe retornada.")
                for class_info in response.disponibilidade_por_classe:
                    print(
                        f"    - Classe '{class_info.nome_classe}': {class_info.quantidade_disponivel} disponível(is)"
                    )
        except grpc.RpcError as e:
            print(
                f"  [ERRO] Falha ao consultar {terminal_nome} ({terminal_addr}): {e.code()}"
            )
        except Exception as e_gen:
            print(
                f"  [ERRO] Erro inesperado ao consultar {terminal_nome} ({terminal_addr}): {str(e_gen)}"
            )
    print("--- [INFO] FIM DA CONSULTA DE DISPONIBILIDADE ---\n")


class CallbackServiceServicer(terminal_pb2_grpc.CallbackServiceServicer):
    def __init__(self, cliente_nome_completo):
        self.cliente_nome_completo = cliente_nome_completo

    def ReceiveCallback(self, request: terminal_pb2.CallbackMessage, context):
        message_content = request.message_content
        print(
            f"\n[CALLBACK CLIENTE {self.cliente_nome_completo}] Mensagem recebida: {message_content}"
        )
        with client_rent_status_lock:
            if self.cliente_nome_completo in client_rent_status:
                if message_content.startswith("CONCLUIDO:"):
                    client_rent_status[self.cliente_nome_completo][
                        "status"
                    ] = "CONCLUIDO_POR_CALLBACK"
                    try:
                        parts = message_content.split(" ")
                        veiculo = parts[2]
                        classe = parts[5].replace(".", "")
                        client_rent_status[self.cliente_nome_completo][
                            "veiculo"
                        ] = veiculo
                        client_rent_status[self.cliente_nome_completo][
                            "classe"
                        ] = classe
                    except IndexError:
                        client_rent_status[self.cliente_nome_completo][
                            "veiculo"
                        ] = "Desconhecido(cb)"
                        client_rent_status[self.cliente_nome_completo][
                            "classe"
                        ] = "Desconhecida(cb)"
        return terminal_pb2.CallbackResponse(status="Callback Recebido OK")


def start_client_as_server(port, cliente_nome_completo):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    terminal_pb2_grpc.add_CallbackServiceServicer_to_server(
        CallbackServiceServicer(cliente_nome_completo), server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    try:
        server.wait_for_termination()
    except Exception as e:
        print(
            f"[ERRO CLIENTE {cliente_nome_completo}] Servidor Callback interrompido: {e}"
        )


def cliente_tarefa(
    classe_solicitada: str, nome_cliente_base: str, cliente_idx: int
):
    cliente_id_unico = f"{nome_cliente_base}_{cliente_idx}"
    ip_cliente = "localhost"
    porta_cliente_callback = str(40000 + cliente_idx)
    log_dir_path = LOGS_DIR_CLIENTES
    try:
        os.makedirs(log_dir_path, exist_ok=True)
        if not os.path.isdir(log_dir_path):
            raise OSError(f"'{log_dir_path}' não é um diretório.")
    except OSError as e:
        print(
            f"[AVISO CLIENTE {cliente_id_unico}] Erro ao criar diretório de logs '{log_dir_path}': {e}. Logs não serão salvos em arquivo."
        )
        log_dir_path = ""
    log_file_name = (
        os.path.join(log_dir_path, f"cliente_{cliente_id_unico}.txt")
        if log_dir_path
        else ""
    )

    if log_file_name:
        with open(log_file_name, "w") as f:
            f.write(
                f"--- Log Cliente {cliente_id_unico} ({ip_cliente}:{porta_cliente_callback}) em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
            )

    def _log_to_file(formatted_line_with_timestamp_at_end):
        if log_file_name:
            with open(log_file_name, "a") as f:
                f.write(f"{formatted_line_with_timestamp_at_end}\n")

    print(
        f"[CLIENTE {cliente_id_unico}] Iniciando tarefa: buscando classe '{classe_solicitada}'"
    )

    server_thread = threading.Thread(
        target=start_client_as_server,
        args=(porta_cliente_callback, cliente_id_unico),
        daemon=True,
    )
    server_thread.start()
    time.sleep(0.5)

    with client_rent_status_lock:
        client_rent_status[cliente_id_unico] = {
            "status": "INICIANDO",
            "veiculo": None,
            "classe": None,
            "current_request_id": None,
            "current_terminal_responsavel_id_str": None,
        }

    veiculo_alugado_info = None
    max_tentativas_guiche = len(ALL_TERMINAL_ADDRESSES) + 3

    for tentativa_guiche in range(max_tentativas_guiche):
        with client_rent_status_lock:
            current_client_status = client_rent_status[cliente_id_unico][
                "status"
            ]
        if current_client_status in [
            "CONCLUIDO_POR_CALLBACK",
            "CONCLUIDO_DIRETO",
        ]:
            break

        terminal_address = None
        ts_guiche_req = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _log_to_file(
            f"Requisição enviada ao guichê de informações em {ts_guiche_req}"
        )
        try:
            with grpc.insecure_channel(INFO_ADDRESS) as info_channel:
                stub_info = guiche_info_pb2_grpc.InformationStub(info_channel)
                response_info = stub_info.TerminalOnLine(
                    guiche_info_pb2.Empty(), timeout=5
                )
                terminal_address = response_info.message
                ts_guiche_resp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                terminal_id_guiche = _get_terminal_id_from_address(
                    terminal_address
                )
                _log_to_file(
                    f"Resposta recebida do guichê de informações em {ts_guiche_resp} termina disponível: {terminal_id_guiche}"
                )
        except grpc.RpcError:
            time.sleep(random.uniform(2, 4))
            continue

        if not terminal_address:
            print(
                f"[CLIENTE {cliente_id_unico}] [GUICHÊ] Nenhum terminal ativo informado. Tentando novamente em breve."
            )
            time.sleep(random.uniform(3, 5))
            continue

        ts_term_req = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        term_id_req = _get_terminal_id_from_address(terminal_address)
        _log_to_file(
            f"Requisição enviada ao {term_id_req} para classe {classe_solicitada} em {ts_term_req}"
        )
        try:
            with grpc.insecure_channel(terminal_address) as term_channel:
                stub_terminal = terminal_pb2_grpc.TerminalStub(term_channel)
                rent_request = terminal_pb2.RentCarRequest(
                    ID_cliente=cliente_id_unico,
                    IP_cliente=ip_cliente,
                    Porta_cliente=porta_cliente_callback,
                    Classe_veiculo=classe_solicitada,
                )
                response_terminal = stub_terminal.RentACar(
                    rent_request, timeout=15
                )
                ts_term_resp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                term_id_resp = _get_terminal_id_from_address(terminal_address)
                status_resp = response_terminal.status
                msg_veiculo = response_terminal.message
                _log_to_file(
                    f"Resposta recebida de {term_id_resp}: {status_resp} {msg_veiculo} em {ts_term_resp}"
                )

                if response_terminal.status == "CONCLUIDO":
                    print(
                        f"[CLIENTE {cliente_id_unico}] [ALUGUEL] CONCLUÍDO! Veículo: {response_terminal.message} (Terminal: {term_id_resp})"
                    )
                    veiculo_alugado_info = (
                        response_terminal.message,
                        classe_solicitada,
                        terminal_address,
                    )
                    with client_rent_status_lock:
                        client_rent_status[cliente_id_unico].update(
                            {
                                "status": "CONCLUIDO_DIRETO",
                                "veiculo": response_terminal.message,
                                "classe": classe_solicitada,
                                "current_request_id": None,
                                "current_terminal_responsavel_id_str": None,
                            }
                        )
                    break
                elif response_terminal.status == "PENDENTE":
                    msg_pendencia = response_terminal.message
                    req_id_pendencia = response_terminal.request_id
                    term_resp_pendencia = (
                        response_terminal.terminal_responsavel_id_str
                    )

                    if (
                        msg_pendencia.startswith("FALHA_")
                        or msg_pendencia.startswith("CLASSE_NAO_ENCAMINHAVEL")
                        or msg_pendencia.startswith("ERRO_")
                    ):
                        time.sleep(random.uniform(1, 2))
                        continue
                    else:
                        print(
                            f"[CLIENTE {cliente_id_unico}] [ALUGUEL] PENDENTE para '{classe_solicitada}'. ReqID: {req_id_pendencia}, Terminal Responsável: {term_resp_pendencia if term_resp_pendencia else term_id_resp}. Aguardando callback..."
                        )
                        with client_rent_status_lock:
                            client_rent_status[cliente_id_unico].update(
                                {
                                    "status": "AGUARDANDO_CALLBACK",
                                    "classe": classe_solicitada,
                                    "current_request_id": req_id_pendencia,
                                    "current_terminal_responsavel_id_str": term_resp_pendencia
                                    if term_resp_pendencia
                                    else term_id_resp,
                                }
                            )
                        break
                else:
                    continue
        except grpc.RpcError:
            continue

    if tentativa_guiche >= max_tentativas_guiche - 1:
        with client_rent_status_lock:
            if client_rent_status[cliente_id_unico]["status"] not in [
                "CONCLUIDO_DIRETO",
                "CONCLUIDO_POR_CALLBACK",
                "AGUARDANDO_CALLBACK",
            ]:
                print(
                    f"[CLIENTE {cliente_id_unico}] [ALUGUEL] FALHA. Não foi possível alugar '{classe_solicitada}' após {max_tentativas_guiche} tentativas."
                )
                client_rent_status[cliente_id_unico][
                    "status"
                ] = "FALHA_ALUGUEL"

    aguardando_resolucao_pendencia = False
    req_id_para_checar = None
    terminal_para_checar_id_str = None

    with client_rent_status_lock:
        cs = client_rent_status.get(cliente_id_unico, {})
        if cs.get("status") == "AGUARDANDO_CALLBACK":
            aguardando_resolucao_pendencia = True
            req_id_para_checar = cs.get("current_request_id")
            terminal_para_checar_id_str = cs.get(
                "current_terminal_responsavel_id_str"
            )

    if aguardando_resolucao_pendencia:
        tempo_total_espera = 0
        intervalo_check_pending = 20
        max_espera_total = 120

        while tempo_total_espera < max_espera_total:
            with client_rent_status_lock:
                cs_loop = client_rent_status[cliente_id_unico]
                if cs_loop["status"] == "CONCLUIDO_POR_CALLBACK":
                    veiculo_alugado_info = (
                        cs_loop["veiculo"],
                        cs_loop["classe"],
                        "TerminalCallback",
                    )
                    print(
                        f"[CLIENTE {cliente_id_unico}] [ALUGUEL] CONCLUÍDO via callback! Veículo: {veiculo_alugado_info[0]}"
                    )
                    break
                req_id_para_checar = cs_loop["current_request_id"]
                terminal_para_checar_id_str = cs_loop[
                    "current_terminal_responsavel_id_str"
                ]

            time.sleep(1)
            tempo_total_espera += 1

            if (
                req_id_para_checar
                and terminal_para_checar_id_str
                and (tempo_total_espera % intervalo_check_pending == 0)
            ):
                terminal_addr_para_checar = _get_address_from_terminal_id_str(
                    terminal_para_checar_id_str
                )
                if terminal_addr_para_checar:
                    try:
                        with grpc.insecure_channel(
                            terminal_addr_para_checar
                        ) as check_channel:
                            check_stub = terminal_pb2_grpc.TerminalStub(
                                check_channel
                            )
                            check_req = terminal_pb2.CheckPendingStatusRequest(
                                request_id=req_id_para_checar,
                                ID_cliente=cliente_id_unico,
                            )
                            check_resp = check_stub.CheckPending(
                                check_req, timeout=7
                            )

                            if check_resp.query_status in [
                                terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.FULFILLED_BY_THIS_TERMINAL,
                                terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.FORWARDED_AND_FULFILLED_ELSEWHERE,
                            ]:
                                print(
                                    f"[CLIENTE {cliente_id_unico}] [ALUGUEL] CONCLUÍDO (via CheckPending)! Veículo: {check_resp.veiculo_alocado}"
                                )
                                veiculo_alugado_info = (
                                    check_resp.veiculo_alocado,
                                    check_resp.classe_veiculo
                                    or classe_solicitada,
                                    terminal_addr_para_checar,
                                )
                                with client_rent_status_lock:
                                    client_rent_status[cliente_id_unico].update(
                                        {
                                            "status": "CONCLUIDO_POR_CALLBACK",
                                            "veiculo": check_resp.veiculo_alocado,
                                            "classe": check_resp.classe_veiculo
                                            or classe_solicitada,
                                        }
                                    )
                                break
                            elif (
                                check_resp.query_status
                                == terminal_pb2.CheckPendingStatusResponse.PendingQueryStatus.REQUEST_UNKNOWN
                            ):
                                with client_rent_status_lock:
                                    client_rent_status[cliente_id_unico][
                                        "status"
                                    ] = "TIMEOUT_CALLBACK"
                                break
                            elif (
                                check_resp.terminal_atual_responsavel_id_str
                                and check_resp.terminal_atual_responsavel_id_str
                                != terminal_para_checar_id_str
                            ):
                                terminal_para_checar_id_str = (
                                    check_resp.terminal_atual_responsavel_id_str
                                )
                                with client_rent_status_lock:
                                    client_rent_status[cliente_id_unico][
                                        "current_terminal_responsavel_id_str"
                                    ] = terminal_para_checar_id_str
                    except grpc.RpcError:
                        pass
                    except Exception:
                        pass
                else:
                    with client_rent_status_lock:
                        client_rent_status[cliente_id_unico][
                            "status"
                        ] = "TIMEOUT_CALLBACK"
                    break

        with client_rent_status_lock:
            if client_rent_status[cliente_id_unico]["status"] == "AGUARDANDO_CALLBACK":
                print(
                    f"[CLIENTE {cliente_id_unico}] [ALUGUEL] TIMEOUT esperando resolução para '{classe_solicitada}'."
                )
                client_rent_status[cliente_id_unico][
                    "status"
                ] = "TIMEOUT_CALLBACK"

    if veiculo_alugado_info:
        nome_veiculo_devolver, classe_veiculo_devolver, _ = veiculo_alugado_info
        tempo_uso = random.randint(3, 7)
        time.sleep(tempo_uso)
        print(
            f"[CLIENTE {cliente_id_unico}] [DEVOLUÇÃO] Iniciando devolução do veículo {nome_veiculo_devolver}..."
        )
        devolucao_concluida = False
        max_tentativas_devolucao = len(ALL_TERMINAL_ADDRESSES) + 2

        for tentativa_devolucao in range(max_tentativas_devolucao):
            terminal_devolucao_address = None
            ts_guiche_req_dev = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _log_to_file(
                f"Requisição enviada ao guichê de informações em {ts_guiche_req_dev}"
            )
            try:
                with grpc.insecure_channel(INFO_ADDRESS) as ch:
                    stub = guiche_info_pb2_grpc.InformationStub(ch)
                    resp = stub.TerminalOnLine(
                        guiche_info_pb2.Empty(), timeout=5
                    )
                    terminal_devolucao_address = resp.message
                ts_guiche_resp_dev = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                term_id_guiche_dev = _get_terminal_id_from_address(
                    terminal_devolucao_address
                )
                _log_to_file(
                    f"Resposta recebida do guichê de informações em {ts_guiche_resp_dev} termina disponível: {term_id_guiche_dev}"
                )
            except grpc.RpcError:
                time.sleep(random.uniform(1, 2))
                continue

            if not terminal_devolucao_address:
                print(
                    f"[CLIENTE {cliente_id_unico}] [DEVOLUÇÃO] Nenhum terminal ativo para devolução. Tentando guichê..."
                )
                time.sleep(random.uniform(2, 3))
                continue

            ts_term_req_dev = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            term_id_req_dev = _get_terminal_id_from_address(
                terminal_devolucao_address
            )
            _log_to_file(
                f"Requisição enviada ao {term_id_req_dev} para classe {classe_veiculo_devolver} em {ts_term_req_dev}"
            )
            try:
                with grpc.insecure_channel(
                    terminal_devolucao_address
                ) as ch_dev:
                    stub_dev = terminal_pb2_grpc.TerminalStub(ch_dev)
                    req_dev = terminal_pb2.ReturnCarRequest(
                        ID_cliente=cliente_id_unico,
                        Nome_veiculo=nome_veiculo_devolver,
                        Classe_veiculo=classe_veiculo_devolver,
                    )
                    resp_dev = stub_dev.ReturnACar(req_dev, timeout=12)
                    ts_term_resp_dev = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    term_id_resp_dev = _get_terminal_id_from_address(
                        terminal_devolucao_address
                    )

                    if resp_dev.success:
                        _log_to_file(
                            f"Resposta recebida de {term_id_resp_dev}: CONCLUIDO {nome_veiculo_devolver} em {ts_term_resp_dev}"
                        )
                        print(
                            f"[CLIENTE {cliente_id_unico}] [DEVOLUÇÃO] Devolução de {nome_veiculo_devolver} CONCLUÍDA no {term_id_resp_dev}."
                        )
                        devolucao_concluida = True
                        consultar_disponibilidade_terminais(
                            origem_da_chamada=f"CLIENTE_{cliente_id_unico}_POS_DEVOLUCAO"
                        )
                        break
                    else:
                        pass
            except grpc.RpcError:
                pass
            except Exception:
                pass

            if not devolucao_concluida:
                time.sleep(random.uniform(0.5, 1.5))

        if not devolucao_concluida:
            print(
                f"[CLIENTE {cliente_id_unico}] [DEVOLUÇÃO] FALHA. Não foi possível devolver {nome_veiculo_devolver}."
            )

    status_final_aluguel_dict = {}
    with client_rent_status_lock:
        status_final_aluguel_dict = client_rent_status.get(
            cliente_id_unico, {}
        ).copy()
    final_status_str = status_final_aluguel_dict.get("status", "DESCONHECIDO")

    if final_status_str in ["CONCLUIDO_DIRETO", "CONCLUIDO_POR_CALLBACK"]:
        print(
            f"<< [CLIENTE {cliente_id_unico}] Finalizou. Status Aluguel: SUCESSO >>"
        )
    elif final_status_str in ["AGUARDANDO_CALLBACK", "TIMEOUT_CALLBACK"]:
        print(
            f"<< [CLIENTE {cliente_id_unico}] Finalizou. Status Aluguel: PENDÊNCIA NÃO RESOLVIDA ({final_status_str}) >>"
        )
    else:
        print(
            f"<< [CLIENTE {cliente_id_unico}] Finalizou. Status Aluguel: FALHA ({final_status_str}) >>"
        )


def main():
    num_threads_max = 5
    print(f"[INFO] Iniciando script principal do cliente.")

    consultar_disponibilidade_terminais(
        origem_da_chamada="INICIO_SCRIPT_CLIENTE"
    )

    try:
        with open("carros_solicitados.txt", "r") as f:
            linhas_solicitacoes = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("[ERRO FATAL] Arquivo carros_solicitados.txt não encontrado.")
        return
    except Exception as e:
        print(f"[ERRO FATAL] Ao ler carros_solicitados.txt: {e}")
        return

    if not linhas_solicitacoes:
        print("[AVISO] Arquivo carros_solicitados.txt está vazio.")
        return

    if not os.path.exists(LOGS_DIR_CLIENTES):
        try:
            os.makedirs(LOGS_DIR_CLIENTES)
            print(
                f"[INFO] Diretório de logs de clientes '{LOGS_DIR_CLIENTES}' criado."
            )
        except OSError:
            print(
                f"[AVISO] Falha ao criar diretório de logs de clientes. Logs individuais não serão salvos."
            )
            pass

    print(
        f"\n[INFO] Processando {len(linhas_solicitacoes)} requisições de clientes com até {num_threads_max} threads simultâneas."
    )

    with ThreadPool(processes=num_threads_max) as pool:
        resultados_async = [
            pool.apply_async(
                cliente_tarefa,
                (
                    classe_requisitada,
                    nomes_clientes[i % len(nomes_clientes)],
                    i,
                ),
            )
            for i, classe_requisitada in enumerate(linhas_solicitacoes)
        ]
        for i, res_async in enumerate(resultados_async):
            try:
                res_async.get()
            except Exception as exc:
                print(
                    f"[ERRO THREADPOOL] Cliente {i} (solicitando {linhas_solicitacoes[i]}) gerou exceção: {exc}"
                )

    print("\n[INFO] Todas as tarefas de cliente foram processadas.")

    consultar_disponibilidade_terminais(
        origem_da_chamada="FIM_SCRIPT_CLIENTE"
    )

    time.sleep(3)
    print("[INFO] Encerrando script principal do cliente.")


if __name__ == "__main__":
    main()