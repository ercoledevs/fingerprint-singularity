# Fingerprint Singularity

Una libreria TypeScript per raccogliere **impronte indipendenti dai dati dello schermo** e confrontare osservazioni con candidati precedenti, anche quando qualche segnale cambia. Implementazione originale, ispirata all’analisi di FingerprintJS. Nessuna dipendenza runtime, rete, cookie, storage o richiesta di permessi.

**Non produce un identificatore fisico universale.** Il browser non espone dati sufficienti per garantire lo stesso ID univoco su ogni browser e per sempre. Due dispositivi con le stesse osservazioni producono lo stesso hash. Questa libreria privilegia stabilità e spiegabilità, sacrificando capacità discriminante; non è dimostrato che identifichi più accuratamente di FingerprintJS.

## Due risultati diversi

| Risultato | Significato | Cosa può cambiare |
|---|---|---|
| `digest(snapshot)` | Hash SHA-256 di una singola osservazione, incluso lo scope | Cambia quando cambia un dato normalizzato |
| `match(snapshot, candidates)` | Candidato compatibile tra quelli forniti dall’applicazione | Può mantenere lo stesso `candidateId` con dati diversi, oppure astenersi |

Un ID assegnato dall’applicazione resta uguale solo quando il candidato viene restituito. Per confrontare visite di browser differenti, l’applicazione deve fornire osservazioni precedenti, per esempio dal proprio backend. Non serve un account, ma **un browser nuovo senza candidati precedenti non può recuperare magicamente un ID**. La libreria non conserva né ricostruisce quei candidati.

## Avvio

Richiede Node.js 20+ per lo sviluppo. Il codice browser richiede moduli ES moderni; l’hash richiede Web Crypto su HTTPS o localhost.

```sh
git clone https://github.com/ercoledevs/fingerprint-singularity.git
cd fingerprint-singularity
npm ci
npm run check
npm run demo
# http://127.0.0.1:4173
```

Il package non è pubblicato su npm. Per usarlo in un altro progetto:

```sh
npm pack
# Nel progetto consumatore, installare il tarball prodotto:
npm install /percorso/fingerprint-singularity-0.1.0.tgz
```

```ts
import { collect, digest, match, type Candidate } from 'fingerprint-singularity'

const snapshot = collect({ scope: 'mia-app.example' })
const fingerprint = await digest(snapshot)

// L’applicazione fornisce l’intero insieme pertinente, con ID e retention propri.
// In questo esempio non sono ancora disponibili osservazioni precedenti.
const candidates: Candidate[] = []
const result = match(snapshot, candidates)

console.log(fingerprint) // sg1_<64 caratteri esadecimali>: hash dell’osservazione
console.log(result.status, result.reason)
if (result.status === 'matched') {
  console.log(result.candidateId) // Continuità ipotizzata, non identità autenticata
}
```

Esempio di continuità quando la memoria non è esposta da un altro browser:

```ts
const previous = {
  schema: 'singularity/v1' as const,
  scope: 'mia-app.example',
  signals: { platform: 'linux' as const, cores: 8, memory: 8, language: 'en', timezone: 'UTC' },
}
const current = { ...previous, signals: { ...previous.signals, memory: null } }
match(current, [{ id: 'candidato-123', snapshot: previous }]).candidateId
// 'candidato-123'; i due digest sono differenti.
```

## Segnali utilizzati

| Famiglia | Dato normalizzato | Peso | Limite |
|---|---|---:|---|
| Piattaforma | `windows`, `macos`, `ios`, `android`, `linux`, `chromeos` | 3 | La piattaforma dichiarata può essere alterata; iPad in modalità desktop può apparire macOS |
| Calcolo | Core dichiarati, arrotondati per difetto in classi 1–64 | 2 | Il browser può limitarli; una variazione spesso causa astensione |
| Calcolo | Memoria dichiarata, classi 0.25–64 GiB | 1 | Approssimata e non disponibile in tutti i browser |
| Impostazioni locali | Lingua primaria, senza regione | 1 | Configurabile separatamente in ogni browser |
| Impostazioni locali | Nome del fuso orario | 1 | Modificabile; alias differenti restano diversi |

Un dato assente/bloccato è `null` e non guadagna punti, neppure se manca da entrambe le parti. Non si raccoglie la stringa completa dello user agent: viene letta soltanto per ricavare la famiglia della piattaforma, senza conservarne versioni o modello. Le famiglie sono raggruppamenti operativi, **non prove statisticamente indipendenti**.

Sono esclusi schermo, risoluzione, viewport, zoom, touch, GPU, WebGL, canvas, audio, font, IP, batteria, versioni del browser e del sistema operativo. L’esclusione evita la dipendenza diretta da queste misure; non prova che cambiare hardware non possa alterare indirettamente altri segnali del sistema.

## Confronto con esclusione delle famiglie

La policy `envelope/v1` richiede:

1. Somiglianza e copertura almeno **0,75**, su tutte e tre le famiglie. Il denominatore comprende anche i segnali mancanti. Piattaforme note differenti impediscono la qualificazione.
2. Un margine di almeno **0,15** rispetto al migliore rivale senza contraddizioni. In assenza di rivali il margine è `null` e questo controllo è soddisfatto.
3. Lo stesso candidato deve superare i controlli dopo aver escluso, a turno, ciascuna delle tre famiglie. Ogni confronto ridotto richiede entrambe le famiglie rimaste e ricalcola il denominatore.

Ogni prova ridotta riconsidera **tutti** i candidati, anche quelli inizialmente scartati. Escludere la piattaforma elimina anche il relativo veto. Un candidato non passa quindi soltanto perché un dato fragile ha escluso i suoi rivali. Il risultato espone contributi, copertura, contraddizioni e prove di esclusione.

Queste soglie sono euristiche fissate e versionate, non calibrate su una popolazione. Con i pesi correnti una variazione dei core può superare la soglia iniziale ma fallire le prove ridotte. Una variazione di un singolo segnale di peso 1 può essere tollerata. L’astensione può essere frequente.

| Stato | Significato |
|---|---|
| `matched` | Un candidato supera tutte le prove nell’insieme fornito |
| `unmatched` | Lista vuota o nessun candidato qualificato con evidenza sufficiente |
| `abstain` | Evidenza incompleta, candidati ambigui o risultato instabile nelle prove ridotte |

Precedenza: convalida completa → lista vuota → evidenza dell’osservazione → qualificazione → margine → prove di esclusione. Un errore in qualsiasi candidato fa fallire l’intera chiamata; nessun risultato parziale. `candidateId` è sempre `null` salvo `matched`. Non assegnare automaticamente un nuovo ID per ogni astensione: significherebbe creare falsi dispositivi distinti. Non modificare automaticamente un candidato sulla base di un match incerto.

La lista diagnostica `candidates` mantiene l’ordine degli input; la decisione e i report di esclusione sono indipendenti da quell’ordine. I pareggi non vengono risolti assegnando arbitrariamente un ID.

**La selezione dei candidati conta:** fornire un solo dispositivo con dati comuni può creare un risultato apparentemente univoco. Una coppia di candidati con osservazioni equivalenti produce astensione. Nessun hash o margine elimina le collisioni di origine.

## API e contratti

- `collect({ scope, environment? }): Snapshot`: raccolta sincrona. L’adapter facoltativo rende i test riproducibili; in Node è obbligatorio.
- `canonicalize(snapshot): string`: tupla JSON v1, ordine congelato, senza timestamp.
- `digest(snapshot): Promise<string>`: SHA-256 con prefisso `sg1_`; richiede Web Crypto, senza fallback casuale.
- `compare(left, right): Comparison`: confronto di una coppia. `qualifies` non equivale a `matched`: non verifica rivali e prove ridotte.
- `match(snapshot, candidates): MatchResult`: funzione pura; al massimo 256 candidati, nessun troncamento.
- `parseSnapshot(json)` / `validateSnapshot(value)`: ingressi con convalida rigorosa; restituiscono una copia.
- `SCHEMA`, `POLICY_VERSION`, `POLICY`, `LIMITS`, `SingularityError`: contratti esportati.

Gli errori espongono `code`: `INVALID_INPUT`, `INCOMPATIBLE_SCHEMA`, `SCOPE_MISMATCH`, `LIMIT_EXCEEDED`, `DUPLICATE_ID`, `BROWSER_UNAVAILABLE`, `CRYPTO_UNAVAILABLE`.

Scope e ID: 1–128 caratteri nell’alfabeto ASCII documentato dal validatore. Snapshot JSON: massimo 2.048 unità UTF-16; prima di passare dati da rete, applicare anche un limite al body HTTP. Scope diversi non vengono confrontati e producono digest diversi. Lo scope è uno spazio dei nomi pubblico, non un controllo di accesso né una protezione contro chi modifica gli input. Gli oggetti con proprietà sconosciute, accessor, prototipi non ordinari o valori non normalizzati vengono rifiutati. Un proxy JavaScript ostile nello stesso processo non è un input isolato o sicuro: usare JSON limitato per dati non fidati.

## Dati e ciclo di vita

Nessuno stato persistente: nessun cookie, localStorage, IndexedDB, chiamata HTTP o recupero dopo cancellazione. Chi integra la libreria decide scopo, informativa, retention, scadenza e cancellazione delle osservazioni. Eliminare i candidati dal proprio archivio e svuotare le cache applicative li rende indisponibili alla libreria; non esiste un meccanismo di ripristino nascosto.

I dati sono falsificabili e potenzialmente personali. **Non usare digest, somiglianza o match come autenticazione, autorizzazione o prova antifrode.** L’hash non rende questi dati anonimi. Nessuna telemetria automatica.

Schema e policy hanno versioni distinte dal package. Una futura modifica a normalizzazione/canonicalizzazione richiederà un nuovo schema; cambiare pesi, soglie o semantica richiederà una nuova policy. Non mischiare schemi diversi: la libreria li rifiuta. Per rollback, reinstallare il tarball precedente e usare soltanto candidati compatibili; questa versione non esegue migrazioni né scrive archivi.

## Verifiche e sviluppo

```sh
npm run check                    # build, contratti e tipi
npx playwright install          # browser necessari, se assenti
npm run test:browser             # Chromium, Firefox, WebKit + demo
npm run bench                   # scaling, warmup, mediana/p95, heap Node
npm pack --dry-run              # contenuti distribuiti
```

Il controllo browser fallisce se un motore non parte: nessuno skip silenzioso. Budget locali di regressione: raccolta p95 <10 ms, confronto con 256 candidati p95 <50 ms, heap trattenuto Node dopo GC <32 MiB. Sono limiti di verifica su questo ambiente, non promesse su ogni dispositivo. Le misure non dimostrano accuratezza. I report locali in `artifacts/` non vengono versionati; [VERIFICATION.md](docs/VERIFICATION.md) descrive il run consegnato e i limiti.

Graphify indicizza `src` per le consultazioni di sviluppo, senza LLM esterni. [ARCHITECTURE.md](docs/ARCHITECTURE.md) descrive moduli e policy; [RESEARCH.md](docs/RESEARCH.md) registra provenienza e scelte. Licenza MIT, conservata dal repository originale del progetto.
