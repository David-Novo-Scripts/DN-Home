Quero criar no meu Raspberry Pi 5 um projeto chamado `DN_Home`.

O objetivo é construir um assistente doméstico pessoal estilo “Jarvis”, modular, local-first, extensível e orientado a eventos.

Não quero apenas uma coleção de automações isoladas. Quero criar uma base sólida que, progressivamente, consiga perceber o estado da casa, reagir a sensores, controlar dispositivos, falar comigo de forma natural, ouvir comandos em português de Portugal e, futuramente, usar um chat dedicado do ChatGPT como camada conversacional/inteligente.

========================
1. PRINCÍPIOS DO PROJETO
========================

O Raspberry Pi 5 será o controlador central.

Quero separar claramente:

1. Automação local
2. Estado da casa
3. Sensores
4. Dispositivos
5. Voz
6. Skills
7. Inteligência/conversa
8. Integrações externas

REGRA FUNDAMENTAL:

Funções básicas da casa NÃO devem depender do ChatGPT.

Exemplo:

porta abre
→ sistema determina que estou a chegar
→ luz acende

Isto deve funcionar mesmo que:
- não haja Internet;
- o ChatGPT esteja indisponível;
- Chromium tenha perdido sessão;
- um serviço TTS online esteja indisponível.

O ChatGPT será futuramente uma camada de interpretação, conversa e raciocínio, não o controlador fundamental da casa.

Quero evitar dependências desnecessárias e vendor lock-in.

========================
2. RESTRIÇÕES IMPORTANTES
========================

- Não usar OpenAI API paga.
- Não usar outras APIs pagas sem eu autorizar.
- Tenho ChatGPT Plus.
- Futuramente quero experimentar integração com ChatGPT através de Chromium/Playwright e da minha sessão normal.
- O login no ChatGPT será SEMPRE feito manualmente por mim.
- Não tentar contornar autenticação, CAPTCHA, proteção anti-bot ou mecanismos de segurança.
- Não guardar passwords.
- Não extrair cookies para sistemas externos.
- Não alterar configurações de rede do Raspberry Pi.
- Não configurar router.
- Não configurar NAT.
- Não configurar DHCP.
- Não criar hotspot.
- Não interferir com WireGuard/Tailscale/VPN/rede existente.
- Não instalar Home Assistant nesta fase.
- Não fazer alterações destrutivas.
- Antes de instalar pacotes de sistema ou alterar serviços/configuração do sistema, mostrar-me primeiro o plano e pedir aprovação.
- Não ativar serviços systemd automaticamente sem autorização.
- Nunca hardcodear passwords, tokens, IPs, nomes de dispositivos ou chaves API.
- Segredos devem ficar em `.env`.
- Configurações normais devem ficar em YAML/TOML ou equivalente.
- Código Python modular e fácil de manter.
- O sistema deve poder crescer sem ser necessário reescrever tudo.

========================
2.1. REDE ATUAL E FUTURA
========================

A rede atual 192.168.0.0/24 é temporária.

Neste momento:

- Raspberry Pi: 192.168.0.23
- Google Nest: 192.168.0.25

Futuramente é provável que a box/router upstream fique em modo bridge e que o
Raspberry Pi 5 volte a assumir funções de router/gateway de uma LAN própria,
provavelmente 192.168.50.0/24.

Isto é apenas contexto arquitetural. Não alterar nem preparar agora a
configuração de rede para esse cenário futuro.

A implementação deve:

- não hardcodear 192.168.0.23;
- não hardcodear 192.168.0.25;
- não hardcodear 192.168.0.0/24;
- não hardcodear 192.168.50.0/24;
- não assumir que eth0 será sempre a interface LAN;
- distinguir conceptualmente LAN, WAN e VPN;
- permitir configuração explícita da interface/IP LAN;
- preferencialmente determinar o endereço local apropriado através da rota
  para o dispositivo alvo;
- permitir futura mudança de subnet apenas por configuração, sem alterar
  código;
- continuar a permitir IP conhecido como configuração/fallback quando mDNS
  não estiver disponível.

IMPORTANTE:

Não alterar agora qualquer configuração de rede.

Não configurar:

- bridge;
- NAT;
- DHCP;
- routing;
- firewall;
- Avahi;
- Tailscale;
- WireGuard;
- interfaces de rede.

========================
3. HARDWARE ATUAL
========================

Atualmente tenho:

- Raspberry Pi 5.
- Google Home/Nest pequeno, cinzento e redondo, já com alguns anos.
- Provavelmente Google Home Mini ou Nest Mini.
- iPhone.
- SwitchBot Contact Sensor instalado e disponível para PoC BLE local.
- Nanoleaf Essentials A19, família NL45, HomeKit/Thread non-Matter.
- Shelly física com AP local acessível em `192.168.33.1`, modelo e geração
  ainda por identificar através da API local read-only.
- Uma lâmpada normal no quarto que futuramente poderá ser substituída por lâmpada RGB inteligente.
- Um downlight/spot LED encastrado no teto, preso por molas, que futuramente poderá ser substituído por um downlight RGB inteligente compatível.
- Futuramente poderá existir um leitor NFC PN532 ou semelhante.
- Futuramente haverá provavelmente um microfone USB.
- Futuramente podem existir BLE tags/beacons nas chaves ou outros objetos.

========================
4. CARTÃO DA RESIDÊNCIA
========================

Tenho um cartão de acesso da residência.

Já foi identificado como:

- MIFARE Classic 1K
- 13.56 MHz
- ISO14443A

NÃO quero:
- clonar o cartão;
- emular o cartão;
- modificar as credenciais;
- descobrir chaves de autenticação;
- interferir com o sistema de controlo de acessos.

Quero apenas usar um leitor NFC como sensor de presença.

Objetivo:

Criar uma pequena “base”/dock para pousar o cartão quando chego a casa.

O Raspberry Pi precisa apenas de saber algo como:

residence_card.present_on_dock = true/false

Opcionalmente:
- comparar o UID com o UID esperado apenas para confirmar que é o cartão correto.

Exemplo:

chego a casa
→ porta abre
→ sistema identifica chegada
→ espero 2 minutos
→ cartão ainda não está na base
→ Nest diz:

“David, não te esqueças de colocar o cartão da residência no sítio.”

Quando sair:

porta abre
→ sistema identifica saída
→ cartão continua pousado na base
→ Nest:

“David, espera. Estás a esquecer-te do cartão da residência.”

========================
5. CHAVES / BLE
========================

Futuramente quero experimentar BLE tags/beacons nas chaves.

Objetivo:

keys.present = true/false
keys.last_seen
keys.rssi
keys.last_motion, caso exista sensor de movimento

Quero evitar depender apenas de RSSI como prova absoluta de localização.

Se necessário futuramente poderão existir vários pontos BLE/ESP32 para melhorar localização.

Exemplo:

saída detetada
→ cartão comigo
→ chaves ficaram no quarto
→ Nest:

“Espera, David. As tuas chaves ficaram no quarto.”

Se não estiver nada esquecido:

“Até logo, David. Tem um bom dia.”

========================
6. SWITCHBOT CONTACT SENSOR
========================

Tenho um SwitchBot Contact Sensor instalado.

Quero, se possível, comunicar diretamente com ele através de BLE a partir do Raspberry Pi, sem comprar SwitchBot Hub.

Quero obter, se tecnicamente disponível:

- porta aberta/fechada;
- movimento;
- bateria;
- timestamps.

Exemplo de eventos:

door.opened
door.closed
door.motion_detected

O sensor foi identificado como `WoContact`, firmware v2.0. O advertising normal
foi comprovado no `hci0` do Raspberry Pi 5, independentemente do iPhone, com
manufacturer `0x0969`, service data `FD3D` e device type `d`/`0x64`. O Pair Mode
usa `D`/`0x44` e deve ser apenas diagnóstico. A automação principal não depende
de GATT, password, pairing, bonding, cloud ou SwitchBot Hub.

A integração local deve usar active scan Bleak, filtrar o endereço configurado
e decodificar deterministicamente o Service Data segundo a BLE Open API oficial
da SwitchBot. O parser deve expor porta (`closed`, `open`, `timeout`), PIR,
luminosidade, bateria, tempos desde PIR/Hall e contadores de entrada, saída e
botão. O MAC e o adapter BlueZ pertencem à configuração local e nunca devem ser
hardcoded no código.

Advertisements repetidos sem alteração atualizam `last_seen` e RSSI sem gerar
eventos duplicados. Transições reais devem produzir `door.opened`,
`door.closed`, `door.left_open`, `door.motion_detected`, `door.light_changed`,
`door.sensor_seen` e `door.sensor_lost`. O limiar de stale/lost deve ser
configurável para acomodar a cadência observada sem mascarar indisponibilidade
real. Raw HCI fica reservado a diagnóstico; não é o backend normal do projeto.

========================
7. ESTADO CENTRAL DA CASA
========================

Quero um sistema central de estado.

Exemplo conceptual:

house:
  mode: normal/night/away/sleep

resident:
  home: true/false
  identity: DAVID_CONFIRMED/UNKNOWN
  presence_confidence:
  presence_evidence:
  last_arrival:
  last_departure:

entry:
  classification: DAVID_CONFIRMED/EXPECTED_VISITOR/UNKNOWN/UNEXPECTED_ENTRY
  incident_id:

visits:
  active:
  next_scheduled:

desktop:
  state: OFFLINE/WAKING/ONLINE

security:
  incident: OPEN/ACKNOWLEDGED/CLOSED
  recorder: UNKNOWN/STARTING/READY/FAILED

door:
  state: open/closed
  last_changed:

occupancy:
  present: true/false
  last_motion:

residence_card:
  present_on_dock: true/false
  last_seen:

keys:
  present: true/false
  last_seen:
  rssi:

lights:
  bedroom:
    state:
    brightness:
    color:
    temperature:

phone:
  connected:
  incoming_call:
  caller:

voice:
  listening:
  speaking:
  last_spoken:

transit:
  destination:
  next_departure:

briefing:
  available:
  played_today:
  generated_at:

O formato real pode ser melhorado se houver uma arquitetura mais apropriada.

Quero evitar estado espalhado por dezenas de módulos.

========================
8. EVENT BUS
========================

Preferencialmente quero arquitetura event-driven.

Exemplo:

door.opened

→ automation engine recebe evento

→ verifica estado atual

→ determina arrival/departure

→ executa ações.

Eventos futuros:

door.opened
door.closed
door.left_open
door.motion_detected
door.light_changed
door.sensor_seen
door.sensor_lost
motion.detected
resident.arrived
resident.departed
card.present
card.absent
keys.present
keys.absent
phone.incoming_call
briefing.ready
wakeword.detected
transit.updated
presence.device_seen
presence.device_lost
presence.resident_confirmed
visit.scheduled
visit.started
visit.completed
visit.expired
visit.cancelled
security.unexpected_entry
desktop.wake_requested
desktop.online
desktop.wake_failed
security.recorder_ready
security.recorder_failed

Eventos relacionados com uma mesma abertura, decisão ou incidente devem poder
transportar metadados de correlação, como `incident_id`, timestamp, origem e
identificador do evento inicial. Isto permite auditoria, deduplicação e
idempotência sem acoplar sensores diretamente às ações.

Pode existir um EventBus simples interno em Python.

Não quero adicionar Kafka, Redis ou infraestrutura pesada sem necessidade.

========================
9. SKILLS
========================

Quero que funcionalidades futuras possam ser adicionadas através de um conceito de skills.

Estrutura conceptual:

skills/
├── lights/
├── transit/
├── weather/
├── reminders/
├── phone/
├── briefing/
├── card/
├── keys/
├── presence/
├── visits/
├── security/
└── conversation/

Uma skill deve poder:

- declarar comandos/intents suportados;
- consultar estado;
- executar ações autorizadas;
- devolver texto para falar;
- falhar de forma controlada.

Exemplos:

“Jarvis, liga a luz.”

→ lights skill

“Jarvis, quanto falta para o comboio para Paris?”

→ transit skill

“Jarvis, onde estão as minhas chaves?”

→ keys skill

“Jarvis, quero ouvir o briefing.”

→ briefing skill

========================
10. ILUMINAÇÃO
========================

Quero futuramente controlar:

- lâmpada RGB do quarto;
- downlight RGB do teto;
- Nanoleaf, se for possível integrá-la localmente.

A Nanoleaf existente foi identificada passivamente como Essentials A19,
família NL45, HomeKit/Thread non-Matter. Qualquer integração deve respeitar o
emparelhamento existente. Não assumir suporte à Nanoleaf HTTP OpenAPI, nem
fazer reset, novo pairing ou alteração de estado sem validação e aprovação
explícitas.

A Shelly deverá ser integrada, depois de identificado o modelo e a geração,
através da API local correspondente e de abstrações como `ShellyDevice`,
`ShellySwitch` e `ShellyProvider`. Host, provider e switch/component ID devem
ser configuração, nunca hardcoded. `status()` é read-only; `turn_on()` e
`turn_off()` exigem autorização antes do primeiro teste físico.

Quero abstrair fabricantes.

Não quero que automações dependam diretamente de Tapo/Nanoleaf/etc.

Exemplo:

lights.set(
    zone="bedroom",
    brightness=40,
    temperature="warm"
)

e o driver específico trata do fabricante.

Comportamento desejado:

Chegada durante o dia:
→ luz aproximadamente 60%

Chegada à noite:
→ luz quente e fraca

Uma futura automação de entrada pode combinar porta, PIR, luminosidade,
presença BLE/iPhone/Amazfit, NFC e contexto temporal antes de atuar sobre
Shelly e/ou Nanoleaf. Fechar a porta, isoladamente, nunca implica desligar a
luz.

Exemplo:
23:30
→ warm
→ 15%

Possibilidades futuras:
- cenas;
- RGB;
- transições suaves;
- sunrise;
- movie mode;
- sleep mode.

========================
11. GOOGLE NEST / GOOGLE CAST
========================

Quero usar o Google Home/Nest como principal saída de áudio.

O Raspberry Pi deve conseguir:

texto
→ TTS
→ ficheiro/stream de áudio
→ Google Cast
→ Nest

Quero uma abstração tipo:

speaker.speak("Bem-vindo a casa, David.")

O módulo de TTS deve estar separado do módulo Google Cast.

Por exemplo:

TTS engine
→ audio file

Nest driver
→ play audio file

Assim posso trocar o TTS no futuro sem alterar a parte Cast.

O áudio temporário deverá ser apagado automaticamente depois de já não ser necessário.

========================
11.1. SERVIDOR HTTP TEMPORÁRIO
========================

O servidor HTTP usado para entregar áudio ao Nest:

- nunca deve fazer bind a 0.0.0.0;
- deve fazer bind apenas ao endereço local selecionado para a rede do Nest;
- não deve anunciar Tailscale, WireGuard, VPN ou WAN;
- deve usar uma porta TCP dedicada e configurável, inicialmente 8765;
- não deve usar uma porta efémera aleatória para a entrega normal de áudio;
- a porta não deve estar hardcoded no código e deve poder mudar apenas por
  configuração;
- deve servir apenas o ficheiro temporário daquela reprodução;
- deve usar URL/token aleatório não previsível;
- não deve permitir directory listing;
- deve expirar após reprodução ou timeout;
- deve fechar e limpar ficheiros/recursos mesmo em caso de erro.
- deve permitir a reutilização normal da porta configurada com SO_REUSEADDR,
  sem usar SO_REUSEPORT;
- deve executar shutdown e server_close explícitos e aguardar o fim da thread
  de serviço antes de devolver controlo;
- não deve permitir dois servidores DN_Home simultâneos na mesma porta.

Numa evolução futura para um processo DN_Home residente, poderá existir um
servidor HTTP persistente na porta configurada. Mesmo nesse modelo, cada media
asset deve continuar acessível apenas através de URL/token temporário, expirar
depois de usado ou por timeout e ser eliminado com segurança. Frases TTS
estáticas e não sensíveis, como greetings, poderão ser cacheadas; conteúdo
dinâmico ou sensível não deve ser guardado nessa cache.

Se for necessária uma regra de firewall para esta entrega, deve seguir o
princípio de menor privilégio: limitar interface, IP de origem do dispositivo
Cast, IP de destino local, protocolo TCP e porta DN_Home configurada. Não abrir
intervalos grandes de portas nem permitir genericamente todo o tráfego vindo
do dispositivo. Qualquer alteração de firewall continua a exigir aprovação
explícita antes de ser aplicada.

========================
11.2. GOOGLE CAST / REDE
========================

Antes de reproduzir:

- determinar qual endereço local deve ser anunciado ao Nest;
- registar em debug qual interface/rota foi escolhida;
- não depender de mDNS para funcionar;
- poder usar endereço conhecido/configurado como fallback.

========================
11.3. VOLUME
========================

O volume do Nest deve poder ser definido através da configuração e da CLI.

O restauro do volume anterior do Nest depois da reprodução deve ser
configurável e não obrigatório.

Por omissão, `speaker.manage_volume` deve ser false. Nesse modo, uma execução
sem `--volume` não deve chamar `set_volume`, não deve restaurar volume e deve
preservar integralmente o volume físico atual do Nest. Um `--volume` explícito
continua autorizado a alterar o volume Cast. O comportamento automático
anterior pode ser ativado com `speaker.manage_volume: true`, usando então
`speaker.volume` quando a CLI não indicar um valor.

Só deve existir tentativa de restauro quando esta execução tiver efetivamente
alterado o volume físico do Nest.

========================
12. TEXT TO SPEECH
========================

Quero uma voz muito natural.

Objetivo:
não quero uma voz robótica tipo GPS antigo.

Preferência:
Português de Portugal.

Quero experimentar soluções gratuitas.

Inicialmente podem ser testadas:
- Edge TTS;
- Piper;
- outras opções gratuitas adequadas.

Mas criar uma interface comum:

TTSEngine

Exemplo:

tts.generate(
    text,
    voice,
    style
)

Quero conseguir listar vozes:

python -m dn_home voices

E testar:

python -m dn_home speak --voice <voice> "Olá David. Esta é a voz da tua casa."

Quero poder mudar facilmente a voz global da casa.

A arquitetura de TTS deve suportar:

- um motor principal configurável;
- um ou mais motores de fallback ordenados e configuráveis;
- adaptadores locais, online ou executados remotamente noutro host da LAN;
- timeouts, health checks e falha controlada por adaptador;
- seleção de idioma/voz por mensagem quando uma automação o exigir;
- uma representação comum do áudio gerado, independente do destino de
  reprodução.

O motor de voz premium definitivo ainda não está escolhido. O Edge TTS pode
continuar como fallback atual enquanto essa escolha não estiver concluída.
Falhar ou trocar de motor não deve exigir alterações no módulo Google Cast.

`TTSEngine` não deve conhecer o Google Nest, URLs Cast nem detalhes do servidor
HTTP. Deve apenas transformar texto e parâmetros de voz num media asset ou
stream descrito por uma interface comum. O módulo Speaker/Cast recebe esse
resultado e trata separadamente da entrega e reprodução.

Um motor TTS remoto na LAN deve ser tratado como integração configurável, sem
IP ou hostname hardcoded, com timeout e fallback. Texto sensível não deve ser
enviado para motores externos ou remotos sem configuração explícita compatível
com a política de privacidade.

O adaptador Edge TTS deve aceitar prosódia opcional através de configuração e
overrides CLI:

- rate no formato de percentagem com sinal obrigatório, por exemplo +8%;
- pitch no formato Hz com sinal obrigatório, por exemplo -5Hz;
- os defaults devem permanecer neutros: rate +0% e pitch +0Hz.

Os parâmetros CLI `--rate` e `--pitch` devem sobrepor apenas a execução atual e
manter compatibilidade com comandos que não os indiquem. O Edge TTS também
suporta volume de síntese em percentagem. Esse ganho deve ser configurável em
`voice.tts_volume`, com default +0%, e não precisa de override CLI nesta fase.
O volume TTS é distinto do volume Cast do Nest configurado por `--volume`.

A mesma voz deverá futuramente ser usada para:
- boas-vindas;
- alertas;
- briefing;
- chamadas;
- conversa;
- transportes.

========================
13. RECONHECIMENTO DE VOZ
========================

O caminho de voz deve ser local-first, modular e orientado a eventos. A primeira
PoC pode correr em foreground e não requer systemd.

Fluxo:

microfone
→ wake word
→ captura limitada por VAD
→ speech-to-text
→ intent/skill local ou, futuramente, conversa
→ resposta
→ TTS
→ Nest

Wake word:
“Jarvis”

Quero reconhecimento de português, especialmente Português de Portugal.

Devem existir interfaces independentes:

- `AudioInput`/`MicrophoneSource`;
- `WakeWordEngine`;
- `VoiceActivityDetector`;
- `STTEngine`.

O dispositivo ALSA, sample rate, modelo, thresholds, timeouts, cooldown e paths
dos binários/modelos devem ser configuráveis e não hardcoded. Devem existir
diagnósticos sem reprodução:

```
python -m dn_home mic list
python -m dn_home mic test --seconds 5
```

O funcionamento normal não deve manter gravação contínua em disco. Em
`WAIT_WAKE` apenas o motor local de wake word recebe frames e pode existir um
ring buffer pequeno em RAM. Depois de detetar a wake word, o sistema capta uma
única utterance, usa VAD/silêncio e timeouts configuráveis e elimina qualquer
ficheiro temporário depois do STT, incluindo em caso de erro.

Estados mínimos:

```
WAIT_WAKE -> LISTENING -> PROCESSING -> SPEAKING -> COOLDOWN -> WAIT_WAKE
```

Durante `SPEAKING` e `COOLDOWN` não devem ser aceites novas wake words. Isto
evita que o áudio do próprio Nest crie um novo comando. Echo cancellation e
barge-in ficam fora da primeira PoC.

Para wake word, avaliar e medir localmente openWakeWord e alternativas livres
adequadas ao Raspberry Pi. O modelo, incluindo eventual modelo personalizado
para “Jarvis”, deve ser substituível por configuração. Um modelo não deve ser
selecionado apenas por suportar a frase nominalmente: deve ser medido com o
microfone e a voz reais, incluindo falsos positivos e falsos negativos.

Para STT local, avaliar:

- whisper.cpp
- faster-whisper, se apropriado

No Raspberry Pi 5 quero testar pelo menos:

- base
- small
- versões quantizadas quando aplicável

Quero benchmark real.

Criar um conjunto de frases minhas em PT-PT e comparar:

- accuracy;
- latency;
- CPU;
- RAM.

Exemplos:

“Jarvis, acende a luz do quarto a cinquenta por cento.”

“Jarvis, quanto falta para o próximo comboio para Paris?”

“Jarvis, não me deixes esquecer o cartão.”

“Jarvis, como correu o briefing hoje?”

Nomes/palavras frequentes poderão ser usados como contexto:

David
Jarvis
Nanoleaf
SwitchBot
Raspberry Pi
Nomad
RMA
Vítor

O texto transcrito só deve ser incluído em logs quando explicitamente
configurado. Os logs nunca devem conter áudio. A primeira validação end-to-end
deve usar saída no terminal; o caminho TTS/Cast só será ativado depois de
autorização explícita para a primeira reprodução audível.

========================
14. CONVERSAÇÃO
========================

Quero futuramente que a casa seja capaz de conversar comigo de forma natural.

Não apenas comandos.

Exemplo:

chego a casa depois do trabalho

Nest:
“Bem-vindo de volta, David. Como correu o teu dia?”

Eu:
“Foi uma seca, tive imenso trabalho.”

Sistema:
→ transcrição local
→ conversa/inteligência
→ resposta

Nest:
“Parece que foi um dia puxado. Queres deixar as luzes mais baixas e desligar um bocado?”

Quero que isto pareça natural.

Mas quero evitar que o sistema:
- fale constantemente;
- interrompa;
- repita mensagens;
- se torne irritante.

Deve existir conceito de cooldown e contexto.

Exemplo:

não perguntar:
“Como correu o teu dia?”

cinco vezes porque abri a porta cinco vezes.

========================
15. CHATGPT — FUTURO
========================

Tenho ChatGPT Plus.

NÃO quero usar OpenAI API paga para isto.

Futuramente quero experimentar um chat dedicado no ChatGPT chamado algo como:

DN Home Jarvis

A integração experimental poderá usar:

Chromium
+
Playwright

com perfil persistente.

IMPORTANTE:

- eu faço login manualmente;
- não automatizar credenciais;
- não contornar CAPTCHA;
- não tentar furar proteções;
- não guardar password;
- se a interface mudar, falhar de forma segura.

O Raspberry Pi poderá enviar ao chat contexto estruturado.

Exemplo:

[HOUSE_STATE]
time=18:51
event=arrival
door=closed
card_on_dock=false
keys_present=true
lights=off

[USER]
Cheguei.

Possível resposta:

SPEAK:
Bem-vindo de volta, David. Como correu o teu dia?

ACTIONS:
bedroom_light=warm_40

NUNCA executar ações devolvidas pelo ChatGPT diretamente.

As ações precisam:
1. ser analisadas;
2. corresponder a uma whitelist;
3. ser validadas;
4. respeitar limites;
5. só depois ser executadas.

O ChatGPT não deve poder executar shell arbitrário.

========================
16. BRIEFING DIÁRIO
========================

Já tenho no ChatGPT uma tarefa agendada diária chamada:

“Resumo diário de interesses”

Ela é executada aproximadamente às 08:00.

Temas incluem:
- mercados;
- trading;
- ouro;
- Roblox;
- gaming;
- IA;
- automação;
- tecnologia;
- empreendedorismo;
- negócios online;
- França;
- Portugal;
- economia.

Futuramente quero:

08:00
→ ChatGPT gera briefing normalmente.

Depois:
→ RP5 abre o ChatGPT através de Chromium/Playwright;
→ localiza o chat/tarefa correta;
→ obtém o briefing mais recente;
→ extrai apenas o texto relevante;
→ remove markdown/URLs/citações que não façam sentido em voz;
→ prepara versão oral;
→ TTS;
→ Nest.

Não implementar já.

Quero guardar:

briefing.generated_at
briefing.available
briefing.played_today

Não quero que fale automaticamente às 08:00 se eu estiver a dormir.

Exemplo futuro:

sistema percebe que acordei
ou
primeira presença relevante da manhã

Nest:
“Bom dia, David. Queres ouvir o teu briefing?”

Eu:
“Sim.”

→ reproduz.

Ou:

“Hoje há três coisas que acho que merecem particularmente a tua atenção…”

Quero que soe como briefing falado, não como leitura robótica de uma página web.

========================
17. TRANSPORTES / RER A
========================

O módulo deve integrar informação em tempo real da Île-de-France Mobilités / PRIM.

Estação principal:

Noisy-le-Grand–Mont d’Est.

Na primeira PoC, os destinos configurados são:

- `work`: Lognes;
- `paris`: Nation.

“Paris” significa Nation nesta PoC. Um alias futuro como “Paris centre” poderá
apontar para Châtelet–Les Halles sem alterar o parser ou provider base.

Quero conseguir perguntar:

“Jarvis, quanto falta para o próximo comboio para Paris?”

“Jarvis, quanto falta para o comboio para Disney?”

“Jarvis, e para Marne-la-Vallée?”

“Tenho tempo de apanhar o próximo?”

Para Paris:
→ direção oeste / Paris.

Para Disney:
→ quero especificamente comboios que vão para Marne-la-Vallée–Chessy.

Não assumir que qualquer comboio sentido este chega a Chessy.

Usar dados em tempo real sempre que disponíveis.

Se não houver dados em tempo real:
→ indicar claramente que estamos a usar horários planeados.

Quero futuramente configurar:

transit.walk_time_to_station

ou até tempos diferentes:
- quarto → estação;
- estação → plataforma.

Exemplo:

próximo comboio = 3 min
tempo necessário = 5 min

Nest:
“Esse já está demasiado em cima. O seguinte passa daqui a 11 minutos.”

Ou ao sair:

“Tem um bom dia, David. O próximo RER para Paris passa daqui a 8 minutos.”

Integração futura sugerida:

transit/
├── idfm.py
├── rer_a.py
└── departures.py

Requisitos:
- API oficial PRIM preferencialmente;
- token em `.env`;
- nunca hardcoded;
- IDs de origem/destino e aliases apenas em configuração;
- validação dos IDs contra os referenciais oficiais atuais;
- distinguir IDs estáticos/monomodal, referências SIRI e IDs Navitia;
- usar preferencialmente `journeys` origem→destino com
  `data_freshness=realtime`, em vez de assumir que qualquer passagem na origem
  serve o destino;
- aceitar apenas viagens diretas cuja secção de transporte corresponde à
  linha, origem e destino configurados;
- Stop Monitoring apenas como diagnóstico/fallback explícito;
- cache curto;
- tratar rate limits;
- tratar timeout;
- tratar ausência de Internet;
- interface genérica para futuramente suportar outras redes.

O parser inicial de intents de trânsito deve ser determinístico e independente
de ChatGPT. Deve reconhecer apenas as formulações aprovadas para `work` e
`paris`, mapear para `transit.next(destination=...)` e não inventar ações ou
horários quando não reconhecer texto ou quando PRIM falhar.

Diagnóstico textual inicial:

```
python -m dn_home transit next --to work
python -m dn_home transit next --to paris
```

Resultado interno mínimo: destino, linha, hora de partida, minutos, direção,
indicador realtime/planeado e estado. Se realtime não estiver disponível, a
resposta deve dizê-lo claramente.

========================
18. IPHONE / PHONE BRIDGE
========================

Quero futuramente investigar integração com iPhone.

Primeiro objetivo:

quando alguém me ligar:
→ Raspberry Pi deteta chamada;
→ tenta obter nome/número do chamador;
→ Nest anuncia:

“David, a tua mãe está a ligar.”

ou:

“O teu pai está a ligar.”

Depois:

“Queres atender?”

Eu:
“Sim.”

Futuramente investigar se é tecnicamente possível aceitar/rejeitar a chamada.

Possível tecnologia a investigar:

Apple Notification Center Service — ANCS via BLE.

Não assumir que ANCS consegue realmente atender chamadas.

Primeiro investigar experimentalmente.

Fases:

V1:
detetar incoming call.

V2:
obter caller.

V3:
anunciar caller no Nest.

V4:
perguntar se quero atender.

V5:
aceitar/rejeitar apenas se o iPhone realmente permitir.

V6:
encaminhamento de áudio pela casa apenas se algum dia for tecnicamente viável.

Não implementar agora.

========================
19. PRESENÇA E ARRIVAL/DEPARTURE
========================

Não quero assumir:

porta abriu = saída

porque também pode ser entrada.

Quero futuramente combinar sinais:

- estado anterior da porta;
- movimento;
- ocupação;
- Bluetooth do telemóvel;
- SwitchBot;
- timestamps;
- BLE tags;
- outros sensores.

Entre os sinais previstos estão a presença Bluetooth/BLE da pulseira Amazfit e
a presença do iPhone. Ambos são evidência de presença, não autenticação
criptográfica. Não assumir que um dispositivo detetado prova de forma absoluta
quem entrou, nem que a ausência momentânea de BLE prova que David não está
presente.

Objetivo:

resident.arrived

e

resident.departed

serem eventos inferidos de forma razoavelmente robusta.

Se a confiança for baixa:
→ não executar automações potencialmente irritantes.

========================
19.1. IDENTIDADE E CLASSIFICAÇÃO DE ENTRADA
========================

A identificação de David não deve depender de um único sinal. Deve existir um
agregador de presença que combine evidência recente, qualidade/frescura dos
sinais e estado anterior da casa.

Depois de uma abertura ou evento candidato a entrada deve existir um grace
period curto e configurável para recolher sinais antes da classificação final.
Durante esse período o estado pode permanecer UNKNOWN.

Separar conceptualmente:

resident.identity:
- DAVID_CONFIRMED
- UNKNOWN

entry.classification:
- DAVID_CONFIRMED
- EXPECTED_VISITOR
- UNKNOWN
- UNEXPECTED_ENTRY

O estado deve guardar confidence e evidência suficiente para explicar a
decisão, sem transformar RSSI ou um único identificador BLE numa verdade
absoluta. Futuramente podem ser adicionados outros sinais sem reescrever as
automações consumidoras.

UNKNOWN não significa automaticamente intrusão. UNEXPECTED_ENTRY significa
operacionalmente que a entrada não foi associada a David nem a uma visita
planeada após o grace period; não constitui prova da identidade ou intenção da
pessoa.

========================
19.2. VISITAS E INTERVENÇÕES PLANEADAS
========================

Deve ser possível registar previamente uma visita ou intervenção, incluindo
por exemplo manutenção, técnico, residência, inspeção ou outra pessoa
autorizada.

Cada registo deve conter pelo menos:

- descrição;
- início e fim da janela temporal, com timezone explícito;
- nome e/ou empresa opcionais;
- estado SCHEDULED, ACTIVE, COMPLETED, CANCELLED ou EXPIRED;
- identificador estável para correlação e auditoria.

Uma abertura dentro de uma janela autorizada, sem David confirmado, deve poder
ser classificada como EXPECTED_VISITOR e não deve gerar imediatamente uma
entrada inesperada.

Eventos previstos:

visit.scheduled
visit.started
visit.completed
visit.expired
visit.cancelled

O mecanismo de criação/alteração destas autorizações deve ser validado e
auditável. Uma mensagem livre recebida de ChatGPT não pode, por si só, criar ou
ativar uma autorização.

As definições e transições de estado devem viver no State Store ou num
repositório próprio por ele coordenado, e não dentro da automação que reage à
porta.

========================
19.3. DECISÃO DE ENTRADA INESPERADA
========================

Fluxo conceptual:

1. Um evento de abertura/entrada cria um candidato com identificador de
   correlação.
2. O DN_Home inicia o grace period e tenta confirmar David através dos sinais
   de presença disponíveis.
3. Em paralelo, verifica visitas/intervenções planeadas aplicáveis à janela
   temporal.
4. Se David for confirmado, emite o fluxo normal de chegada.
5. Se existir uma visita aplicável, classifica EXPECTED_VISITOR e não cria
   aviso de entrada inesperada.
6. Se o grace period terminar sem David confirmado nem visita aplicável,
   classifica UNEXPECTED_ENTRY e emite `security.unexpected_entry`.

Sensores indisponíveis ou stale devem constar da evidência e dos logs. A
política deve privilegiar a redução de falsos positivos, mas continuar capaz de
tratar uma entrada não planeada de forma conservadora e configurável.

A reação futura a `security.unexpected_entry` deve ser configurável e composta
por ações independentes, para que a falha de uma não impeça as restantes:

- pedir Wake-on-LAN do desktop Windows;
- aguardar, com timeout, que o host fique acessível;
- verificar, quando suportado, o health/status do gravador;
- criar imediatamente uma notificação prioritária para David;
- reproduzir uma única vez um aviso de voz configurado dentro da casa.

Estas operações devem passar pela camada normal de actions validadas. A
automação de segurança coordena pedidos e estados; não deve executar shell
arbitrário nem chamar diretamente implementações específicas.

A notificação não deve ficar bloqueada à espera de o desktop ou gravador ficar
READY. Atualizações posteriores podem comunicar a mudança de estado do
gravador no mesmo incidente.

O aviso de voz deve ser state-aware e baseado apenas em estados confirmados:

1. Antes de `security.recorder` estar READY, a mensagem pode informar que foi
   detetada uma entrada não planeada, que David será alertado e que o sistema
   de segurança está a ser ativado. Não deve afirmar que existe vídeo ou
   gravação ativa.
2. Depois de `security.recorder` estar READY, a mensagem pode incluir o aviso
   configurado de que existe vídeo, gravação ou ambos em estado ativo.

A segunda regra também pode aplicar-se antes de o recorder principal ficar
READY se existir outro sistema de gravação independente cujo estado ativo
tenha sido comprovado. O simples pedido de arranque, estado STARTING, desktop
ONLINE ou envio de Wake-on-LAN não é prova de gravação.

Os templates, a formulação francesa concreta, o idioma e a voz não devem estar
hardcoded. Cada template pode ser reproduzido no máximo uma vez por transição
de estado do mesmo incidente; o aviso posterior a READY é configurável e não
deve bloquear nem repetir as restantes ações.

========================
19.4. WAKE-ON-LAN DO DESKTOP
========================

Criar futuramente uma abstração de device/service para o desktop:

devices.desktop:
  state:
    OFFLINE
    WAKING
    ONLINE

actions:
  desktop.wake
  desktop.check_online

Hostname, MAC, interface, endereço de broadcast e eventual IP de verificação
devem ser configuráveis. Não assumir IP fixo nem uma interface LAN específica.

Wake-on-LAN deve ter:

- cooldown;
- número limitado de retries;
- timeout total;
- logs por tentativa e resultado;
- idempotência por incidente;
- proibição de repetir magic packets indefinidamente.

Uma mudança futura de subnet deve exigir apenas configuração. Um pedido de
Wake-on-LAN aceite não significa que o desktop já esteja online nem que exista
gravação ativa.

========================
19.5. FRIGATE / GRAVADOR
========================

Nesta arquitetura o DN_Home não implementa diretamente toda a gravação de
vídeo. A responsabilidade inicial será:

DN_Home
→ Wake-on-LAN desktop
→ Windows inicia os componentes já configurados
→ DN_Home verifica futuramente health/status quando existir integração

Abstração futura:

security.recorder:
  UNKNOWN
  STARTING
  READY
  FAILED

Eventos:

security.recorder_ready
security.recorder_failed

Não assumir que ONLINE ou um Wake-on-LAN bem-sucedido significa que o sistema
já está a gravar. A definição concreta de READY deve corresponder a um health
check do componente efetivamente responsável pela gravação.

========================
19.6. NOTIFICAÇÃO PRIORITÁRIA
========================

Uma entrada inesperada deve criar uma notificação prioritária associada ao
mesmo `incident_id`. O canal poderá futuramente ser Telegram, push ou outro
provider configurado.

Conteúdo conceptual:

"Entrada não planeada detetada em casa.
David não foi identificado e não existe uma intervenção planeada ativa.
Desktop/gravador: <estado>.
Hora: <timestamp>."

Templates, idioma, canal, retries e política de atualização devem ser
configuráveis. Não implementar o canal nesta fase.

O estado deve distinguir pelo menos notificação PENDING, SENT e FAILED. O
DN_Home não deve afirmar nem registar que David foi efetivamente notificado
enquanto a action/provider não confirmar sucesso. Uma tentativa iniciada ou
colocada em fila continua PENDING.

========================
19.7. INDEPENDÊNCIA DE CHATGPT
========================

A deteção, agregação de presença, classificação, criação de incidente,
Wake-on-LAN, arranque/verificação do gravador e notificação devem funcionar sem
ChatGPT e sem Internet quando as dependências locais o permitirem.

ChatGPT poderá futuramente ajudar a formular mensagens ou conversar, mas não é
autoridade para decidir se a casa deve proteger, notificar ou iniciar o
gravador. Estas decisões pertencem a automações locais, determinísticas,
configuradas e auditáveis.

========================
20. EXEMPLO DE ARRIVAL
========================

Porta abre.

Sistema determina:
resident.arrived

Então:

→ acende luz apropriada conforme hora.

→ Nest:
“Bem-vindo de volta, David.”

Passado ~2 minutos:

cartão na base?

SIM:
→ nada.

NÃO:
→ Nest:
“David, não te esqueças de colocar o cartão da residência no sítio.”

Pode também futuramente perguntar:

“Como correu o teu dia?”

Mas apenas uma vez e quando fizer sentido.

========================
21. EXEMPLO DE DEPARTURE
========================

Sistema determina:
resident.departed

Antes de considerar saída concluída:

verificar:
- cartão;
- chaves;
- outros objetos futuros.

Tudo OK:

“Até logo, David. Tem um bom dia.”

Cartão ficou:

“David, espera. Estás a esquecer-te do cartão.”

Chaves ficaram:

“Espera. As tuas chaves ficaram no quarto.”

Ambos:

“David, estás a esquecer-te das chaves e do cartão.”

Opcionalmente:
→ informar próximo RER.

========================
22. CONTEXTO / ANTI-SPAM
========================

Criar conceito de cooldown.

Exemplos:

arrival_greeting:
não repetir durante X minutos.

card_reminder:
não repetir a cada poucos segundos.

phone:
não repetir anúncio indefinidamente.

briefing:
apenas uma reprodução automática por dia.

O sistema deverá recordar eventos recentes suficientes para evitar automações absurdas.

Para segurança deve existir ainda um conceito explícito de incidente:

security incident:
  incident_id:
  state: OPEN/ACKNOWLEDGED/CLOSED
  opened_at:
  classification:
  actions_requested:
  actions_completed:

Uma única abertura/entrada não deve provocar vários avisos de voz, vários
Wake-on-LAN nem dezenas de notificações. Enquanto existir um incidente OPEN ou
ACKNOWLEDGED aplicável, eventos repetidos devem ser correlacionados ou
deduplicados em vez de criar outro incidente. Cooldowns e chaves de
idempotência devem existir por ação. Fechar ou reabrir incidentes deve ser uma
transição explícita e registada.

========================
23. PRIVACIDADE
========================

Quero local-first.

Por defeito:

- não guardar áudio;
- apagar gravações temporárias;
- não guardar conversas de microfone desnecessariamente;
- não enviar áudio para serviços externos sem configuração explícita;
- logs não devem guardar segredos;
- não guardar conteúdos sensíveis sem necessidade;
- presença BLE é evidência e não autenticação forte;
- UNKNOWN não deve ser registado ou comunicado como certeza de intrusão;
- guardar apenas o estado/evidência de presença necessário à decisão;
- não conservar identificadores ou histórico de rastreamento para além da
  retenção configurada e necessária;
- logs de presença, visitas e incidentes não devem conter dados pessoais
  desnecessários;
- gravação e avisos devem respeitar a configuração da instalação e as regras
  aplicáveis;
- decisões e ações de segurança devem ser auditáveis através de eventos e
  logs correlacionados.

Quero poder configurar níveis de logging.

========================
24. LOGGING
========================

Formato legível.

Cada entrada deverá idealmente ter:

timestamp
level
module
event
action
result
latency
error

Exemplo:

2026-09-19 08:34:02 INFO arrival resident.arrived
2026-09-19 08:34:02 INFO lights bedroom_on success
2026-09-19 08:34:03 INFO voice speak success duration=1.2s

Logs devem ter rotação para não encher o disco.

========================
25. CONFIGURAÇÃO
========================

Nada importante hardcoded.

Exemplo:

config/config.yaml

house:
  resident_name: David

voice:
  primary_engine:
  fallback_engines: []
  default_voice:
  tts_volume: "+0%"
  language: pt-PT

speaker:
  manage_volume: false
  volume:
  restore_volume:

tts_engines:
  edge:
    enabled: true
  premium:
    type: local/lan_remote/online
    endpoint:

presence:
  grace_seconds:
  resident_devices:
    amazfit:
    iphone:

visits:
  timezone:
  retention_days:

devices:
  desktop:
    hostname:
    mac:
    wol_interface:
    wol_broadcast:
    cooldown_seconds:
    retries:
    timeout_seconds:

security:
  unexpected_entry:
    enabled:
    voice_warning:
      language: fr-FR
      before_recorder_ready_text:
      recorder_ready_text:
      recording_notice_mode: video/audio/both
  recorder:
    health_endpoint:
    startup_timeout_seconds:
  notifications:
    provider:
    priority:

nest:
  name:
  host:

automations:
  arrival_greeting: true
  card_reminder_delay: 120

transit:
  station:
  walking_time:

Segredos:

.env

Exemplo:

IDFM_API_TOKEN=

========================
26. TESTES
========================

Quero testes automatizados onde façam sentido.

Principalmente para:

- estado;
- event bus;
- automations;
- parsing;
- actions;
- cooldown;
- skill routing;
- agregação e frescura dos sinais de presença;
- grace period e estados UNKNOWN;
- precedência entre David confirmado, visita planeada e entrada inesperada;
- limites temporais, cancelamento e expiração de visitas;
- criação/deduplicação/transições de incidentes;
- cooldown, retries e timeout de Wake-on-LAN;
- distinção entre desktop ONLINE e recorder READY;
- falhas independentes de voz, notificação, desktop e recorder;
- funcionamento da decisão de segurança sem ChatGPT.

Hardware deverá poder ser mockado.

Quero poder simular:

python -m dn_home simulate arrival

ou equivalente.

Assim conseguimos desenvolver automações mesmo sem todos os sensores físicos.

========================
27. DIAGNÓSTICO
========================

Quero futuramente comandos como:

python -m dn_home status

python -m dn_home doctor

Que mostrem:

- serviço;
- Nest;
- Bluetooth;
- sensores;
- NFC;
- Internet;
- chat;
- TTS;
- microfone;
- sinais de presença e respetiva frescura;
- visitas planeadas ativas;
- estado do desktop/Wake-on-LAN;
- estado/health do gravador;
- notificações prioritárias, quando existir provider.

Sem expor segredos.

========================
28. ESTRUTURA SUGERIDA
========================

Não é obrigatório seguir exatamente esta estrutura se tiveres uma proposta tecnicamente melhor.

DN_Home/
├── dn_home/
│   ├── core/
│   │   ├── config.py
│   │   ├── events.py
│   │   ├── state.py
│   │   ├── actions.py
│   │   └── logging.py
│   │
│   ├── sensors/
│   │   ├── switchbot.py
│   │   ├── nfc.py
│   │   ├── ble_presence.py
│   │   ├── phone_presence.py
│   │   └── occupancy.py
│   │
│   ├── devices/
│   │   ├── nest.py
│   │   ├── lights.py
│   │   ├── desktop.py
│   │   └── phone.py
│   │
│   ├── presence/
│   │   └── aggregator.py
│   │
│   ├── visits/
│   │   └── scheduler.py
│   │
│   ├── security/
│   │   ├── incidents.py
│   │   └── recorder.py
│   │
│   ├── notifications/
│   │   └── base.py
│   │
│   ├── voice/
│   │   ├── tts/
│   │   ├── stt/
│   │   ├── microphone.py
│   │   └── wakeword.py
│   │
│   ├── skills/
│   │   ├── lights/
│   │   ├── transit/
│   │   ├── weather/
│   │   ├── reminders/
│   │   ├── phone/
│   │   ├── briefing/
│   │   ├── presence/
│   │   ├── visits/
│   │   ├── security/
│   │   └── conversation/
│   │
│   ├── intelligence/
│   │   ├── jarvis.py
│   │   ├── conversation.py
│   │   └── chatgpt_browser.py
│   │
│   ├── automations/
│   │   ├── arrival.py
│   │   ├── departure.py
│   │   ├── unexpected_entry.py
│   │   ├── card_reminder.py
│   │   ├── morning_briefing.py
│   │   └── incoming_call.py
│   │
│   ├── transit/
│   │   ├── idfm.py
│   │   ├── rer_a.py
│   │   └── departures.py
│   │
│   ├── phone_bridge/
│   │   └── ancs.py
│   │
│   ├── cli.py
│   └── __main__.py
│
├── config/
│   └── config.example.yaml
│
├── data/
├── logs/
├── tests/
├── scripts/
├── systemd/
├── .env.example
├── pyproject.toml
├── README.md
└── LICENSE

========================
28.1. GIT
========================

O projeto deve ser inicializado como repositório Git antes da implementação.

O ficheiro .gitignore deve excluir:

- .env;
- ambientes virtuais;
- logs;
- caches;
- ficheiros temporários;
- áudio gerado;
- segredos.

========================
29. SYSTEMD
========================

Futuramente quero que DN_Home possa funcionar como serviço.

Preparar arquitetura compatível com systemd.

Para reduzir a latência de voz, avaliar nessa fase manter o processo residente,
reutilizar ligações Google Cast saudáveis, reconectar automaticamente quando
necessário e manter o servidor HTTP local disponível na porta configurada.
Não implementar este daemon persistente durante as correções da Fase 1.

Mas:

NÃO ativar nem instalar automaticamente um serviço nesta primeira etapa.

Quando chegar essa fase quero:

restart automático razoável
logging adequado
startup depois da rede/Bluetooth quando necessário
shutdown limpo

========================
30. FAIL-SAFE
========================

Se ChatGPT falhar:
→ automações locais continuam.

Se TTS online falhar:
→ idealmente permitir fallback local.

Se Nest estiver offline:
→ não bloquear event loop.

Se Internet falhar:
→ sensores e luzes locais continuam.

Se transit API falhar:
→ responder de forma clara ou usar horário planeado se disponível.

Se um sensor ficar offline:
→ estado deve indicar unknown/stale, não inventar valor.

Se Amazfit ou iPhone não forem detetados:
→ não concluir imediatamente que David está ausente; respeitar grace period,
frescura e restantes sinais.

Se Wake-on-LAN falhar:
→ limitar retries, registar `desktop.wake_failed` e continuar a notificação e
as restantes ações possíveis.

Se o desktop ficar ONLINE mas o gravador não ficar READY:
→ manter estados distintos, emitir `security.recorder_failed` após timeout e
atualizar o incidente/notificação sem assumir gravação.

Se TTS ou Nest falharem durante uma entrada inesperada:
→ não bloquear Wake-on-LAN, verificação do gravador ou notificação.

Se ChatGPT estiver indisponível:
→ toda a classificação e reação base de segurança continua funcional.

========================
31. PERFORMANCE
========================

Este projeto vai correr num Raspberry Pi 5.

Não quero processos pesados desnecessários permanentemente.

Modelos STT mais pesados só devem ser carregados quando apropriado ou de forma eficiente.

Quero medir:

- CPU
- RAM
- latency

Para o caminho de voz, medir separadamente:

- tts_generation_ms;
- http_server_start_ms;
- cast_connection_ms;
- receiver_launch_ms;
- play_media_to_http_get_ms;
- http_get_to_playback_started_ms;
- total_text_to_audio_started_ms.

A duração total da reprodução/operação não deve ser apresentada como latência
até ao início da fala.

antes de decidir soluções permanentes.

========================
32. PRIMEIRA FASE — ÚNICA COISA A IMPLEMENTAR AGORA
========================

Apesar de toda esta especificação, NÃO quero implementar o Jarvis inteiro agora.

A primeira fase é exclusivamente:

Raspberry Pi 5
→ texto
→ TTS
→ Google Nest
→ som audível.

Quero provar primeiro que o Jarvis consegue falar.

OBJETIVO:

executar:

python -m dn_home speak "Bem-vindo a casa, David."

e ouvir essa frase no Google Nest.

Também quero:

python -m dn_home voices

e:

python -m dn_home speak --voice <nome> "Olá David. Esta é a voz da tua casa."

========================
33. PROCEDIMENTO DA FASE 1
========================

ANTES DE ALTERAR O SISTEMA:

Analisa o Raspberry Pi.

Verifica:

- sistema operativo;
- arquitetura;
- kernel;
- Python;
- pip/venv;
- Bluetooth;
- interfaces de rede relevantes apenas para diagnóstico;
- ferramentas existentes;
- Google Cast/mDNS;
- se o Nest é descoberto na LAN.

NÃO alterar a rede.

NÃO reiniciar serviços desnecessariamente.

NÃO instalar nada ainda.

Depois apresenta-me:

1. diagnóstico;
2. arquitetura proposta;
3. bibliotecas Python necessárias;
4. pacotes de sistema necessários, se existirem;
5. abordagem para TTS;
6. abordagem Google Cast;
7. como o Nest vai conseguir obter/reproduzir o áudio;
8. possíveis problemas de isolamento/mDNS;
9. estratégia de fallback;
10. comandos que pretendes executar.

Só depois da minha aprovação podes começar a instalar/implementar.

========================
34. IMPLEMENTAÇÃO MÍNIMA DA FASE 1
========================

Depois de aprovada:

Criar ambiente Python isolado.

Criar apenas a estrutura mínima necessária.

Implementar interfaces separadas:

TTSEngine

e

Speaker / CastSpeaker

Fluxo:

text
↓
TTS
↓
temporary audio
↓
local HTTP serving se necessário
↓
Google Cast
↓
Nest

Não implementar ainda:
- SwitchBot;
- NFC;
- BLE keys;
- iluminação;
- ChatGPT;
- Chromium;
- Playwright;
- briefing;
- transit;
- microfone;
- STT;
- wake word;
- iPhone;
- ANCS;
- identificação de presença Amazfit/iPhone;
- visitas/intervenções planeadas;
- classificação de entrada inesperada;
- Wake-on-LAN do desktop;
- integração Frigate/gravador;
- notificações prioritárias;
- incidentes de segurança.

Apenas deixar arquitetura preparada.

========================
35. ACCEPTANCE CRITERIA — FASE 1
========================

A fase 1 só é considerada concluída quando:

1. o Nest é identificado corretamente;

2. consigo executar:

python -m dn_home speak "Bem-vindo a casa, David."

3. ouço a frase no Nest;

4. consigo escolher entre várias vozes;

5. consigo definir volume através de configuração ou CLI;

6. o áudio temporário é limpo posteriormente;

7. falha do Nest é tratada sem crashar todo o programa;

8. logs mostram claramente o processo;

9. existe README com instruções;

10. não foi alterada nenhuma configuração de rede;

11. não há API paga;

12. nenhuma password/token está hardcoded;

13. os módulos TTS e Cast estão desacoplados;

14. existe pelo menos um comando simples de diagnóstico;

15. o código está preparado para crescer para as fases seguintes.

========================
36. OBJETIVO DA SESSÃO ATUAL
========================

Nesta sessão não quero construir o sistema completo.

Quero apenas:

ANALISAR
↓
PLANEAR
↓
EU APROVO
↓
IMPLEMENTAR FASE 1
↓
RP5 FAZ O GOOGLE NEST DIZER UMA FRASE.

Começa agora apenas pela análise do ambiente e pelo plano.

Não instales nada e não alteres o sistema até eu autorizar explicitamente.
