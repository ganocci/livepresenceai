// LivePresenceAI - Configuração central do app
// Ao rodar em outra máquina, basta trocar o host aqui (ex.: 192.168.0.15).

const String apiHost = '127.0.0.1';
const int apiPort = 8000;

const String apiBaseUrl = 'http://$apiHost:$apiPort';
const String wsBaseUrl = 'ws://$apiHost:$apiPort';
