# Provenienza e decisione

Analisi del 7 ottobre 2026. Sorgente di riferimento: [FingerprintJS](https://github.com/fingerprintjs/fingerprintjs), commit `dac5ae59409669f09aa09c0b2f44b7615b0520da`, package 5.3.0. Implementazione di questo repository originale, senza copia di codice upstream.

Il percorso [agent.ts](https://github.com/fingerprintjs/fingerprintjs/blob/dac5ae59409669f09aa09c0b2f44b7615b0520da/src/agent.ts) serializza i valori dei componenti ordinando le chiavi, poi calcola l’hash. Le fonti comprendono dati dello schermo, ma ci sono eccezioni: Safari recente omette la risoluzione, Safari/Firefox recenti omettono il frame. Non è corretto sostenere che qualsiasi cambio schermo modifichi sempre FingerprintJS.

La [policy upstream](https://github.com/fingerprintjs/fingerprintjs/blob/dac5ae59409669f09aa09c0b2f44b7615b0520da/docs/version_policy.md) cerca di mantenere compatibilità entro una minor, ammettendo variazioni per correzioni. Singularity separa invece esplicitamente versione del package, schema dell’osservazione e policy del confronto.

Le API web non forniscono la garanzia di identificazione richiesta inizialmente. [hardwareConcurrency](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/hardwareConcurrency) può essere ridotto dal browser; [deviceMemory](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/deviceMemory) è approssimato e non universale. Le [indicazioni W3C](https://www.w3.org/TR/fingerprinting-guidance/) descrivono mitigazioni e limiti della persistenza. L’utente ha scelto esplicitamente rilevamento automatico probabilistico senza login o associazione, rinunciando alla garanzia assoluta.

Codex Mind: cinque contributi Forge compatti, sei pareri Council e cinque revisioni anonime. Esito `build`, fiducia media, nessun blocco architetturale; non è una prova di accuratezza. Hyper ha scelto Relay: autore unico, verifica aritmetica dei casi limite, test e falsificazione finale separata. Le prospettive degli agenti sono correlate e non costituiscono diversità di fornitori/modelli.

L’idea mantenuta è il confronto ripetuto dopo esclusione di ogni famiglia. I dati ridotti devono bastare nuovamente a distinguere lo stesso candidato. Vengono scartati servizi di identità, storage automatico, crescita automatica dello storico e qualunque promessa di unicità. La minore quantità di dati può produrre più collisioni e più astensioni; non abbiamo una coorte che dimostri superiorità su FingerprintJS.

[Graphify](https://github.com/Graphify-Labs/graphify) 0.9.76 ha indicizzato localmente 101 file upstream: 402 nodi, 976 archi, nessuna API LLM. Diagnostica upstream: 107 endpoint mancanti nel corpus grezzo, 83 relazioni accorpate e 2 autoanelli. Le conclusioni sono state ricontrollate nei sorgenti; il grafo è un indice incompleto. Nessuna percentuale di risparmio token è stata misurata o rivendicata.

## Indice di sviluppo

La nuova libreria è stata indicizzata separatamente: 6 file sorgente, 54 nodi, 7 comunità. I nodi centrali comprendono `validateSnapshot`, `match` e `SingularityError`. La query sul collegamento fra `runnerUp`, `best` e `match` guida direttamente alla verifica delle ambiguità. L’export `index.ts` non produce simboli propri nell’estrattore; la diagnostica del grafo finale segnala un autoanello e non ricostruisce eventuali relazioni perse prima del build. Le relazioni di un grafo non diretto non dimostrano la direzione delle chiamate.

Con Graphify già installato, rigenerare dal working tree:

```sh
graphify extract src --code-only --out .
graphify cluster-only . --no-label
graphify query 'runnerUp' --context call --budget 800
```

Gli output locali `graphify-out/graph.json`, `GRAPH_REPORT.md` e `graph.html` sono esclusi dal package e da Git. L’estrazione del codice usa AST locali; documenti e API LLM non partecipano a questi comandi. Il grafo facilita la navigazione, i sorgenti e i test rimangono l’evidenza autorevole.
