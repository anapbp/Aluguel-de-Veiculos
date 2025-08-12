# ALUNA: ANA PAULA BARBOSA PEREIRA


# Sistema de Aluguel de Veículos

Este projeto simula um sistema distribuído de aluguel de veículos, implementado em Python utilizando gRPC para comunicação entre os componentes. O sistema é composto por Clientes, Terminais de Aluguel, um Guichê de Informações, um Servidor de Backup e um Servidor de Heartbeat.




## Como Executar:

1.  **Compile os arquivos `.proto`:**
    ```bash
    python3 -m grpc_tools.protoc -I protos --python_out=. --grpc_python_out=. protos/guiche_info.proto protos/terminal.proto protos/client.proto protos/heartbeat.proto protos/backup.proto
    ```
2.  **Inicie os Servidores (em terminais separados):**
    ```bash
    python heartbeat.py
    python backup.py
    python terminal.py 1
    python terminal.py 2
    python terminal.py 3
    python guiche.py
    ```
3.  **Prepare o arquivo `carros_solicitados.txt`:**
    Crie este arquivo na mesma pasta do `cliente.py` com uma classe de veículo desejada por linha. Exemplo:
    ```
    Economicos
    Minivan
    SUV
    Economicos
    ```
4.  **Execute o script do Cliente:**
    ```bash
    python client.py
    ```

4.  **Executando novamente:**
    Caso for executar novamente, utilizar o comando abaixo para apagar os arquivos gerados na execução passada:
    ```bash
    python limpar_logs.py
    ```

    A seguir, refazer os passos 2 em diante novamente.




## Sistema de Aluguel e Devolução

1.  Um cliente deseja alugar um veículo de uma classe específica.
2.  O cliente contata o Guichê de Informações para obter o endereço de um terminal ativo.
3.  O cliente envia uma requisição de aluguel (`RentACar`) para o terminal obtido.
    *   Se o terminal gerencia a classe e tem veículos disponíveis:
        *   O terminal aluga o veículo.
        *   Registra a transação como "CONCLUIDA" no Backup.
        *   Responde ao cliente com os detalhes do veículo.
    *   Se o terminal não gerencia a classe:
        *   Encaminha a requisição para o terminal responsável pela classe. A resposta do terminal de destino é repassada ao cliente.
    *   Se o terminal gerencia a classe, mas não tem veículos disponíveis:
        *   A requisição do cliente é colocada em uma fila de pendências local.
        *   A pendência é registrada no Servidor de Backup (com status "PENDENTE" e dados do cliente para callback).
        *   O cliente é informado que sua solicitação está pendente.
4.  O cliente aguarda. Se sua solicitação estava pendente, ele pode receber um callback quando um veículo estiver disponível ou pode proativamente consultar o status da sua pendência (`CheckPending`).
5.  Após o uso, o cliente devolve o veículo (`ReturnACar`) a qualquer terminal ativo (obtido novamente via Guichê).
    *   O terminal que recebe a devolução adiciona o veículo à sua frota disponível para aquela classe.
    *   Registra a transação como "DEVOLUCAO_CONCLUIDA" no Backup.
    *   Verifica sua fila local de pendências. Se houver um cliente aguardando por aquela classe de veículo, o veículo é alocado para ele, o Backup é notificado para remover a pendência, e o cliente pendente é contatado via callback.




## Componentes Principais

1.  **Cliente (`cliente.py`):**
    *   Solicita informações ao Guichê para encontrar um terminal ativo.
    *   Tenta alugar um veículo de uma classe específica no terminal indicado.
    *   Se o aluguel for bem-sucedido, utiliza o veículo por um tempo aleatório e depois o devolve.
    *   Se o aluguel ficar pendente, o terminal atua como cliente e busca um terminal ativo que contenha a classe desejada e faz a requisição.

2.  **Terminal (`terminal.py`):**
    *   Gerencia um conjunto inicial de classes de veículos.
    *   Processa requisições de aluguel e devolução.
    *   Encaminha requisições para outros terminais se não gerenciar a classe solicitada.
    *   Mantém uma fila local de clientes com requisições pendentes.
    *   Registra todas as transações (aluguéis, devoluções, pendências) no Servidor de Backup.
    *   Envia heartbeats para o Servidor de Heartbeat.
    *   Pode aceitar a devolução de qualquer veículo, independentemente da classe que gerencia inicialmente. Como pode aceitar a devolução de qualquer veículo, passa a ter o veículo devolvido em seu inventário para alugar a outro cliente. Ou seja, a distribuição inicial de veículos vai mudando com o passar do tempo.

3.  **Servidor de Backup (`backup.py`):**
    *   Recebe e armazena logs de todas as transações dos terminais em `Backup.txt`.
    *   Permite que terminais consultem pendências.
    *   Envia heartbeats para o Servidor de Heartbeat.

4.  **Guichê de Informações (`guiche.py`):**
    *   Fornece aos clientes o endereço de um terminal de aluguel ativo.
    *   Utiliza o Servidor de Heartbeat para determinar quais terminais estão online (implementação comum é round-robin entre ativos).

5.  **Servidor de Heartbeat (`heartbeat.py`):**
    *   Recebe heartbeats dos Terminais e do Servidor de Backup.
    *   Mantém uma lista de serviços ativos, que é consultada pelo Guichê.




## Principais Informações Sobre a Implementação:

### 1. Distribuição Inicial e Dinâmica de Veículos

*   **Inicialização:** Cada terminal é configurado para gerenciar diretamente um conjunto específico de classes de veículos e começa com uma frota inicial definida (`INITIAL_VEHICLES` e `CLASS_MANAGEMENT_MAP` em `terminal.py`).
*   **Devoluções Dinâmicas:** Uma característica chave é que um cliente pode devolver um veículo de **qualquer classe** a **qualquer terminal ativo**. O terminal que recebe a devolução adiciona esse veículo à sua própria lista de veículos disponíveis para a respectiva classe, mesmo que não seja uma classe que ele gerenciava inicialmente. Isso significa que, com o tempo, a distribuição de veículos entre os terminais pode se tornar dinâmica e diferir da configuração inicial.


### 2. Fila de Requisições Pendentes e Persistência

*   **Criação da Pendência:** Quando um cliente solicita um veículo de uma classe que o terminal contatado gerencia, mas não há unidades disponíveis, o terminal:
    1.  Adiciona o cliente à sua fila de pendências interna (em memória).
    2.  Envia uma requisição ao Servidor de Backup para registrar essa pendência. Esta requisição inclui o ID do cliente, classe desejada, informações de contato do cliente (IP/Porta para callback) e um ID único para a pendência.
*   **Persistência no Backup:** O Servidor de Backup armazena os detalhes de todas as pendências ativas no sistema no arquivo `pending_requests.json`.
    *   **Importância:** Se um terminal específico falhar, suas pendências em memória seriam perdidas. No entanto, como elas também foram registradas no `pending_requests.json` do Servidor de Backup, a informação sobre quais clientes estão esperando e por quais classes de veículos **não é perdida**. O sistema como um todo mantém o conhecimento dessas pendências.
*   **Resolução da Pendência:**
    1.  Quando um veículo é devolvido a um terminal, este verifica sua fila de pendências local.
    2.  Se um cliente estiver esperando por aquela classe, o veículo é alocado.
    3.  O terminal então notifica o Servidor de Backup que a pendência específica foi resolvida (enviando uma transação "CONCLUIDA" com o ID da pendência original). O Backup remove a entrada correspondente de `pending_requests.json`.
    4.  O terminal contata o cliente via callback para informar que o veículo está disponível.


### 3. Comunicação Cliente-Terminal (Callbacks e Consultas)

*   **Callbacks:** Quando uma requisição pendente de um cliente pode ser atendida, o terminal responsável envia uma mensagem de callback diretamente para o cliente (que está executando um pequeno servidor gRPC para isso).


### 4. Sobre "PENDÊNCIA NÃO RESOLVIDA (TIMEOUT_CALLBACK)"

Eventualmente, alguns clientes podem finalizar com o status "PENDÊNCIA NÃO RESOLVIDA (TIMEOUT_CALLBACK)". Isso ocorre devido a uma combinação de fatores inerentes à simulação e à lógica de espera do cliente:

*   **Disponibilidade Limitada de Veículos:** O sistema possui um número finito de veículos. Se muitos clientes solicitarem a mesma classe de veículo e não houver devoluções suficientes dessa classe em tempo hábil, alguns clientes permanecerão na fila de pendências.
*   **Tempo de Espera do Cliente:** O `cliente.py` implementa um tempo máximo de espera (`max_espera_total`) para a resolução de uma pendência. Se um veículo não se tornar disponível para aquele cliente dentro desse período, o cliente desiste e registra um timeout.
*   **Dinâmica das Devoluções:** A disponibilidade de veículos para clientes pendentes depende inteiramente de outros clientes devolverem veículos da classe desejada. Se as devoluções forem lentas ou para classes diferentes das que estão em alta demanda, as filas de pendência não diminuirão rapidamente.
*   **Ordem na Fila:** Os terminais atendem as pendências, em geral, na ordem em que foram registradas (FIFO - First-In, First-Out) para uma determinada classe. Clientes que entraram na fila mais tarde para uma classe muito requisitada têm maior probabilidade de enfrentar um timeout se a oferta não aumentar.
*   **Fim da Simulação:** Se a simulação (execução do `cliente.py`) terminar enquanto alguns clientes ainda estão em estado de "AGUARDANDO_CALLBACK" e seu tempo de espera individual não se esgotou, eles podem ser registrados como `TIMEOUT_CALLBACK` ao final do processo principal do cliente, pois a simulação não continuará indefinidamente para resolver todas as pendências.
