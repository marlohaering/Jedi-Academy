# Server load indicator

Approved in chat: a persistent small indicator at the top of the game, showing dedicated-server CPU (100% = one core), resident RAM and gateway-to-game UDP response time. Yellow/red indicate high load or delayed/missing responses. Missing readings must remain unknown.

## Approaches
Measure the dedicated process, chosen because VM totals include gateway downloads and asset repacking. VM-wide metrics were considered but would obscure game load. No engine rebuild or new dependencies are required. The indicator diagnoses symptoms; it does not fix or establish the cause of the reported map-change slowdown.

Implementation choices: sample once every two seconds for all authenticated clients; CPU warning at 80/95%, response warning at 100/250 ms. Use process identity to reset CPU sampling on restart. Do not capture passwords or expose process details.
