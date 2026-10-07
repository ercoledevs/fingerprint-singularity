# Verifica della versione 0.1.0

Run locale del **7 ottobre 2026**, macOS arm64, Node.js 24.21.0. Il risultato riguarda il contratto della libreria sperimentale; non dimostra identificazione fisica o accuratezza su una popolazione.

| Controllo | Esito | Evidenza |
|---|---|---|
| Compilazione TypeScript | PASS | `npm run build`, configurazione strict e dichiarazioni pubbliche |
| Test Node | PASS | 29 test con `node --test tests/*.test.mjs` |
| Tipi del consumatore | PASS | `npm run test:types` |
| Falsificazione indipendente | PASS | Rilettura dei sorgenti, riesecuzione test e riproduzioni del difetto corretto |
| Invarianti combinatorie | PASS | Verificatore: 59.049 scenari di stati osservazione/candidato, ordine e astensione sui duplicati |
| Chromium 145.0.7632.6 | PASS | Esecuzione reale, viewport desktop/mobile, hash invariato, controlli senza storage/rete, matcher |
| WebKit 26.0 | PASS | Stessi controlli reali |
| Firefox 146.0.1 locale | UNKNOWN | Fallimento avvio plugin-container / sandbox macOS, prima dell’esecuzione della libreria; anche modalità grafica non disponibile |
| Confronto Chromium/WebKit sullo stesso host | PASS per questo caso | Candidato compatibile; un solo host, non un test di accuratezza |
| Budget di prestazione Node | PASS | 256 candidati, tre esclusioni, warmup e 200 campioni |
| Cambio fisico di monitor | UNKNOWN | Verificati esclusione dei segnali e cambio viewport; nessuna sostituzione hardware effettuata |
| Stabilità nel tempo / unicità di popolazione | UNKNOWN | Nessuna coorte etichettata o osservazione longitudinale |

Il comando browser completo locale restituisce correttamente codice di uscita 1 per Firefox: **non è un run interamente verde**. La pipeline GitHub Actions è predisposta su Linux per eseguire tutti e tre i motori; il suo esito va letto sul commit effettivo, non dedotto dalla configurazione.

## Difetto trovato e corretto

Il verificatore ha dimostrato che un array con `Symbol.iterator` personalizzato poteva nascondere rivali o fornire più di 256 candidati pur dichiarando una lunghezza inferiore. Il confronto ora cattura la lunghezza e legge ciascun elemento numerico tramite descrittore di proprietà, senza eseguire iteratori o getter. Rifiuta buchi, elementi ereditati e accessor. Le riproduzioni originali e i nuovi test di regressione passano.

## Misure locali

Run Node dopo la correzione: raccolta con adapter p95 circa **0,003 ms**; confronto completo con 256 candidati p95 circa **0,847 ms**. Nei browser disponibili, nei run locali, raccolta e matching rispettano p95 <10 ms e <50 ms. I clock browser possono avere precisione ridotta.

Heap Node trattenuto dopo GC: circa **5 KiB** nel run; delta prima del GC circa **23 MiB**. Sono osservazioni rumorose, non allocazioni massime garantite. Non esiste una misura portabile delle allocazioni di picco per tutti i browser: il limite di lavoro deriva anche da 5 segnali, 3 esclusioni e 256 candidati. Budget di regressione: heap trattenuto <32 MiB. Nessun confronto di prestazioni o accuratezza con FingerprintJS.

## Riproduzione

```sh
npm ci --ignore-scripts
npm run check
npx playwright install chromium firefox webkit
npm run test:browser
npm run bench
npm pack --dry-run
```

I report grezzi vengono scritti in `artifacts/`, esclusa da Git. Non vengono inviati altrove. Un nuovo ambiente può cambiare tempi o disponibilità dei browser: riportare i fallimenti, senza trasformare un test non eseguito in PASS.
