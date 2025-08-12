compile:
	python3 -m grpc_tools.protoc -I protos --python_out=. --grpc_python_out=. protos/guiche_info.proto protos/terminal.proto protos/client.proto protos/heartbeat.proto protos/backup.proto